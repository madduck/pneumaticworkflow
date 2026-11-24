from collections.abc import Callable
from typing import Any
from urllib.parse import parse_qs, urlsplit

import jwt
import pytest
from _pytest.logging import LogCaptureFixture
from cryptography.hazmat.primitives.asymmetric import rsa
from django.core.cache import cache
from django.urls import reverse
from django.utils import timezone
from requests import Response
from rest_framework import status
from rest_framework.test import APIClient

from src.accounts.models import Account
from src.authentication.models import OIDCLoginAttempt
from src.authentication.services.oidc import OIDCError, OIDCService

pytestmark = pytest.mark.django_db

ISSUER = 'https://sso.example.org/application/o/pneumatic/'
CALLBACK = 'https://workflows.example.org/oauth/oidc/callback/'
BROWSER_KEY = 'a' * 43


@pytest.fixture
def oidc_settings(settings: Any) -> Any:
    settings.PROJECT_CONF = {
        **settings.PROJECT_CONF,
        'SSO_AUTH': True,
        'SSO_PROVIDER': 'oidc',
    }
    settings.OIDC_ISSUER = ISSUER
    settings.OIDC_CLIENT_ID = 'pneumatic'
    settings.OIDC_CLIENT_SECRET = 'client-secret'
    settings.OIDC_REDIRECT_URI = CALLBACK
    settings.OIDC_ACCOUNT_ID = ''
    cache.clear()
    return settings


@pytest.fixture
def service(oidc_settings: Any) -> OIDCService:
    oidc_settings.OIDC_ACCOUNT_ID = '123'
    return OIDCService()


def test_oidc_uses_the_only_workspace(oidc_settings: Any) -> None:
    workspace = Account.objects.create()

    assert OIDCService().account_id == workspace.pk


def test_oidc_requires_a_workspace(oidc_settings: Any) -> None:
    with pytest.raises(OIDCError, match='Create a workspace'):
        OIDCService()


def test_oidc_requires_an_explicit_id_with_multiple_workspaces(
    oidc_settings: Any,
) -> None:
    Account.objects.create()
    selected = Account.objects.create()

    with pytest.raises(OIDCError, match='Set OIDC_ACCOUNT_ID'):
        OIDCService()

    oidc_settings.OIDC_ACCOUNT_ID = str(selected.pk)
    assert OIDCService().account_id == selected.pk


def test_oidc_does_not_infer_a_workspace_for_an_invalid_id(
    oidc_settings: Any,
) -> None:
    Account.objects.create()
    oidc_settings.OIDC_ACCOUNT_ID = '0'

    with pytest.raises(OIDCError):
        OIDCService()


@pytest.fixture
def provider_profile() -> dict[str, Any]:
    """Return the claims to serve from UserInfo when enabled."""
    return {}


@pytest.fixture
def fake_provider(
    mocker: Any, provider_profile: dict[str, Any],
) -> Callable[[dict[str, Any]], None]:
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    public_key = jwt.algorithms.RSAAlgorithm.to_jwk(
        key.public_key(), as_dict=True,
    )
    claims: dict[str, Any] = {}

    def request(method: str, url: str, **kwargs: Any) -> dict[str, Any]:
        if url == ISSUER + '.well-known/openid-configuration':
            metadata = {
                'issuer': ISSUER,
                'authorization_endpoint': 'https://sso.example.org/authorize',
                'token_endpoint': 'https://sso.example.org/token',
                'jwks_uri': 'https://sso.example.org/jwks',
            }
            if provider_profile:
                metadata['userinfo_endpoint'] = 'https://sso.example.org/me'
            return metadata
        if url == 'https://sso.example.org/jwks':
            return {'keys': [{**public_key, 'kid': 'test'}]}
        if url == 'https://sso.example.org/me':
            assert method == 'GET'
            assert kwargs['headers'] == {'Authorization': 'Bearer test-token'}
            return provider_profile
        assert method == 'POST'
        assert url == 'https://sso.example.org/token'
        assert kwargs['data']['redirect_uri'] == CALLBACK
        assert kwargs['data']['code_verifier'] == claims.pop('_verifier')
        return {
            'access_token': 'test-token',
            'id_token': jwt.encode(
                claims, key, algorithm='RS256', headers={'kid': 'test'},
            ),
        }

    mocker.patch(
        'src.authentication.services.oidc._json_request', side_effect=request,
    )
    return claims.update


def test_start_uses_configured_scopes(
    oidc_settings: Any,
    fake_provider: Callable[[dict[str, Any]], None],
) -> None:
    """Send the configured scopes instead of the defaults."""
    oidc_settings.OIDC_ACCOUNT_ID = '123'
    oidc_settings.OIDC_SCOPES = 'openid email roles'

    url = OIDCService().start(BROWSER_KEY)

    assert parse_qs(urlsplit(url).query)['scope'] == ['openid email roles']


