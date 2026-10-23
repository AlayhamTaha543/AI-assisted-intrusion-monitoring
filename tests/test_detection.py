import json
import uuid
from datetime import datetime, timedelta

import pytest
from django.utils import timezone

from tests.conftest import post_events


def test_brute_force_creates_incident(client, ingestor_token, db):
    from alerts.models import Alert
    now = timezone.now()
    events = []
    ip = '203.0.113.45'
    for i in range(25):
        events.append({
            'event_id': str(uuid.uuid4()),
            'timestamp': (now - timedelta(seconds=40 - i)).isoformat(),
            'source_ip': ip,
            'dest_ip': '192.168.1.100',
            'dest_port': 22,
            'protocol': 'ssh',
            'event_type': 'login_failed',
            'username': f'user{i%8}',
            'bytes_sent': 50,
        })
    resp = client.post('/api/events/', data=json.dumps(events), content_type='application/json', HTTP_AUTHORIZATION=f'Token {ingestor_token}')
    assert resp.status_code == 201
    assert Alert.objects.filter(rule_name='brute_force', source_ip=ip).count() >= 1
    alert = Alert.objects.filter(rule_name='brute_force', source_ip=ip).first()
    assert alert.severity == 'high'


def _logins(ip, n, start, usernames=3):
    events = []
    for i in range(n):
        events.append({
            'event_id': str(uuid.uuid4()),
            'timestamp': (start + timedelta(seconds=i)).isoformat(),
            'source_ip': ip,
            'dest_ip': '192.168.1.100',
            'dest_port': 22,
            'protocol': 'ssh',
            'event_type': 'login_failed',
            'username': f'user{i % usernames}',
            'bytes_sent': 50,
        })
    return events


def _connections(ip, ports, start):
    events = []
    for i, port in enumerate(ports):
        events.append({
            'event_id': str(uuid.uuid4()),
            'timestamp': (start + timedelta(seconds=i)).isoformat(),
            'source_ip': ip,
            'dest_ip': '192.168.1.200',
            'dest_port': port,
            'protocol': 'tcp',
            'event_type': 'connection',
            'bytes_sent': 40,
        })
    return events


@pytest.mark.parametrize('count,expect', [(19, False), (20, True)])
def test_exact_brute_force_threshold(client, ingestor_token, db, count, expect):
    from alerts.models import Alert
    start = timezone.now() - timedelta(seconds=50)
    resp = post_events(client, ingestor_token, _logins('10.9.0.1', count, start))
    assert resp.status_code == 201
    assert Alert.objects.filter(rule_name='brute_force').exists() is expect


@pytest.mark.parametrize('count,expect', [(14, False), (15, True)])
def test_exact_port_scan_threshold(client, ingestor_token, db, count, expect):
    from alerts.models import Alert
    start = timezone.now() - timedelta(seconds=50)
    ports = [1000 + i for i in range(count)]
    resp = post_events(client, ingestor_token, _connections('10.9.0.2', ports, start))
    assert resp.status_code == 201
    assert Alert.objects.filter(rule_name='port_scan').exists() is expect


def test_sliding_window_crosses_minute_boundary(client, ingestor_token, db):
    from alerts.models import Alert
    latest = (timezone.now() - timedelta(minutes=5)).replace(second=5, microsecond=0)
    earlier = latest - timedelta(seconds=15)
    events = _logins('10.9.1.1', 12, earlier) + _logins('10.9.1.1', 12, latest)
    resp = post_events(client, ingestor_token, events)
    assert resp.status_code == 201
    alert = Alert.objects.get(rule_name='brute_force', source_ip='10.9.1.1')
    assert alert.evidence['failed_logins'] == 24


def test_events_70s_apart_do_not_combine(client, ingestor_token, db):
    from alerts.models import Alert
    latest = timezone.now() - timedelta(seconds=10)
    earlier = latest - timedelta(seconds=70)
    events = _logins('10.9.1.2', 12, earlier) + _logins('10.9.1.2', 12, latest)
    resp = post_events(client, ingestor_token, events)
    assert resp.status_code == 201
    assert not Alert.objects.filter(source_ip='10.9.1.2').exists()


def test_same_port_20_times_not_scan(client, ingestor_token, db):
    from alerts.models import Alert
    start = timezone.now() - timedelta(seconds=30)
    events = _connections('10.9.2.1', [1000] * 20, start)
    resp = post_events(client, ingestor_token, events)
    assert resp.status_code == 201
    assert not Alert.objects.filter(rule_name='port_scan').exists()


def test_split_batches_detected(client, ingestor_token, db):
    from alerts.models import Alert
    now = timezone.now()
    first = _logins('10.9.3.1', 12, now - timedelta(seconds=50))
    second = _logins('10.9.3.1', 12, now - timedelta(seconds=30))
    assert post_events(client, ingestor_token, first).status_code == 201
    assert not Alert.objects.filter(source_ip='10.9.3.1').exists()
    assert post_events(client, ingestor_token, second).status_code == 201
    assert Alert.objects.filter(source_ip='10.9.3.1', rule_name='brute_force').count() == 1


