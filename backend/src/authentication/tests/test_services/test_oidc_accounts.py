from typing import Any

import pytest
from rest_framework.exceptions import PermissionDenied

from src.accounts.models import Account, User, UserGroup
from src.accounts.services.user import UserService
from src.authentication.models import OIDCIdentity
from src.authentication.services.oidc import OIDCError
from src.authentication.services.oidc_accounts import authenticate_oidc_user
from src.processes.tests.fixtures import (
    create_invited_user,
    create_test_account,
    create_test_not_admin,
    create_test_owner,
)

pytestmark = pytest.mark.django_db
ISSUER = 'https://sso.example.org/application/o/pneumatic/'
EMAIL = 'member@example.org'


@pytest.fixture
def workspace(settings: Any) -> Account:
    account = create_test_account()
    create_test_owner(account=account)
    settings.OIDC_ISSUER = ISSUER
    settings.OIDC_ACCOUNT_ID = str(account.pk)
    settings.OIDC_AUTO_CREATE_USERS = False
    settings.OIDC_ADMIN_GROUP = ''
    settings.PROJECT_CONF = {
        **settings.PROJECT_CONF,
        'SSO_AUTH': True,
        'SSO_PROVIDER': 'oidc',
    }
    return account


def _login(workspace: Account, **overrides: Any) -> User:
    user, token = authenticate_oidc_user(
        issuer=ISSUER,
        account_id=workspace.pk,
        claims={
            'sub': 'subject',
            'email': EMAIL,
            'email_verified': True,
            'groups': [],
            **overrides,
        },
        user_agent='test',
        user_ip=None,
    )
    assert token
    return user


def test_auto_creation_disabled_by_default(workspace: Account) -> None:
    with pytest.raises(OIDCError):
        _login(workspace, groups=['operations'])
    assert not User.objects.filter(email=EMAIL).exists()
    assert not UserGroup.objects.filter(
        account=workspace, name='operations',
    ).exists()


def test_provisioning_creates_one_member_without_password(
    workspace: Account,
    settings: Any,
) -> None:
    settings.OIDC_AUTO_CREATE_USERS = True
    user = _login(workspace)
    assert not user.is_admin
    assert not user.has_usable_password()
    assert _login(workspace, email='changed@example.org') == user
    assert User.objects.filter(email=EMAIL).count() == 1


def test_existing_email_is_not_linked_by_auto_creation(
    workspace: Account,
    settings: Any,
) -> None:
    settings.OIDC_AUTO_CREATE_USERS = True
    create_test_not_admin(account=workspace, email=EMAIL)
    with pytest.raises(OIDCError):
        _login(workspace)
    assert not OIDCIdentity.objects.filter(issuer=ISSUER).exists()


def test_unverified_email_does_not_provision(
    workspace: Account, settings: Any,
) -> None:
    settings.OIDC_AUTO_CREATE_USERS = True
    with pytest.raises(OIDCError):
        _login(workspace, email_verified='true')
    assert not User.objects.filter(email=EMAIL).exists()


def test_pending_invitation_is_accepted_without_auto_creation(
    workspace: Account,
) -> None:
    invited = create_invited_user(user=workspace.get_owner(), email=EMAIL)
    assert _login(workspace) == invited
    invited.refresh_from_db()
    assert invited.is_active


@pytest.mark.parametrize('infer_workspace', [False, True])
def test_sync_reuses_and_creates_groups_and_revokes_admin(
    workspace: Account,
    settings: Any,
    infer_workspace: bool,
) -> None:
    if infer_workspace:
        settings.OIDC_ACCOUNT_ID = ''
    settings.OIDC_ADMIN_GROUP = 'administrators'
    user = create_test_not_admin(account=workspace, email=EMAIL)
    OIDCIdentity.objects.create(issuer=ISSUER, subject='subject', user=user)
    existing = UserGroup.objects.create(account=workspace, name='operations')
    manual = UserGroup.objects.create(account=workspace, name='local')
    manual.users.add(user)

    assert _login(
        workspace, groups=['operations', 'administrators', 'local'],
    ).is_admin
    assert existing.users.filter(pk=user.pk).exists()
    assert UserGroup.objects.filter(
        account=workspace, name='administrators', users=user,
    ).exists()
    with pytest.raises(PermissionDenied):
        UserService(instance=user, user=workspace.get_owner()).toggle_admin()

    assert not _login(workspace).is_admin
    assert set(user.user_groups.values_list('name', flat=True)) == {'local'}
    assert (
        UserGroup.objects.filter(
            account=workspace, name='administrators',
        ).count()
        == 1
    )


def test_oidc_admin_rule_does_not_demote_owner(
    workspace: Account, settings: Any,
) -> None:
    settings.OIDC_ADMIN_GROUP = 'administrators'
    owner = workspace.get_owner()
    OIDCIdentity.objects.create(issuer=ISSUER, subject='subject', user=owner)
    assert _login(workspace).is_admin
