from unittest.mock import patch

import httpx
import ollama
import pytest

from agent.tasks import run_investigation
from tests.conftest import make_alert


def test_remote_protocol_error_is_transient(db):
    alert = make_alert()
    with patch('agent.investigator.ollama.Client') as client_cls, patch('agent.tasks.time.sleep'):
        client_cls.return_value.chat.side_effect = httpx.RemoteProtocolError('dropped')
        run_investigation.run(alert.id)
    alert.refresh_from_db()
    assert alert.investigation_status == 'failed'
    assert alert.investigation_error == 'llm_unavailable'
    assert alert.investigation_attempts == 2


def test_read_error_then_success(db):
    alert = make_alert()
    first_ok = {'message': {'role': 'assistant', 'content': ''}}
    success = {'message': {'role': 'assistant', 'content': '{"summary": "ok", "recommended_actions": ["check"]}'}}
    with patch('agent.investigator.ollama.Client') as client_cls, patch('agent.tasks.time.sleep'):
        chat = client_cls.return_value.chat
        chat.side_effect = [httpx.ReadError('read'), first_ok, success]
        run_investigation.run(alert.id)
    alert.refresh_from_db()
    assert alert.investigation_status == 'completed'
    assert alert.investigation_attempts == 2


def test_response_error_not_retried(db):
    alert = make_alert()
    with patch('agent.investigator.ollama.Client') as client_cls, patch('agent.tasks.time.sleep'):
        chat = client_cls.return_value.chat
        chat.side_effect = ollama.ResponseError('model not found')
        run_investigation.run(alert.id)
        calls = chat.call_count
    alert.refresh_from_db()
    assert alert.investigation_status == 'failed'
    assert alert.investigation_error == 'llm_error'
    assert alert.investigation_attempts == 1
    assert calls == 1


def test_invalid_json_not_retried(db):
    alert = make_alert()
    with patch('agent.investigator.ollama.Client') as client_cls, patch('agent.tasks.time.sleep'):
        chat = client_cls.return_value.chat
        chat.side_effect = [
            {'message': {'role': 'assistant', 'content': ''}},
            {'message': {'role': 'assistant', 'content': 'not json'}},
        ]
        run_investigation.run(alert.id)
        calls = chat.call_count
    alert.refresh_from_db()
    assert alert.investigation_status == 'failed'
    assert alert.investigation_error == 'invalid_output'
    assert alert.investigation_attempts == 1
    assert calls == 2


def test_soft_time_limit_recorded(db):
    from celery.exceptions import SoftTimeLimitExceeded
    alert = make_alert()
    with patch('agent.tasks.investigate', side_effect=SoftTimeLimitExceeded()):
        run_investigation.run(alert.id)
    alert.refresh_from_db()
    assert alert.investigation_status == 'failed'
    assert alert.investigation_error == 'time_limit'


def test_unexpected_error_still_contained(db):
    alert = make_alert()
    with patch('agent.tasks.investigate', side_effect=RuntimeError('boom')) as inv:
        run_investigation.run(alert.id)
    alert.refresh_from_db()
    assert alert.investigation_status == 'failed'
    assert alert.investigation_error == 'unexpected_error'
    assert alert.investigation_attempts == 1
    assert inv.call_count == 1


def _result():
    return {'summary': 'ok', 'recommended_actions': ['check'], 'used_tool': False, 'latency_ms': 5}


def test_claim_runs_once(db):
    alert = make_alert()
    with patch('agent.tasks.investigate', return_value=_result()) as inv:
        run_investigation.run(alert.id)
        run_investigation.run(alert.id)
    assert inv.call_count == 1
    alert.refresh_from_db()
    assert alert.investigation_status == 'completed'


def test_result_discarded_if_status_reset_mid_run(db):
    from alerts.models import Alert
    alert = make_alert()

    def fake(alert_obj):
        Alert.objects.filter(id=alert_obj.id).update(investigation_status='queued')
        return _result()

    with patch('agent.tasks.investigate', side_effect=fake):
        run_investigation.run(alert.id)
    alert.refresh_from_db()
    assert alert.investigation_status == 'queued'
    assert alert.ai_summary == ''


def test_queue_failure_returns_201_and_marks_alert(client, ingestor_token, db, django_capture_on_commit_callbacks):
    from alerts.models import Alert
    from tests.conftest import post_events
    from tests.test_detection import _logins
    from datetime import timedelta
    from django.utils import timezone

    events = _logins('10.8.0.1', 20, timezone.now() - timedelta(seconds=50))
    with patch('agent.tasks.run_investigation.apply_async', side_effect=ConnectionError('broker down')):
        with django_capture_on_commit_callbacks(execute=True):
            resp = post_events(client, ingestor_token, events)
    assert resp.status_code == 201
    alert = Alert.objects.get(source_ip='10.8.0.1')
    assert alert.investigation_status == 'failed'
    assert alert.investigation_error == 'queue_unavailable'
    assert alert.evidence['failed_logins'] == 20
    assert alert.severity == 'high'


def test_dispatch_not_called_before_commit(client, ingestor_token, db, django_capture_on_commit_callbacks):
    from tests.conftest import post_events
    from tests.test_detection import _logins
    from datetime import timedelta
    from django.utils import timezone

    events = _logins('10.8.0.2', 20, timezone.now() - timedelta(seconds=50))
    with patch('detection.service.dispatch_investigation') as dispatch:
        with django_capture_on_commit_callbacks(execute=False) as callbacks:
            resp = post_events(client, ingestor_token, events)
            assert resp.status_code == 201
            assert dispatch.call_count == 0
        assert len(callbacks) == 1
        for callback in callbacks:
            callback()
        assert dispatch.call_count == 1


def test_dispatch_not_called_on_rollback(client, ingestor_token, db, django_capture_on_commit_callbacks):
    from alerts.models import Alert
    from events.models import LogEvent
    from events import views
    from tests.conftest import post_events
    from tests.test_detection import _logins
    from datetime import timedelta
    from django.utils import timezone

    real = views.process_events_for_detection

    def boom(events):
        real(events)
        raise RuntimeError('rollback')

    events = _logins('10.8.0.3', 20, timezone.now() - timedelta(seconds=50))
    with patch('detection.service.dispatch_investigation') as dispatch, \
            patch('events.views.process_events_for_detection', side_effect=boom):
        with django_capture_on_commit_callbacks(execute=True):
            with pytest.raises(RuntimeError):
                post_events(client, ingestor_token, events)
    assert dispatch.call_count == 0
    assert Alert.objects.count() == 0
    assert LogEvent.objects.count() == 0
