import logging

from drf_spectacular.utils import extend_schema
from rest_framework import serializers
from rest_framework.decorators import action
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.viewsets import GenericViewSet

from src.analysis.mixins import BaseIdentifyMixin
from src.generics.mixins.views import AnonymousMixin
from src.openapi.internal_serializers import AuthUriResponseSerializer
from src.openapi.serializers import AuthTokenResponseSerializer
from src.utils.validation import raise_validation_error

from ..permissions import SSOPermission  # noqa: TID252
from ..services.oidc import OIDCError, OIDCService  # noqa: TID252
from ..services.oidc_accounts import authenticate_oidc_user  # noqa: TID252
from ..throttling import SSOAuthUriThrottle, SSOTokenThrottle  # noqa: TID252

logger = logging.getLogger(__name__)


class OIDCStartSerializer(serializers.Serializer):
    browser_key = serializers.RegexField(r'\A[A-Za-z0-9_-]{43}\Z')


class OIDCExchangeSerializer(OIDCStartSerializer):
    state = serializers.RegexField(r'\A[A-Za-z0-9_-]{43}\Z')
    code = serializers.CharField(max_length=4096, trim_whitespace=False)


class OIDCViewSet(AnonymousMixin, BaseIdentifyMixin, GenericViewSet):
    """Start and finish the OpenID Connect flow from the frontend server."""

    authentication_classes = ()
    permission_classes = (SSOPermission,)

    @extend_schema(
        tags=['Auth'],
        auth=[],
        request=OIDCStartSerializer,
        responses=AuthUriResponseSerializer,
    )
    @action(
        methods=['post'],
        detail=False,
        url_path='auth-uri',
        throttle_classes=[SSOAuthUriThrottle],
    )
    def auth_uri(self, request: Request) -> Response:
        """Return the authorisation URL for this browser."""
        serializer = OIDCStartSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            uri = OIDCService().start(**serializer.validated_data)
        except OIDCError as exc:
            logger.warning('OIDC sign-in did not start: %s', exc.reason)
            raise_validation_error(message=exc.message)
        return Response(
            {'auth_uri': uri}, headers={'Cache-Control': 'no-store'},
        )

    @extend_schema(
        tags=['Auth'],
        auth=[],
        request=OIDCExchangeSerializer,
        responses=AuthTokenResponseSerializer,
    )
    @action(
        methods=['post'], detail=False, throttle_classes=[SSOTokenThrottle],
    )
    def token(self, request: Request) -> Response:
        """Complete sign-in and return a Pneumatic session token."""
        serializer = OIDCExchangeSerializer(data=request.data)
        try:
            serializer.is_valid(raise_exception=True)
        except serializers.ValidationError:
            logger.warning(
                'OIDC callback failed: Invalid callback fields: %s.',
                ', '.join(serializer.errors),
            )
            raise
        try:
            service = OIDCService()
            claims = service.exchange(**serializer.validated_data)
            user, token = authenticate_oidc_user(
                issuer=service.issuer,
                account_id=service.account_id,
                claims=claims,
                user_agent=self.get_user_agent(request),
                user_ip=self.get_user_ip(request),
            )
        except OIDCError as exc:
            logger.warning('OIDC callback failed: %s', exc.reason)
            raise_validation_error(message=exc.message)
        self.identify(user)
        return Response(
            {'token': token}, headers={'Cache-Control': 'no-store'},
        )
