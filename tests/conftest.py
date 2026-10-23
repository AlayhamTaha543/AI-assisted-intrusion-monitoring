import json
import uuid
from datetime import timedelta

import pytest
from django.contrib.auth.models import User, Group
from django.utils import timezone
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


def make_events(ip, event_type, n, start=None, protocol='ssh', dest_port=22):
    if start is None:
        start = timezone.now()
    events = []
    for i in range(n):
        events.append({
            'event_id': str(uuid.uuid4()),
            'timestamp': (start - timedelta(seconds=n - i)).isoformat(),
            'source_ip': ip,
            'dest_ip': '192.168.1.100',
            'dest_port': dest_port if event_type == 'connection' else dest_port,
            'protocol': protocol if event_type == 'connection' else protocol,
            'event_type': event_type,
            'username': f'user{i % 8}' if event_type in ['login_failed', 'login_success'] else None,
            'bytes_sent': 50,
        })
    return events


def post_events(client, token, events):
    return client.post('/api/events/', data=json.dumps(events), content_type='application/json', HTTP_AUTHORIZATION=f'Token {token}')
