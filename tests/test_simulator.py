import json
from datetime import datetime, timezone

import pytest

from simulator.generator import BRUTE_FORCE_IP, generate_scenario
from tests.conftest import post_events


def _start():
    return datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc)


def test_same_seed_same_events():
    assert generate_scenario('brute_force', seed=7, start=_start()) == generate_scenario('brute_force', seed=7, start=_start())


def test_different_seed_different_ids():
    a = generate_scenario('brute_force', seed=7, start=_start())
    b = generate_scenario('brute_force', seed=8, start=_start())
    assert [e['event_id'] for e in a] != [e['event_id'] for e in b]


@pytest.mark.parametrize('name', ['normal', 'brute_force', 'port_scan', 'benign_failures', 'injection', 'continue_attack'])
def test_ids_unique(name):
    events = generate_scenario(name, seed=1)
    ids = [e['event_id'] for e in events]
    assert len(ids) == len(set(ids))


@pytest.mark.parametrize('name', ['normal', 'brute_force', 'port_scan', 'benign_failures', 'injection', 'continue_attack'])
def test_chronological(name):
    events = generate_scenario(name, seed=1)
    stamps = [datetime.fromisoformat(e['timestamp']) for e in events]
    assert stamps == sorted(stamps)


@pytest.mark.parametrize('name', ['normal', 'brute_force', 'port_scan', 'benign_failures', 'injection', 'continue_attack'])
def test_not_in_future(name):
    now = datetime.now(timezone.utc)
    events = generate_scenario(name, seed=1)
    for e in events:
        assert datetime.fromisoformat(e['timestamp']) <= now


@pytest.mark.parametrize('name', ['normal', 'brute_force', 'port_scan', 'benign_failures', 'injection', 'continue_attack'])
def test_all_events_pass_serializer(name):
    from events.serializers import LogEventSerializer
    for e in generate_scenario(name, seed=1):
        s = LogEventSerializer(data=e)
        assert s.is_valid(), s.errors


def test_normal_creates_no_alert(client, ingestor_token, db):
    from alerts.models import Alert
    events = generate_scenario('normal', seed=1)
    resp = post_events(client, ingestor_token, events)
    assert resp.status_code == 201
    assert Alert.objects.count() == 0


def test_brute_force_shape():
    events = generate_scenario('brute_force', seed=1, start=_start())
    failures = [e for e in events if e['event_type'] == 'login_failed']
    usernames = {e['username'] for e in failures}
    stamps = [datetime.fromisoformat(e['timestamp']) for e in failures]
    assert len(failures) == 40
    assert len(usernames) == 8
    assert (max(stamps) - min(stamps)).total_seconds() <= 60


def test_port_scan_shape():
    events = generate_scenario('port_scan', seed=1, start=_start())
    ports = {e['dest_port'] for e in events if e['event_type'] == 'connection'}
    assert len(ports) == 50


def test_injection_payload_present():
    events = generate_scenario('injection', seed=1, start=_start())
    matches = [e for e in events if e.get('username') and 'ignore previous instructions' in e['username']]
    assert len(matches) == 1


def test_rerun_same_seed_is_idempotent(client, ingestor_token, db):
    from alerts.models import Alert
    from events.models import LogEvent
    events = generate_scenario('brute_force', seed=1)
    first = post_events(client, ingestor_token, events)
    assert first.status_code == 201
    rows_after_first = LogEvent.objects.count()
    alerts_after_first = Alert.objects.count()
    second = post_events(client, ingestor_token, events)
    assert second.status_code == 201
    body = json.loads(second.content)
    assert body['inserted'] == 0
    assert LogEvent.objects.count() == rows_after_first
    assert Alert.objects.count() == alerts_after_first == 1
    assert Alert.objects.first().source_ip == BRUTE_FORCE_IP
