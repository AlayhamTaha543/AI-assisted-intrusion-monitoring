from django.core.management.base import BaseCommand
from django.contrib.auth.models import User, Group
from rest_framework.authtoken.models import Token


class Command(BaseCommand):
    help = 'Create demo users'

    def handle(self, *args, **options):
        ingestor_g, _ = Group.objects.get_or_create(name='ingestor')
        analyst_g, _ = Group.objects.get_or_create(name='analyst')
        u1, _ = User.objects.get_or_create(username='ingestor1')
        u1.set_password('pass')
        u1.save()
        u1.groups.add(ingestor_g)
        Token.objects.get_or_create(user=u1)
        u2, _ = User.objects.get_or_create(username='analyst1')
        u2.set_password('pass')
        u2.is_staff = True
        u2.save()
        u2.groups.add(analyst_g)
        Token.objects.get_or_create(user=u2)
        self.stdout.write(self.style.SUCCESS('Demo users created'))
