import json
import uuid
from datetime import datetime, timedelta
from django.utils import timezone
from rest_framework.authtoken.models import Token


def test_normal_stores_no_incident(client, ingestor_token, db):
    now = timezone.now()
    events = [{
        'event_id': str(uuid.uuid4()),
        'timestamp': now.isoformat(),
        'source_ip': '198.51.100.10',
        'dest_ip': '192.168.1.10',
        'dest_port': 80,
        'protocol': 'tcp',
        'event_type': 'login_success',
        'username': 'alice',
        'bytes_sent': 100,
    }]
    resp = client.post('/api/events/', data=json.dumps(events), content_type='application/json', HTTP_AUTHORIZATION=f'Token {ingestor_token}')
    assert resp.status_code == 201
    from alerts.models import Alert
    assert Alert.objects.count() == 0


def _event(raw):
    import uuid
    from django.utils import timezone
    return {
        'event_id': str(uuid.uuid4()),
        'timestamp': timezone.now().isoformat(),
        'source_ip': '198.51.100.20',
        'dest_ip': '192.168.1.10',
        'dest_port': 80,
        'protocol': 'tcp',
        'event_type': 'connection',
        'bytes_sent': 10,
        'raw': raw,
    }


def test_raw_with_nul_rejected(client, ingestor_token, db):
    from events.models import LogEvent
    resp = client.post('/api/events/', data=json.dumps([_event({'k': 'a\x00b'})]),
                       content_type='application/json', HTTP_AUTHORIZATION=f'Token {ingestor_token}')
    assert resp.status_code == 400
    assert LogEvent.objects.count() == 0


def test_raw_with_nul_in_key_rejected(client, ingestor_token, db):
    from events.models import LogEvent
    resp = client.post('/api/events/', data=json.dumps([_event({'a\x00b': 'v'})]),
                       content_type='application/json', HTTP_AUTHORIZATION=f'Token {ingestor_token}')
    assert resp.status_code == 400
    assert LogEvent.objects.count() == 0


def test_raw_normal_object_accepted(client, ingestor_token, db):
    from events.models import LogEvent
    resp = client.post('/api/events/', data=json.dumps([_event({'k': 'v'})]),
                       content_type='application/json', HTTP_AUTHORIZATION=f'Token {ingestor_token}')
    assert resp.status_code == 201
    assert LogEvent.objects.count() == 1
