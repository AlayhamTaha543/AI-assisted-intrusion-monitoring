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
