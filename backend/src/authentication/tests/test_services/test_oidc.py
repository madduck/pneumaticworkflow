from collections.abc import Callable
from typing import Any
from urllib.parse import parse_qs, urlsplit

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from django.core.cache import cache
from django.utils import timezone

from src.authentication.models import OIDCLoginAttempt
from src.authentication.services.oidc import OIDCError, OIDCService

pytestmark = pytest.mark.django_db

ISSUER = 'https://sso.example.org/application/o/pneumatic/'
CALLBACK = 'https://workflows.example.org/oauth/oidc/callback/'
BROWSER_KEY = 'a' * 43


@pytest.fixture
def service(settings: Any) -> OIDCService:
    settings.PROJECT_CONF = {
        **settings.PROJECT_CONF,
        'SSO_AUTH': True,
        'SSO_PROVIDER': 'oidc',
    }
    settings.OIDC_ISSUER = ISSUER
    settings.OIDC_CLIENT_ID = 'pneumatic'
    settings.OIDC_CLIENT_SECRET = 'client-secret'
    settings.OIDC_REDIRECT_URI = CALLBACK
    settings.OIDC_ACCOUNT_ID = '123'
    cache.clear()
    return OIDCService()


@pytest.fixture
def fake_provider(mocker: Any) -> Callable[[dict[str, Any]], None]:
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    public_key = jwt.algorithms.RSAAlgorithm.to_jwk(
        key.public_key(), as_dict=True,
    )
    claims: dict[str, Any] = {}

    def request(method: str, url: str, **kwargs: Any) -> dict[str, Any]:
        if url == ISSUER + '.well-known/openid-configuration':
            return {
                'issuer': ISSUER,
                'authorization_endpoint': 'https://sso.example.org/authorize',
                'token_endpoint': 'https://sso.example.org/token',
                'jwks_uri': 'https://sso.example.org/jwks',
            }
        if url == 'https://sso.example.org/jwks':
            return {'keys': [{**public_key, 'kid': 'test'}]}
        assert method == 'POST'
        assert url == 'https://sso.example.org/token'
        assert kwargs['data']['redirect_uri'] == CALLBACK
        assert kwargs['data']['code_verifier'] == claims.pop('_verifier')
        return {
            'id_token': jwt.encode(
                claims, key, algorithm='RS256', headers={'kid': 'test'},
            ),
        }

    mocker.patch(
        'src.authentication.services.oidc._json_request', side_effect=request,
    )
    return claims.update


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


def test_callback_requires_same_browser_and_consumes_state(
    service: OIDCService,
    fake_provider: Callable[[dict[str, Any]], None],
) -> None:
    state = _start(service, fake_provider)
    with pytest.raises(OIDCError):
        service.exchange('code', state, 'b' * 43)

    assert service.exchange('code', state, BROWSER_KEY)['sub'] == 'subject'
    with pytest.raises(OIDCError):
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
