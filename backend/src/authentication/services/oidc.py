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

from ..models import OIDCLoginAttempt  # noqa: TID252
from .exceptions import AuthException

_SCOPE = 'openid email profile groups'
_ATTEMPT_TTL = timedelta(minutes=10)


class OIDCError(AuthException):
    """An OIDC error that the application can show to users."""


def _reject() -> OIDCError:
    return OIDCError(_('OpenID Connect sign-in failed. Start a new sign-in.'))


def _https_url(value: Any) -> str:
    if not isinstance(value, str):
        raise _reject()
    try:
        url = urlsplit(value)
    except ValueError:
        raise _reject() from None
    if (
        url.scheme != 'https'
        or not url.hostname
        or url.fragment
        or url.username is not None
        or '\\' in value
    ):
        raise _reject()
    return value


def _json_request(method: str, url: str, **kwargs: Any) -> dict[str, Any]:
    try:
        response = requests.request(
            method,
            _https_url(url),
            timeout=5,
            allow_redirects=False,
            **kwargs,
        )
        if response.status_code != 200:
            raise _reject()
        data = response.json()
    except (requests.RequestException, ValueError):
        raise _reject() from None
    if not isinstance(data, dict):
        raise _reject()
    return data


class OIDCService:
    """Run the OpenID Connect authorisation code flow for one deployment."""

    def __init__(self) -> None:
        if (
            not settings.PROJECT_CONF['SSO_AUTH']
            or settings.PROJECT_CONF.get('SSO_PROVIDER') != 'oidc'
        ):
            raise OIDCError(_('OpenID Connect sign-in is disabled.'))
        self.issuer = _https_url(settings.OIDC_ISSUER)
        self.client_id = settings.OIDC_CLIENT_ID
        self.client_secret = settings.OIDC_CLIENT_SECRET
        self.redirect_uri = _https_url(settings.OIDC_REDIRECT_URI)
        try:
            self.account_id = int(settings.OIDC_ACCOUNT_ID)
        except (TypeError, ValueError):
            raise _reject() from None
        if (
            not self.client_id
            or not self.client_secret
            or self.account_id < 1
            or str(self.account_id) != str(settings.OIDC_ACCOUNT_ID)
            or len(self.issuer) > 512
            or urlsplit(self.issuer).query
        ):
            raise _reject()

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
            )
            if metadata.get('issuer') != self.issuer:
                raise _reject()
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
                'scope': _SCOPE,
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
            if not attempt or not secrets.compare_digest(
                attempt.browser_binding,
                self._binding(browser_key),
            ):
                raise _reject()
            attempt.delete()
            return attempt

    def _id_claims(
        self,
        id_token: Any,
        jwks_uri: str,
        nonce: str,
    ) -> dict[str, Any]:
        if not isinstance(id_token, str):
            raise _reject()
        try:
            header = jwt.get_unverified_header(id_token)
            if header.get('alg') != 'RS256':
                raise _reject()
            keys = _json_request('GET', jwks_uri).get('keys')
            if not isinstance(keys, list):
                raise _reject()
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
                raise _reject()
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
        except (jwt.PyJWTError, TypeError, ValueError, OverflowError):
            raise _reject() from None
        subject = claims['sub']
        if (
            claims['nonce'] != nonce
            or not subject
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
            raise _reject()
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
            raise _reject()
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
            raise _reject()
        tokens = _json_request(
            'POST', metadata['token_endpoint'], data=data, auth=auth,
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
                    headers={
                        'Authorization': f'Bearer {token}',
                    },
                )
                if profile.get('sub') != claims['sub']:
                    raise _reject()
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
            )
        return claims
