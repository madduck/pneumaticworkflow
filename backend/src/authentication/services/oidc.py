import base64
import hashlib
import json
import secrets
from datetime import timedelta
from typing import Any
from urllib.parse import quote_plus, urlencode, urlsplit, urlunsplit

import jwt
import requests
from django.conf import settings
from django.core.cache import cache
from django.db import transaction
from django.utils import timezone
from django.utils.translation import gettext as _

from src.accounts.models import Account

from ..models import OIDCLoginAttempt  # noqa: TID252
from .exceptions import AuthException

_ATTEMPT_TTL = timedelta(minutes=10)


class OIDCError(AuthException):
    """An error with a public message and a reason safe to log."""

    def __init__(self, message: str, *, reason: str) -> None:
        super().__init__(message)
        self.reason = reason


def _reject(reason: str) -> OIDCError:
    return OIDCError(
        _('OpenID Connect sign-in failed. Start a new sign-in.'),
        reason=reason,
    )


def _https_url(value: Any) -> str:
    reason = 'The configuration contains a missing or invalid HTTPS URL.'
    if not isinstance(value, str):
        raise _reject(reason)
    try:
        url = urlsplit(value)
    except ValueError:
        raise _reject(reason) from None
    if (
        url.scheme != 'https'
        or not url.hostname
        or url.fragment
        or url.username is not None
        or '\\' in value
    ):
        raise _reject(reason)
    return value


def _json_request(
    method: str, url: str, *, endpoint: str, **kwargs: Any,
) -> dict[str, Any]:
    try:
        response = requests.request(
            method,
            _https_url(url),
            timeout=5,
            allow_redirects=False,
            **kwargs,
        )
    except (requests.RequestException, ValueError) as exc:
        raise _reject(
            f'Request to the {endpoint} failed: {type(exc).__name__}.',
        ) from None
    if response.status_code != 200:
        raise _reject(
            f'The {endpoint} returned HTTP {response.status_code}.',
        )
    reason = f'The {endpoint} did not return a JSON object.'
    try:
        data = response.json()
    except ValueError:
        raise _reject(reason) from None
    if not isinstance(data, dict):
        raise _reject(reason)
    return data


