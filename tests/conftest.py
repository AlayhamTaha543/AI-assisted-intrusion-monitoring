import pytest
from django.contrib.auth.models import User, Group
from rest_framework.authtoken.models import Token


@pytest.fixture
def ingestor_user(db):
    user = User.objects.create_user('ingestor', 'i@test.com', 'pass')
    g, _ = Group.objects.get_or_create(name='ingestor')
    user.groups.add(g)
    Token.objects.create(user=user)
    return user


@pytest.fixture
def analyst_user(db):
    user = User.objects.create_user('analyst', 'a@test.com', 'pass')
    g, _ = Group.objects.get_or_create(name='analyst')
    user.groups.add(g)
    Token.objects.create(user=user)
    return user


@pytest.fixture
def ingestor_token(ingestor_user):
    return Token.objects.get(user=ingestor_user).key


@pytest.fixture
def analyst_token(analyst_user):
    return Token.objects.get(user=analyst_user).key