def _start(
    service: OIDCService, set_claims: Callable[[dict[str, Any]], None],
) -> str:
    url = service.start(BROWSER_KEY)
    params = parse_qs(urlsplit(url).query)
    assert params['scope'] == ['openid email profile groups']
    assert params['code_challenge_method'] == ['S256']
    state = params['state'][0]
    now = int(timezone.now().timestamp())
    set_claims(
        {
            'iss': ISSUER,
            'sub': 'subject',
            'aud': 'pneumatic',
            'iat': now,
            'exp': now + 60,
            'nonce': params['nonce'][0],
            'groups': ['operations'],
            '_verifier': OIDCLoginAttempt.objects.get(pk=state).verifier,
        },
    )
    return state


def test_callback_logs_provider_status_without_logging_credentials(
    service: OIDCService,
    api_client: APIClient,
    caplog: LogCaptureFixture,
    mocker: Any,
) -> None:
    mocker.patch.object(
        OIDCService,
        '_metadata',
        return_value={
            'authorization_endpoint': 'https://sso.example.org/authorize',
            'token_endpoint': 'https://sso.example.org/token',
        },
    )
    url = service.start(BROWSER_KEY)
    state = parse_qs(urlsplit(url).query)['state'][0]
    code = 'test-authorization-code'
    response = Response()
    response.status_code = 401
    mocker.patch(
        'src.authentication.services.oidc.requests.request',
        return_value=response,
    )

    result = api_client.post(
        reverse('auth:oidc-token'),
        {'browser_key': BROWSER_KEY, 'state': state, 'code': code},
        format='json',
    )

    assert result.status_code == status.HTTP_400_BAD_REQUEST
    assert 'The token endpoint returned HTTP 401.' in caplog.text
    assert result.data['message'] == (
        'OpenID Connect sign-in failed. Start a new sign-in.'
    )
    for secret in (BROWSER_KEY, state, code, service.client_secret):
        assert secret not in caplog.text


def test_callback_requires_same_browser_and_consumes_state(
    service: OIDCService,
    fake_provider: Callable[[dict[str, Any]], None],
) -> None:
    state = _start(service, fake_provider)
    with pytest.raises(OIDCError) as wrong_browser:
        service.exchange('code', state, 'b' * 43)
    assert 'does not match this browser' in wrong_browser.value.reason

    claims = service.exchange('code', state, BROWSER_KEY)
    assert claims['sub'] == 'subject'
    assert claims['groups'] == ['operations']
    with pytest.raises(OIDCError) as consumed:
        service.exchange('code', state, BROWSER_KEY)
    assert 'missing or expired' in consumed.value.reason


@pytest.mark.parametrize('source', ['id_token', 'userinfo'])
def test_callback_uses_configured_groups_claim(
    service: OIDCService,
    oidc_settings: Any,
    fake_provider: Callable[[dict[str, Any]], None],
    provider_profile: dict[str, Any],
    source: str,
) -> None:
    """Use the named claim and prefer the token over UserInfo."""
    oidc_settings.OIDC_GROUPS_CLAIM = 'roles'
    provider_profile.update(sub='subject', roles=['from-userinfo'])
    state = _start(service, fake_provider)
    if source == 'id_token':
        fake_provider({'roles': ['from-id-token']})
        expected = ['from-id-token']
    else:
        # Make the missing roles claim the only reason to fetch UserInfo.
        fake_provider({'email': 'user@example.org', 'email_verified': True})
        expected = ['from-userinfo']

    claims = service.exchange('code', state, BROWSER_KEY)

    assert claims['groups'] == expected


@pytest.mark.parametrize('overrides', [{}, {'roles': 'not-a-list'}])
def test_callback_rejects_missing_or_invalid_configured_groups_claim(
    service: OIDCService,
    oidc_settings: Any,
    fake_provider: Callable[[dict[str, Any]], None],
    overrides: dict[str, Any],
) -> None:
    """Reject an unusable configured claim even when groups is valid."""
    oidc_settings.OIDC_GROUPS_CLAIM = 'roles'
    state = _start(service, fake_provider)
    fake_provider(overrides)

    with pytest.raises(OIDCError, match='no valid group list'):
        service.exchange('code', state, BROWSER_KEY)


@pytest.mark.parametrize(
    'claim',
    [
        {'iss': 'https://other.example.org/'},
        {'aud': 'wrong-client'},
        {'nonce': 'wrong-nonce'},
        {'exp': 1},
        {'groups': 'not-a-list'},
        {'groups': None},
    ],
)
def test_callback_rejects_invalid_claims(
    service: OIDCService,
    fake_provider: Callable[[dict[str, Any]], None],
    claim: dict[str, Any],
) -> None:
    state = _start(service, fake_provider)
    fake_provider(claim)
    with pytest.raises(OIDCError):
        service.exchange('code', state, BROWSER_KEY)
    assert not OIDCLoginAttempt.objects.filter(pk=state).exists()