def test_continued_attack_updates_one_incident_no_second_investigation(
        client, ingestor_token, db, django_capture_on_commit_callbacks):
    from unittest.mock import patch
    from alerts.models import Alert
    now = timezone.now()
    first = _logins('10.9.4.1', 25, now - timedelta(seconds=50))
    second = _logins('10.9.4.1', 25, now - timedelta(seconds=20))
    with patch('detection.service.dispatch_investigation') as dispatch:
        with django_capture_on_commit_callbacks(execute=True):
            assert post_events(client, ingestor_token, first).status_code == 201
        assert dispatch.call_count == 1
        with django_capture_on_commit_callbacks(execute=True):
            assert post_events(client, ingestor_token, second).status_code == 201
        assert dispatch.call_count == 1
    assert Alert.objects.filter(source_ip='10.9.4.1').count() == 1


def test_resolved_then_new_incident(client, ingestor_token, db):
    from alerts.models import Alert
    now = timezone.now()
    assert post_events(client, ingestor_token, _logins('10.9.5.1', 20, now - timedelta(seconds=50))).status_code == 201
    alert = Alert.objects.get(source_ip='10.9.5.1')
    alert.incident_status = 'resolved'
    alert.save(update_fields=['incident_status'])
    assert post_events(client, ingestor_token, _logins('10.9.5.1', 20, now - timedelta(seconds=40))).status_code == 201
    assert Alert.objects.filter(source_ip='10.9.5.1').count() == 2


def test_ipv6_normalized(client, ingestor_token, db):
    from alerts.models import Alert
    start = timezone.now() - timedelta(seconds=50)
    assert post_events(client, ingestor_token, _logins('2001:DB8::1', 20, start)).status_code == 201
    assert Alert.objects.filter(source_ip='2001:db8::1').exists()


def test_first_seen_is_earliest_event(client, ingestor_token, db):
    from alerts.models import Alert
    start = timezone.now() - timedelta(seconds=45)
    events = _logins('10.9.6.1', 25, start)
    assert post_events(client, ingestor_token, events).status_code == 201
    alert = Alert.objects.get(source_ip='10.9.6.1')
    assert alert.first_seen_at == datetime.fromisoformat(events[0]['timestamp'])
    assert alert.last_seen_at == datetime.fromisoformat(events[-1]['timestamp'])


def test_last_seen_never_moves_backwards(client, ingestor_token, db):
    from alerts.models import Alert
    now = timezone.now()
    first = _logins('10.9.7.1', 25, now - timedelta(seconds=45))
    assert post_events(client, ingestor_token, first).status_code == 201
    alert = Alert.objects.get(source_ip='10.9.7.1')
    original_last = alert.last_seen_at
    older = _logins('10.9.7.1', 25, now - timedelta(seconds=120))
    assert post_events(client, ingestor_token, older).status_code == 201
    alert.refresh_from_db()
    assert alert.last_seen_at == original_last


def test_integrity_race_handled(client, ingestor_token, db):
    from unittest.mock import MagicMock, patch
    from alerts.models import Alert
    from tests.conftest import make_alert
    make_alert(source_ip='10.9.8.1', rule_name='brute_force')
    assert Alert.objects.filter(source_ip='10.9.8.1').count() == 1

    real_filter = Alert.objects.filter
    state = {'calls': 0}

    def fake_filter(*args, **kwargs):
        state['calls'] += 1
        if state['calls'] == 1:
            m = MagicMock()
            m.select_for_update.return_value.first.return_value = None
            return m
        return real_filter(*args, **kwargs)

    start = timezone.now() - timedelta(seconds=50)
    with patch.object(Alert.objects, 'filter', side_effect=fake_filter):
        resp = post_events(client, ingestor_token, _logins('10.9.8.1', 20, start))
    assert resp.status_code == 201
    assert Alert.objects.filter(source_ip='10.9.8.1').count() == 1


def test_brute_force_evidence_and_severity(client, ingestor_token, db):
    from alerts.models import Alert
    start = timezone.now() - timedelta(seconds=50)
    assert post_events(client, ingestor_token, _logins('10.9.9.1', 20, start, usernames=3)).status_code == 201
    alert = Alert.objects.get(source_ip='10.9.9.1')
    assert alert.severity == 'high'
    assert alert.mitre_id == 'T1110'
    assert alert.evidence['failed_logins'] == 20
    assert alert.evidence['distinct_usernames'] == 3
    assert isinstance(alert.evidence['distinct_usernames'], int)
    assert alert.evidence['threshold'] == 20
    assert alert.evidence['window_seconds'] == 60
    assert 'window_start' in alert.evidence and 'window_end' in alert.evidence


def test_port_scan_evidence_and_severity(client, ingestor_token, db):
    from alerts.models import Alert
    start = timezone.now() - timedelta(seconds=30)
    assert post_events(client, ingestor_token, _connections('10.9.9.2', [1000 + i for i in range(15)], start)).status_code == 201
    alert = Alert.objects.get(source_ip='10.9.9.2')
    assert alert.severity == 'medium'
    assert alert.mitre_id == 'T1046'
    assert alert.evidence['distinct_ports'] == 15
    assert alert.evidence['connection_events'] == 15
    assert alert.evidence['threshold'] == 15
