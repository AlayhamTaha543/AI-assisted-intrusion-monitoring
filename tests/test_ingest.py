import json
import uuid
from datetime import timedelta
from django.utils import timezone


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


def _valid(**overrides):
    from django.utils import timezone
    ev = {
        'event_id': str(uuid.uuid4()),
        'timestamp': timezone.now().isoformat(),
        'source_ip': '198.51.100.30',
        'dest_ip': '192.168.1.10',
        'dest_port': 80,
        'protocol': 'tcp',
        'event_type': 'connection',
        'bytes_sent': 10,
    }
    ev.update(overrides)
    return ev


def _post(client, token, events):
    return client.post('/api/events/', data=json.dumps(events),
                       content_type='application/json', HTTP_AUTHORIZATION=f'Token {token}')


def test_bytes_sent_overflow_400(client, ingestor_token, db):
    from events.models import LogEvent
    resp = _post(client, ingestor_token, [_valid(bytes_sent=2147483648)])
    assert resp.status_code == 400
    assert LogEvent.objects.count() == 0


def test_event_id_required_400(client, ingestor_token, db):
    from events.models import LogEvent
    ev = _valid()
    ev.pop('event_id')
    resp = _post(client, ingestor_token, [ev])
    assert resp.status_code == 400
    assert LogEvent.objects.count() == 0


def test_error_names_item_index(client, ingestor_token, db):
    resp = _post(client, ingestor_token, [_valid(), _valid(source_ip='not-an-ip'), _valid()])
    assert resp.status_code == 400
    assert resp.json()['errors'][0]['index'] == 1


def test_batch_too_large_400(client, ingestor_token, db):
    from events.models import LogEvent
    resp = _post(client, ingestor_token, [_valid() for _ in range(201)])
    assert resp.status_code == 400
    assert LogEvent.objects.count() == 0


def test_future_and_too_old_timestamp_400(client, ingestor_token, db):
    from events.models import LogEvent
    future = (timezone.now() + timedelta(minutes=10)).isoformat()
    old = (timezone.now() - timedelta(hours=25)).isoformat()
    assert _post(client, ingestor_token, [_valid(timestamp=future)]).status_code == 400
    assert _post(client, ingestor_token, [_valid(timestamp=old)]).status_code == 400
    assert LogEvent.objects.count() == 0


def test_duplicate_batch_inserts_zero(client, ingestor_token, db):
    from events.models import LogEvent
    events = [_valid(), _valid()]
    first = _post(client, ingestor_token, events)
    assert first.status_code == 201
    assert first.json()['inserted'] == 2
    second = _post(client, ingestor_token, events)
    assert second.status_code == 201
    assert second.json()['inserted'] == 0
    assert second.json()['duplicates'] == 2
    assert LogEvent.objects.count() == 2


def test_duplicate_race_returns_201(client, ingestor_token, db):
    from unittest.mock import MagicMock, patch
    from events.models import LogEvent
    events = [_valid(), _valid()]
    assert _post(client, ingestor_token, events).status_code == 201
    assert LogEvent.objects.count() == 2

    real_filter = LogEvent.objects.filter
    state = {'calls': 0}

    def fake_filter(*args, **kwargs):
        state['calls'] += 1
        if state['calls'] == 1:
            m = MagicMock()
            m.values_list.return_value = []
            return m
        return real_filter(*args, **kwargs)

    with patch.object(LogEvent.objects, 'filter', side_effect=fake_filter):
        resp = _post(client, ingestor_token, events)
    assert resp.status_code == 201
    ids = [e['event_id'] for e in events]
    assert LogEvent.objects.filter(event_id__in=ids).count() == 2
