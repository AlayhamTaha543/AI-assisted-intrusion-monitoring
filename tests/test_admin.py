from io import StringIO
from unittest.mock import patch

from django.core.management import call_command
from django.utils import timezone

from tests.conftest import make_alert


def _demo_login(client):
    out = StringIO()
    call_command('create_demo_users', stdout=out)
    password = None
    for line in out.getvalue().splitlines():
        if line.startswith('ANALYST_PASSWORD='):
            password = line.split('=', 1)[1]
    assert password and password != '(unchanged)'
    assert client.login(username='analyst1', password=password)


def test_analyst_can_view_alerts_in_admin(client, db):
    make_alert(source_ip='10.7.0.1')
    _demo_login(client)
    resp = client.get('/admin/alerts/alert/')
    assert resp.status_code == 200
    assert '10.7.0.1' in resp.content.decode()


def test_admin_is_read_only(client, db):
    alert = make_alert()
    _demo_login(client)
    assert client.get('/admin/alerts/alert/add/').status_code == 403
    assert client.get(f'/admin/alerts/alert/{alert.id}/delete/').status_code == 403
    resp = client.get(f'/admin/alerts/alert/{alert.id}/change/')
    assert resp.status_code == 200
    content = resp.content.decode()
    assert 'name="evidence"' not in content
    assert 'name="severity"' not in content


def test_admin_escapes_ai_text(client, db):
    alert = make_alert(ai_summary='<script>alert(1)</script>')
    _demo_login(client)
    content = client.get(f'/admin/alerts/alert/{alert.id}/change/').content.decode()
    assert '&lt;script&gt;' in content
    assert '<script>alert(1)</script>' not in content


def test_admin_sections_present(client, db):
    alert = make_alert()
    _demo_login(client)
    content = client.get(f'/admin/alerts/alert/{alert.id}/change/').content.decode()
    assert 'Computed by the backend' in content
    assert 'AI-generated, not authoritative' in content


def test_rerun_requeues_failed_and_skips_completed(client, db, django_capture_on_commit_callbacks):
    failed = make_alert(
        source_ip='10.7.0.2',
        investigation_status='failed',
        ai_summary='old summary',
        ai_model='old-model',
        ai_used_tool=True,
        investigation_attempts=2,
        investigation_error='llm_error',
        investigation_started_at=timezone.now(),
        investigated_at=timezone.now(),
        investigation_latency_ms=123,
    )
    completed = make_alert(
        source_ip='10.7.0.3',
        investigation_status='completed',
        ai_summary='keep me',
    )
    _demo_login(client)
    with patch('agent.tasks.run_investigation.delay') as delay:
        with django_capture_on_commit_callbacks(execute=True):
            resp = client.post('/admin/alerts/alert/', {
                'action': 'rerun_investigation',
                'index': '0',
                'select_across': '0',
                '_selected_action': [str(failed.id), str(completed.id)],
            }, follow=True)
    assert resp.status_code == 200
    failed.refresh_from_db()
    completed.refresh_from_db()
    assert failed.investigation_status == 'queued'
    assert failed.ai_summary == ''
    assert failed.ai_model == ''
    assert failed.ai_used_tool is False
    assert failed.investigation_attempts == 0
    assert failed.investigation_error == ''
    assert failed.investigation_started_at is None
    assert failed.investigated_at is None
    assert failed.investigation_latency_ms is None
    assert completed.investigation_status == 'completed'
    assert completed.ai_summary == 'keep me'
    assert delay.call_count == 1
    assert 'Re-queued 1, skipped 1' in resp.content.decode()
