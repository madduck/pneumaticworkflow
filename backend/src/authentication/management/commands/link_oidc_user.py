from argparse import ArgumentParser
from typing import Any

from django.core.management.base import BaseCommand, CommandError
from django.db import IntegrityError, transaction

from src.accounts.enums import UserStatus, UserType
from src.accounts.models import User
from src.authentication.models import OIDCIdentity
from src.authentication.services.oidc import OIDCError, OIDCService


class Command(BaseCommand):
    help = 'Link an existing workspace user to a verified OIDC subject.'

    def add_arguments(self, parser: ArgumentParser) -> None:
        """Accept a Pneumatic user ID and an OIDC subject."""
        parser.add_argument('user_id', type=int)
        parser.add_argument('subject')

    def handle(self, *args: Any, **options: Any) -> None:
        """Create the identity link without replacing any existing link."""
        subject = options['subject']
        if (
            not 1 <= len(subject) <= 255
            or not subject.isascii()
            or '\x00' in subject
        ):
            raise CommandError(
                'The OIDC subject must contain 1 to 255 ASCII characters.',
            )
        try:
            service = OIDCService()
            with transaction.atomic():
                user = User.objects.select_for_update().get(
                    pk=options['user_id'],
                    account_id=service.account_id,
                    status=UserStatus.ACTIVE,
                    type=UserType.USER,
                )
                OIDCIdentity.objects.get_or_create(
                    user=user,
                    issuer=service.issuer,
                    subject=subject,
                )
        except OIDCError as exc:
            raise CommandError(exc.message) from None
        except User.DoesNotExist:
            raise CommandError(
                'The configured workspace has no active user with that ID.',
            ) from None
        except IntegrityError:
            raise CommandError(
                'The user or subject already has a different identity link.',
            ) from None
        self.stdout.write('Linked the Pneumatic user to the OIDC identity.')
