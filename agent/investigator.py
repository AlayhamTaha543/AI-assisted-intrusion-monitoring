import json
import time
from datetime import timedelta

import ollama
from django.conf import settings
from django.db.models import Count
from pydantic import BaseModel, ConfigDict, Field

from alerts.models import Alert
from events.models import LogEvent


class Assessment(BaseModel):
    model_config = ConfigDict(extra='forbid')
    summary: str = Field(min_length=1, max_length=500)
    recommended_actions: list[str] = Field(default_factory=list, max_length=3)


def get_related_context(alert):
    # Counts grouped by event_type for same source_ip within [first_seen_at - 60s, last_seen_at + 60s]
    window_start = alert.first_seen_at - timedelta(seconds=60)
    window_end = alert.last_seen_at + timedelta(seconds=60)
    counts = {}
    for et in ['login_failed', 'login_success', 'connection']:
        counts[et] = LogEvent.objects.filter(source_ip=alert.source_ip, event_type=et, timestamp__gte=window_start, timestamp__lte=window_end).count()
    # previous alerts
    prev_alerts = list(Alert.objects.filter(source_ip=alert.source_ip).exclude(id=alert.id).order_by('-created_at')[:3].values('id', 'rule_name', 'incident_status', 'severity', 'created_at'))
    # nearby events
    nearby = []
    for ev in LogEvent.objects.filter(source_ip=alert.source_ip, timestamp__gte=window_start, timestamp__lte=window_end).order_by('-timestamp')[:5]:
        uname = ev.username[:64] if ev.username else None
        nearby.append({
            'timestamp': ev.timestamp.isoformat(),
            'event_type': ev.event_type,
            'protocol': ev.protocol,
            'dest_port': ev.dest_port,
            'username_truncated': uname,
        })
    return {
        'event_type_counts': counts,
        'previous_alerts': prev_alerts,
        'nearby_events': nearby,
    }


TOOL_DEFINITION = {
    'type': 'function',
    'function': {
        'name': 'get_related_context',
        'description': 'Get related context for the current incident (bounded, read-only)',
        'parameters': {
            'type': 'object',
            'properties': {},
            'required': [],
        },
    },
}


def investigate(alert):
    start = time.time()
    used_tool = False
    context_data = None

    prompt = f"Rule: {alert.rule_name}\nSource IP: {alert.source_ip}\nEvidence: {json.dumps(alert.evidence)}\n"
    messages = [
        {'role': 'system', 'content': 'You are a security investigator. Only return JSON with summary and recommended_actions. Do not change severity or evidence.'},
        {'role': 'user', 'content': prompt},
    ]

    try:
        # First call with tool
        resp1 = ollama.chat(
            model=settings.OLLAMA_MODEL,
            messages=messages,
            tools=[TOOL_DEFINITION],
            options={'timeout': settings.OLLAMA_TIMEOUT_SECONDS},
        )
        # Check for tool calls
        msg = resp1.get('message', {}) if isinstance(resp1, dict) else getattr(resp1, 'message', {})
        tool_calls = msg.get('tool_calls') or []
        if len(tool_calls) == 1 and tool_calls[0].get('function', {}).get('name') == 'get_related_context':
            try:
                context_data = get_related_context(alert)
                used_tool = True
                messages.append(msg)
                messages.append({'role': 'tool', 'name': 'get_related_context', 'content': json.dumps(context_data)})
            except Exception:
                used_tool = False
        # Final call
        resp2 = ollama.chat(
            model=settings.OLLAMA_MODEL,
            messages=messages + [{'role': 'user', 'content': 'Return JSON with summary (1-500 chars) and recommended_actions (list of up to 3 strings, each max 200 chars).'}],
            format=Assessment.model_json_schema(),
            options={'timeout': settings.OLLAMA_TIMEOUT_SECONDS},
        )
        content = resp2.get('message', {}).get('content', '') if isinstance(resp2, dict) else getattr(resp2.message, 'content', '')
        data = json.loads(content)
        assessment = Assessment.model_validate(data)
        # sanitize
        summary = ''.join(c for c in assessment.summary if ord(c) >= 32 or c in '\n\t')
        summary = summary[:500]
        recos = []
        for r in assessment.recommended_actions[:3]:
            rr = ''.join(c for c in r if ord(c) >= 32 or c in '\n\t')
            recos.append(rr[:200])
        latency_ms = int((time.time() - start) * 1000)
        return {'summary': summary, 'recommended_actions': recos, 'used_tool': used_tool, 'latency_ms': latency_ms}
    except Exception as e:
        raise
