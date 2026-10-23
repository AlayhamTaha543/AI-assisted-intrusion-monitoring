import os
import secrets

from django.contrib.auth.models import Group, Permission, User
from django.core.management.base import BaseCommand
from rest_framework.authtoken.models import Token


class Command(BaseCommand):
    help = 'Create demo users'

    def _ensure_user(self, username, group, is_staff, password_label):
        env_password = os.environ.get('DEMO_USER_PASSWORD') or ''
        user, created = User.objects.get_or_create(username=username)
        if created or env_password:
            password = env_password or secrets.token_urlsafe(12)
            user.set_password(password)
            self.stdout.write(f'{password_label}={password}')
        else:
            self.stdout.write(f'{password_label}=(unchanged)')
        if is_staff:
            user.is_staff = True
        user.save()
        user.groups.add(group)
        token, _ = Token.objects.get_or_create(user=user)
        return user, token

    def handle(self, *args, **options):
        ingestor_g, _ = Group.objects.get_or_create(name='ingestor')
        analyst_g, _ = Group.objects.get_or_create(name='analyst')
        try:
            analyst_g.permissions.add(Permission.objects.get(codename='view_alert'))
        except Permission.DoesNotExist:
            pass

        _, ingest_token = self._ensure_user('ingestor1', ingestor_g, False, 'INGEST_PASSWORD')
        self.stdout.write(f'INGEST_TOKEN={ingest_token.key}')

        _, analyst_token = self._ensure_user('analyst1', analyst_g, True, 'ANALYST_PASSWORD')
        self.stdout.write(f'ANALYST_TOKEN={analyst_token.key}')
