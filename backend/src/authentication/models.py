from datetime import timedelta

from django.contrib.auth import get_user_model
from django.db import models
from django.utils import timezone

from src.accounts.enums import SourceType
from src.accounts.models import Account
from src.authentication.enums import SSOProvider
from src.generics.models import SoftDeleteModel

UserModel = get_user_model()


class AccessToken(SoftDeleteModel):

    class Meta:
        ordering = ('id',)
        constraints = [
            models.UniqueConstraint(
                fields=['user_id', 'source'],
                condition=(models.Q(is_deleted=False)),
                name='auth_access_token_user_unique',
            ),
        ]

    access_token = models.CharField(max_length=3000)
    refresh_token = models.CharField(max_length=3000)
    expires_in = models.PositiveIntegerField(
        help_text='Seconds before expiration access_token')
    user = models.ForeignKey(
        UserModel,
        on_delete=models.CASCADE,
        related_name='access_tokens',
    )
    source = models.CharField(
        max_length=255,
        choices=SourceType.CHOICES,
    )
    date_updated = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f'{self.user.name} ({self.source})'

    @property
    def is_expired(self) -> bool:
        now = timezone.now()
        exp_date = self.date_updated + timedelta(seconds=self.expires_in - 30)
        return now > exp_date


class SSOConfig(models.Model):

    class Meta:
        unique_together = ('account', 'provider')
        ordering = ['account', 'provider']
        constraints = [
            models.UniqueConstraint(
                fields=['account'],
                condition=models.Q(is_active=True),
                name='unique_active_sso_per_account',
            ),
        ]

    account = models.ForeignKey(
        Account,
        on_delete=models.CASCADE,
        related_name='sso_configurations',
    )
    provider = models.CharField(
        max_length=50,
        choices=SSOProvider.CHOICES,
    )
    domain = models.CharField(max_length=255)
    client_id = models.CharField(max_length=255)
    client_secret = models.CharField(max_length=255)
    is_active = models.BooleanField(default=False)

    def __str__(self):
        return f'{self.account.name} - {self.provider}'


class OIDCIdentity(models.Model):
    user = models.OneToOneField(
        UserModel,
        on_delete=models.CASCADE,
        related_name='oidc_identity',
    )
    issuer = models.CharField(max_length=512)
    subject = models.CharField(max_length=255)
    managed_groups = models.ManyToManyField('accounts.UserGroup', blank=True)
    admin_granted = models.BooleanField(default=False)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=['issuer', 'subject'],
                name='oidc_identity_issuer_subject_unique',
            ),
        ]


    def __str__(self) -> str:
        """Describe the link without exposing the provider subject."""
        return f'OIDC identity for user {self.user_id}'


class OIDCLoginAttempt(models.Model):
    state = models.CharField(primary_key=True, max_length=43)
    browser_binding = models.CharField(max_length=64)
    nonce = models.CharField(max_length=43)
    verifier = models.CharField(max_length=43)
    expires_at = models.DateTimeField(db_index=True)

    def __str__(self) -> str:
        """Describe the attempt without exposing the flow values."""
        return f'OIDC sign-in attempt expiring at {self.expires_at}'
