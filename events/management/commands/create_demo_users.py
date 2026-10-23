from django.core.management.base import BaseCommand
from django.contrib.auth.models import User, Group, Permission
from rest_framework.authtoken.models import Token
import os
import secrets


class Command(BaseCommand):
    help = 'Create demo users'

    def handle(self, *args, **options):
        ingestor_g, _ = Group.objects.get_or_create(name='ingestor')
        analyst_g, _ = Group.objects.get_or_create(name='analyst')
        try:
            perm = Permission.objects.get(codename='view_alert')
            analyst_g.permissions.add(perm)
        except Exception:
            pass

        demo_pass = os.environ.get('DEMO_USER_PASSWORD') or ''

        u1, created = User.objects.get_or_create(username='ingestor1')
        if created or not demo_pass:
            if not demo_pass:
                demo_pass = secrets.token_urlsafe(12)
            u1.set_password(demo_pass)
            u1.save()
        else:
            u1.set_password(demo_pass)
            u1.save()
        u1.groups.add(ingestor_g)
        token1, _ = Token.objects.get_or_create(user=u1)
        self.stdout.write(f'INGEST_TOKEN={token1.key}')

        u2, created2 = User.objects.get_or_create(username='analyst1')
        if created2 or not os.environ.get('DEMO_USER_PASSWORD'):
            if not os.environ.get('DEMO_USER_PASSWORD'):
                p2 = secrets.token_urlsafe(12)
            else:
                p2 = os.environ.get('DEMO_USER_PASSWORD')
            u2.set_password(p2)
            u2.save()
            self.stdout.write(f'ANALYST_PASSWORD={p2}')
        else:
            u2.set_password(os.environ.get('DEMO_USER_PASSWORD'))
            u2.save()
        u2.is_staff = True
        u2.save()
        u2.groups.add(analyst_g)
        token2, _ = Token.objects.get_or_create(user=u2)
        self.stdout.write(f'ANALYST_TOKEN={token2.key}')
