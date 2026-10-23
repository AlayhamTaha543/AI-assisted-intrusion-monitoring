import json
import uuid
from datetime import datetime, timedelta
from django.utils import timezone
from rest_framework.authtoken.models import Token


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
