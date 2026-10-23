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