class OIDCService:
    """Run the OpenID Connect authorisation code flow for one deployment."""

    def __init__(self) -> None:
        if (
            not settings.PROJECT_CONF['SSO_AUTH']
            or settings.PROJECT_CONF.get('SSO_PROVIDER') != 'oidc'
        ):
            raise OIDCError(
                _('OpenID Connect sign-in is disabled.'),
                reason='OIDC is disabled on the backend.',
            )
        self.issuer = _https_url(settings.OIDC_ISSUER)
        self.client_id = settings.OIDC_CLIENT_ID
        self.client_secret = settings.OIDC_CLIENT_SECRET
        self.redirect_uri = _https_url(settings.OIDC_REDIRECT_URI)
        if (
            not self.client_id
            or not self.client_secret
            or len(self.issuer) > 512
            or urlsplit(self.issuer).query
        ):
            raise _reject('The issuer or client configuration is invalid.')

        configured_id = settings.OIDC_ACCOUNT_ID
        if configured_id == '':
            account_ids = list(
                Account.objects.values_list('pk', flat=True)[:2],
            )
            if not account_ids:
                raise OIDCError(
                    _('Create a workspace before using OIDC.'),
                    reason='There is no workspace for OIDC.',
                )
            if len(account_ids) > 1:
                raise OIDCError(
                    _('Set OIDC_ACCOUNT_ID to choose a workspace for OIDC.'),
                    reason='Multiple workspaces exist. Set OIDC_ACCOUNT_ID.',
                )
            self.account_id = account_ids[0]
        else:
            reason = 'OIDC_ACCOUNT_ID is not a valid workspace ID.'
            try:
                self.account_id = int(configured_id)
            except (TypeError, ValueError):
                raise _reject(reason) from None
            if (
                self.account_id < 1
                or str(self.account_id) != str(configured_id)
            ):
                raise _reject(reason)

    def _binding(self, browser_key: str) -> str:
        value = json.dumps(
            (
                browser_key,
                self.issuer,
                self.client_id,
                self.redirect_uri,
                self.account_id,
            ),
        )
        return hashlib.sha256(value.encode()).hexdigest()

    def _metadata(self) -> dict[str, Any]:
        key = (
            'oidc:metadata:' + hashlib.sha256(self.issuer.encode()).hexdigest()
        )
        metadata = cache.get(key)
        if metadata is None:
            metadata = _json_request(
                'GET',
                self.issuer.rstrip('/') + '/.well-known/openid-configuration',
                endpoint='discovery endpoint',
            )
            if metadata.get('issuer') != self.issuer:
                raise _reject('The provider issuer differs from OIDC_ISSUER.')
            for endpoint in (
                'authorization_endpoint',
                'token_endpoint',
                'jwks_uri',
            ):
                _https_url(metadata.get(endpoint))
            cache.set(key, metadata, timeout=300)
        return metadata

    def start(self, browser_key: str) -> str:
        """Return the provider URL for a new browser-bound sign-in."""
        endpoint = urlsplit(self._metadata()['authorization_endpoint'])
        state = secrets.token_urlsafe(32)
        nonce = secrets.token_urlsafe(32)
        verifier = secrets.token_urlsafe(32)
        challenge = (
            base64.urlsafe_b64encode(
                hashlib.sha256(verifier.encode()).digest(),
            )
            .rstrip(b'=')
            .decode()
        )
        now = timezone.now()
        OIDCLoginAttempt.objects.filter(expires_at__lte=now).delete()
        OIDCLoginAttempt.objects.create(
            state=state,
            browser_binding=self._binding(browser_key),
            nonce=nonce,
            verifier=verifier,
            expires_at=now + _ATTEMPT_TTL,
        )
        query = urlencode(
            {
                'client_id': self.client_id,
                'redirect_uri': self.redirect_uri,
                'scope': settings.OIDC_SCOPES,
                'state': state,
                'nonce': nonce,
                'code_challenge': challenge,
                'code_challenge_method': 'S256',
                'response_type': 'code',
            },
        )
        return urlunsplit(
            endpoint._replace(
                query=f'{endpoint.query}&{query}' if endpoint.query else query,
            ),
        )

    def _consume(self, state: str, browser_key: str) -> OIDCLoginAttempt:
        with transaction.atomic():
            attempt = (
                OIDCLoginAttempt.objects.select_for_update()
                .filter(
                    pk=state,
                    expires_at__gt=timezone.now(),
                )
                .first()
            )
            if not attempt:
                raise _reject('The sign-in attempt is missing or expired.')
            if not secrets.compare_digest(
                attempt.browser_binding,
                self._binding(browser_key),
            ):
                raise _reject(
                    'The sign-in attempt does not match this browser '
                    'or configuration.',
                )
            attempt.delete()
            return attempt

    def _id_claims(
        self,
        id_token: Any,
        jwks_uri: str,
        nonce: str,
    ) -> dict[str, Any]:
        if not isinstance(id_token, str):
            raise _reject('The provider did not return an ID token.')
        try:
            header = jwt.get_unverified_header(id_token)
            if header.get('alg') != 'RS256':
                raise _reject(
                    'The provider did not sign the ID token with RS256.',
                )
            keys = _json_request(
                'GET', jwks_uri, endpoint='signing key endpoint',
            ).get('keys')
            if not isinstance(keys, list):
                raise _reject('The provider sent no valid signing key list.')
            kid = header.get('kid')
            candidates = [
                key
                for key in keys
                if isinstance(key, dict)
                and key.get('kty') == 'RSA'
                and key.get('use', 'sig') == 'sig'
                and key.get('alg', 'RS256') == 'RS256'
                and (kid is None or key.get('kid') == kid)
            ]
            if len(candidates) != 1:
                raise _reject('The ID token has no unique matching key.')
            claims = jwt.decode(
                id_token,
                jwt.PyJWK.from_dict(candidates[0], 'RS256').key,
                algorithms=['RS256'],
                audience=self.client_id,
                issuer=self.issuer,
                leeway=30,
                options={
                    'require': ['iss', 'aud', 'exp', 'iat', 'sub', 'nonce'],
                },
            )
        except (jwt.PyJWTError, TypeError, ValueError, OverflowError) as exc:
            raise _reject(
                f'ID token validation failed ({type(exc).__name__}).',
            ) from None
        if claims['nonce'] != nonce:
            raise _reject('The ID token has the wrong nonce.')
        subject = claims['sub']
        if (
            not subject
            or len(subject) > 255
            or not subject.isascii()
            or '\x00' in subject
            or ('azp' in claims and claims['azp'] != self.client_id)
            or (
                isinstance(claims['aud'], list)
                and len(claims['aud']) > 1
                and claims.get('azp') != self.client_id
            )
        ):
            raise _reject('The ID token has an invalid subject or party.')
        return claims

    def exchange(
        self,
        code: str,
        state: str,
        browser_key: str,
    ) -> dict[str, Any]:
        """Consume the attempt and return verified claims."""
        attempt = self._consume(state, browser_key)
        metadata = self._metadata()
        methods = metadata.get(
            'token_endpoint_auth_methods_supported',
            [
                'client_secret_basic',
            ],
        )
        if not isinstance(methods, list):
            raise _reject(
                'The token authentication method list is invalid.',
            )
        data = {
            'grant_type': 'authorization_code',
            'code': code,
            'redirect_uri': self.redirect_uri,
            'code_verifier': attempt.verifier,
        }
        auth = None
        if 'client_secret_basic' in methods:
            auth = (quote_plus(self.client_id), quote_plus(self.client_secret))
        elif 'client_secret_post' in methods:
            data.update(
                client_id=self.client_id, client_secret=self.client_secret,
            )
        else:
            raise _reject(
                'The provider lists no supported client authentication.',
            )
        tokens = _json_request(
            'POST', metadata['token_endpoint'], endpoint='token endpoint',
            data=data, auth=auth,
        )
        claims = self._id_claims(
            tokens.get('id_token'), metadata['jwks_uri'], attempt.nonce,
        )
        userinfo = metadata.get('userinfo_endpoint')
        if userinfo and any(
            key not in claims for key in ('groups', 'email', 'email_verified')
        ):
            token = tokens.get('access_token')
            if isinstance(token, str) and token:
                profile = _json_request(
                    'GET',
                    userinfo,
                    endpoint='UserInfo endpoint',
                    headers={
                        'Authorization': f'Bearer {token}',
                    },
                )
                if profile.get('sub') != claims['sub']:
                    raise _reject(
                        'The UserInfo subject does not match the ID token.',
                    )
                claims.setdefault('groups', profile.get('groups'))
                if 'email' not in claims:
                    claims.update(
                        email=profile.get('email'),
                        email_verified=profile.get('email_verified'),
                    )
                elif claims['email'] == profile.get('email'):
                    claims.setdefault(
                        'email_verified', profile.get('email_verified'),
                    )
                for key in ('given_name', 'family_name'):
                    claims.setdefault(key, profile.get(key))
        groups = claims.get('groups')
        if not isinstance(groups, list) or any(
            not isinstance(name, str)
            or not name
            or len(name) > 255
            or name != name.strip()
            or '\x00' in name
            for name in groups
        ):
            raise OIDCError(
                _('The identity provider sent no valid group list.'),
                reason='The provider did not return a valid groups claim.',
            )
        return claims
