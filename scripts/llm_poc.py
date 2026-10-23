#!/usr/bin/env python
import json
import time
from pathlib import Path

import ollama

from pydantic import BaseModel, ConfigDict, Field


class Assessment(BaseModel):
    model_config = ConfigDict(extra='forbid')
    summary: str = Field(min_length=1, max_length=500)
    recommended_actions: list[str] = Field(default_factory=list, max_length=3)


def get_related_context():
    return {
        'event_type_counts': {'login_failed': 20, 'login_success': 0, 'connection': 0},
        'previous_alerts': [],
        'nearby_events': [],
    }


TOOL_DEFINITION = {
    'type': 'function',
    'function': {
        'name': 'get_related_context',
        'description': 'Get related context for the current incident',
        'parameters': {'type': 'object', 'properties': {}, 'required': []},
    },
}


MODEL = 'qwen2.5:7b'


def _client():
    host = 'http://localhost:11434'
    return ollama.Client(host=host, timeout=60)


def run():
    evidence = {'failed_logins': 25, 'distinct_usernames': 5, 'threshold': 20}
    results = []
    for i in range(3):
        messages = [
            {'role': 'system', 'content': 'You are a security investigator. Only return JSON with summary and recommended_actions.'},
            {'role': 'user', 'content': f"Rule: brute_force\nSource IP: 203.0.113.45\nEvidence: {json.dumps(evidence)}\n"},
        ]
        tool_called = False
        try:
            start = time.time()
            resp1 = _client().chat(model=MODEL, messages=messages, tools=[TOOL_DEFINITION], options={'temperature': 0})
            msg = resp1.get('message', {}) if isinstance(resp1, dict) else getattr(resp1, 'message', {})
            tcs = getattr(msg, 'tool_calls', None) if not isinstance(msg, dict) else msg.get('tool_calls') or []
            if tcs and len(tcs) == 1:
                tool_called = True
                messages.append(msg)
                ctx = get_related_context()
                messages.append({'role': 'tool', 'tool_name': 'get_related_context', 'content': json.dumps(ctx)})
            resp2 = _client().chat(
                model=MODEL,
                messages=messages + [{'role': 'user', 'content': 'Return JSON.'}],
                format=Assessment.model_json_schema(),
                options={'temperature': 0},
            )
            content = resp2.get('message', {}).get('content', '') if isinstance(resp2, dict) else getattr(resp2.message, 'content', '')
            data = json.loads(content)
            Assessment.model_validate(data)
            latency = int((time.time() - start) * 1000)
            results.append((tool_called, True, latency))
            print(f'run{i+1}: tool_called={tool_called} valid=True latency_ms={latency}')
        except Exception as e:
            results.append((tool_called, False, 0))
            print(f'run{i+1}: fail {e}')
    append_results(results)


def append_results(results):
    path = Path('docs/DECISIONS.md')
    text = path.read_text() if path.exists() else '# Decisions\n'
    text = text.replace('| _pending_ | | | | |\n', '')
    if '## Step 0 results' not in text:
        text += '\n## Step 0 results\n'
    lines = [
        '',
        '| Run | Tool called | Valid JSON | Latency (ms) | Model |',
        '| --- | --- | --- | --- | --- |',
    ]
    for index, (tool_called, valid, latency) in enumerate(results, 1):
        lines.append(f'| {index} | {tool_called} | {valid} | {latency} | {MODEL} |')
    path.write_text(text.rstrip() + '\n' + '\n'.join(lines) + '\n')


if __name__ == '__main__':
    run()
