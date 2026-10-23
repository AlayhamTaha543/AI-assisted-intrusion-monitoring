import json
from datetime import timedelta
from urllib.parse import quote

import pytest
from django.utils import timezone
from rest_framework.authtoken.models import Token

from tests.conftest import make_alert


def _auth(token):
    return {'HTTP_AUTHORIZATION': f'Token {token}'}


def _patch(client, token, alert, body):
    return client.patch(f'/api/alerts/{alert.id}/', data=json.dumps(body),
                        content_type='application/json', **_auth(token))


def test_analyst_can_patch_status(client, analyst_token, analyst_user, db):
    alert = make_alert()
    resp = _patch(client, analyst_token, alert, {'incident_status': 'acknowledged'})
    assert resp.status_code == 200
    alert.refresh_from_db()
    assert alert.incident_status == 'acknowledged'
    assert alert.status_changed_by == analyst_user


def test_page_size_invalid_400(client, analyst_token, db):
    for value in ('abc', '0', '-5'):
        resp = client.get(f'/api/alerts/?page_size={value}', **_auth(analyst_token))
        assert resp.status_code == 400, value


def test_page_size_capped_100(client, analyst_token, db):
    for i in range(105):
        make_alert(source_ip=f'10.0.0.{i}', incident_status='resolved')
    resp = client.get('/api/alerts/?page_size=500', **_auth(analyst_token))
    assert resp.status_code == 200
    assert len(resp.json()['results']) == 100


def test_source_ip_filter_invalid_400(client, analyst_token, db):
    resp = client.get('/api/alerts/?source_ip=not-an-ip', **_auth(analyst_token))
    assert resp.status_code == 400


def test_source_ip_filter_ipv6_normalized(client, analyst_token, db):
    make_alert(source_ip='2001:DB8::1')
    resp = client.get('/api/alerts/?source_ip=2001:DB8::1', **_auth(analyst_token))
    assert resp.status_code == 200
    assert resp.json()['count'] == 1


def test_time_filters_work_and_reject_garbage(client, analyst_token, db):
    now = timezone.now()
    make_alert(source_ip='10.1.0.1', first_seen_at=now - timedelta(hours=3))
    make_alert(source_ip='10.1.0.2', first_seen_at=now - timedelta(hours=2))
    make_alert(source_ip='10.1.0.3', first_seen_at=now - timedelta(hours=1))

    after = (now - timedelta(minutes=150)).isoformat()
    resp = client.get(f'/api/alerts/?first_seen_after={quote(after)}', **_auth(analyst_token))
    assert resp.status_code == 200
    assert resp.json()['count'] == 2

    before = (now - timedelta(minutes=150)).isoformat()
    resp = client.get(f'/api/alerts/?first_seen_before={quote(before)}', **_auth(analyst_token))
    assert resp.status_code == 200
    assert resp.json()['count'] == 1

    resp = client.get('/api/alerts/?first_seen_after=yesterday', **_auth(analyst_token))
    assert resp.status_code == 400


def test_filters_combine_with_and(client, analyst_token, db):
    now = timezone.now()
    make_alert(source_ip='10.2.0.1', severity='high', rule_name='brute_force',
               incident_status='open', first_seen_at=now - timedelta(hours=1))
    make_alert(source_ip='10.2.0.2', severity='medium', rule_name='port_scan',
               incident_status='open', first_seen_at=now - timedelta(hours=1))
    make_alert(source_ip='10.2.0.3', severity='high', rule_name='brute_force',
               incident_status='resolved', first_seen_at=now - timedelta(hours=1))

    after = (now - timedelta(hours=2)).isoformat()
    resp = client.get(
        f'/api/alerts/?severity=high&rule_name=brute_force&incident_status=open&first_seen_after={quote(after)}',
        **_auth(analyst_token),
    )
    assert resp.status_code == 200
    assert resp.json()['count'] == 1


def test_patch_non_object_body_400(client, analyst_token, db):
    alert = make_alert()
    for body in ([], 'x', 5):
        resp = _patch(client, analyst_token, alert, body)
        assert resp.status_code == 400


def test_patch_extra_field_400(client, analyst_token, db):
    alert = make_alert()
    resp = _patch(client, analyst_token, alert, {'incident_status': 'acknowledged', 'severity': 'medium'})
    assert resp.status_code == 400


def test_status_transitions(client, analyst_token, analyst_user, db):
    alert = make_alert(incident_status='open')
    assert _patch(client, analyst_token, alert, {'incident_status': 'acknowledged'}).status_code == 200
    assert _patch(client, analyst_token, alert, {'incident_status': 'resolved'}).status_code == 200
    assert _patch(client, analyst_token, alert, {'incident_status': 'open'}).status_code == 400
    alert.refresh_from_db()
    assert alert.incident_status == 'resolved'
    assert alert.status_changed_by == analyst_user


def test_role_permissions(client, ingestor_token, analyst_token, db):
    alert = make_alert()

    resp = client.get('/api/alerts/', **_auth(ingestor_token))
    assert resp.status_code == 403
    resp = _patch(client, ingestor_token, alert, {'incident_status': 'acknowledged'})
    assert resp.status_code == 403

    resp = client.post('/api/events/', data=json.dumps([]), content_type='application/json',
                       **_auth(analyst_token))
    assert resp.status_code == 403

    resp = client.get('/api/alerts/')
    assert resp.status_code == 401
