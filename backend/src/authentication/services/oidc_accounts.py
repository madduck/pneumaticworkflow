from typing import Any

from django.conf import settings
from django.contrib.auth.hashers import make_password
from django.core.exceptions import ValidationError
from django.core.validators import validate_email
from django.db import IntegrityError, transaction
from django.db.models import Q
from django.utils.translation import gettext as _

from src.accounts.enums import (
    UserGroupType,
    UserInviteStatus,
    UserStatus,
    UserType,
)
from src.accounts.models import Account, User, UserGroup, UserInvite
from src.accounts.services.account import AccountService
from src.accounts.services.exceptions import AlreadyRegisteredException
from src.accounts.services.group import UserGroupService
from src.accounts.services.user import UserService
from src.accounts.services.user_invite import UserInviteService
from src.analysis.services import AnalyticService
from src.logs.events import AuditEventService

from ..enums import AuthTokenType  # noqa: TID252
from ..models import OIDCIdentity  # noqa: TID252
from .oidc import OIDCError
from .user_auth import AuthService


def _no_user() -> OIDCError:
    return OIDCError(_('This identity cannot sign in to this workspace.'))


def _verified_email(claims: dict[str, Any]) -> str:
    email = claims.get('email')
    if claims.get('email_verified') is not True or not isinstance(email, str):
        raise _no_user()
    try:
        validate_email(email)
    except ValidationError:
        raise _no_user() from None
    if len(email) > 254:
        raise _no_user()
    return email.lower()


def _resolve_user(
    account: Account,
    issuer: str,
    claims: dict[str, Any],
) -> tuple[OIDCIdentity, bool]:
    link = OIDCIdentity.objects.filter(
        issuer=issuer, subject=claims['sub'],
    ).first()
    if link:
        try:
            link.user = User.include_inactive.select_for_update().get(
                pk=link.user_id,
                account=account,
                type=UserType.USER,
                status=UserStatus.ACTIVE,
            )
        except User.DoesNotExist:
            raise _no_user() from None
        return link, False

    email = _verified_email(claims)
    users = list(
        User.include_inactive.type_user()
        .select_for_update()
        .filter(email=email),
    )
    invited = [
        user
        for user in users
        if user.account_id == account.id and user.status == UserStatus.INVITED
    ]
    if (
        any(user.status != UserStatus.INVITED for user in users)
        or len(invited) > 1
    ):
        raise _no_user()
    first_name = claims.get('given_name')
    first_name = (
        first_name.replace('\x00', '')[:150]
        if isinstance(first_name, str)
        else ''
    )
    last_name = claims.get('family_name')
    last_name = (
        last_name.replace('\x00', '')[:150]
        if isinstance(last_name, str)
        else ''
    )
    if invited:
        user = invited[0]
        if OIDCIdentity.objects.filter(user=user).exists():
            raise _no_user()
        try:
            invite = UserInvite.objects.get(
                invited_user=user,
                account=account,
                status=UserInviteStatus.PENDING,
            )
        except UserInvite.DoesNotExist:
            raise _no_user() from None
        service = UserInviteService(
            request_user=user,
            current_url='',
            auth_type=AuthTokenType.USER,
            send_email=False,
        )
        user = service.accept(
            invite=invite,
            first_name=first_name or user.first_name,
            last_name=last_name or user.last_name,
        )
    elif users or not settings.OIDC_AUTO_CREATE_USERS:
        raise _no_user()
    else:
        user = UserService(account=account).create(
            account=account,
            email=email,
            first_name=first_name or email.split('@')[0][:150],
            last_name=last_name,
            password=make_password(None),
            is_admin=False,
        )
        AccountService(instance=account, user=user).update_users_counts()
    return OIDCIdentity.objects.create(
        user=user,
        issuer=issuer,
        subject=claims['sub'],
    ), not invited


def _sync_groups(link: OIDCIdentity, names: set[str]) -> None:
    user = link.user
    desired_ids = set()
    for name in sorted(names):
        group = UserGroup.include_personal.filter(
            name=name,
            account_id=user.account_id,
        ).first()
        if group and group.type != UserGroupType.REGULAR:
            raise OIDCError(
                _('An identity provider group uses a reserved name.'),
            )
        if not group:
            group = UserGroupService(user=user).create(name=name)
        desired_ids.add(group.pk)
    managed_ids = set(link.managed_groups.values_list('pk', flat=True))
    groups = (
        UserGroup.objects.select_for_update()
        .filter(
            Q(pk__in=desired_ids) | Q(pk__in=managed_ids),
            account_id=user.account_id,
        )
        .order_by('pk')
    )
    for group in groups:
        member_ids = set(group.users.values_list('pk', flat=True))
        desired = group.pk in desired_ids
        if desired == (user.pk in member_ids):
            continue
        if desired:
            member_ids.add(user.pk)
            link.managed_groups.add(group)
        else:
            member_ids.remove(user.pk)
        UserGroupService(user=user, instance=group).partial_update(
            users=sorted(member_ids),
        )
    link.managed_groups.remove(*(managed_ids - desired_ids))


def _sync_admin(link: OIDCIdentity, names: set[str]) -> None:
    user = link.user
    if user.is_account_owner:
        return
    group = settings.OIDC_ADMIN_GROUP
    if not group and not link.admin_granted:
        return
    grant = bool(group and group in names)
    if user.is_admin != grant:
        user.is_admin = grant
        user.save(update_fields=['is_admin'])
        AuditEventService.user_admin_toggled(
            user=None,
            auth_type=AuthTokenType.USER,
            target=user,
        )
    if link.admin_granted != grant:
        link.admin_granted = grant
        link.save(update_fields=['admin_granted'])


def authenticate_oidc_user(
    *,
    issuer: str,
    account_id: int,
    claims: dict[str, Any],
    user_agent: str | None,
    user_ip: str | None,
) -> tuple[User, str]:
    """Reconcile verified OIDC grants and issue a normal Pneumatic session."""
    try:
        with transaction.atomic():
            # Serialize first sign-ins and group creation within the workspace.
            account = Account.objects.select_for_update().get(pk=account_id)
            link, created = _resolve_user(account, issuer, claims)
            names = set(claims['groups'])
            _sync_groups(link, names)
            _sync_admin(link, names)
    except (Account.DoesNotExist, AlreadyRegisteredException, IntegrityError):
        raise _no_user() from None
    user = link.user
    token = AuthService.get_auth_token(
        user=user, user_agent=user_agent, user_ip=user_ip,
    )
    AnalyticService.users_logged_in(
        user=user,
        is_superuser=False,
        auth_type=AuthTokenType.USER,
        source='oidc',
    )
    if created:
        AuditEventService.user_signed_up(user=user, source='oidc')
    else:
        AuditEventService.user_logged_in(user=user, source='oidc')
    return user, token
