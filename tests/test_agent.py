from unittest.mock import patch
from alerts.models import Alert, MITRE
from django.utils import timezone


def test_agent_saves_valid_output(db):
    from agent import investigator
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
    mock_resp1 = {'message': {'role': 'assistant', 'content': ''}}
    mock_resp2 = {'message': {'role': 'assistant', 'content': '{"summary": "Brute force detected", "recommended_actions": ["Block IP"]}'}}
    with patch.object(investigator.ollama, 'Client') as m:
        client_inst = m.return_value
        client_inst.chat.side_effect = [mock_resp1, mock_resp2]
        res = investigator.investigate(alert)
        assert res['summary'] == 'Brute force detected'
        assert res['recommended_actions'] == ['Block IP']
