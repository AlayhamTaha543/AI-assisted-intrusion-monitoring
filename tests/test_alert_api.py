import json


def test_analyst_can_patch_status(client, analyst_token, db):
    from alerts.models import Alert, MITRE
    from django.utils import timezone
    alert = Alert.objects.create(
        rule_name='brute_force',
        source_ip='1.2.3.4',
        incident_status='open',
        investigation_status='queued',
        severity='high',
        mitre_id=MITRE['brute_force']['id'],
        mitre_name=MITRE['brute_force']['name'],
        first_seen_at=timezone.now(),
        last_seen_at=timezone.now(),
        last_window_count=20,
        peak_window_count=20,
        evidence={'failed_logins': 20},
    )
    resp = client.patch(f'/api/alerts/{alert.id}/', data=json.dumps({'incident_status': 'acknowledged'}), content_type='application/json', HTTP_AUTHORIZATION=f'Token {analyst_token}')
    assert resp.status_code == 200
