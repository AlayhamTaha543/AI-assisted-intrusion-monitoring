#!/usr/bin/env python
import json
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


def run():
    evidence = {'failed_logins': 25, 'distinct_usernames': 5, 'threshold': 20}
    prompt = f"Rule: brute_force\nSource IP: 203.0.113.45\nEvidence: {json.dumps(evidence)}\n"
    messages = [
        {'role': 'system', 'content': 'You are a security investigator. Only return JSON with summary and recommended_actions.'},
        {'role': 'user', 'content': prompt},
    ]
    tool_calls = 0
    valid = 0
    for i in range(3):
        try:
            resp1 = ollama.chat(model='qwen2.5:7b', messages=messages, tools=[TOOL_DEFINITION])
            msg = resp1.get('message', {}) if isinstance(resp1, dict) else getattr(resp1, 'message', {})
            tcs = msg.get('tool_calls') or []
            if len(tcs) == 1 and tcs[0].get('function', {}).get('name') == 'get_related_context':
                tool_calls += 1
                messages.append(msg)
                ctx = get_related_context()
                messages.append({'role': 'tool', 'name': 'get_related_context', 'content': json.dumps(ctx)})
            resp2 = ollama.chat(
                model='qwen2.5:7b',
                messages=messages + [{'role': 'user', 'content': 'Return JSON.'}],
                format=Assessment.model_json_schema(),
            )
            content = resp2.get('message', {}).get('content', '') if isinstance(resp2, dict) else getattr(resp2.message, 'content', '')
            data = json.loads(content)
            Assessment.model_validate(data)
            valid += 1
            print(f'run{i+1}: ok')
        except Exception as e:
            print(f'run{i+1}: fail {e}')
    print(f'tool_calls={tool_calls} valid={valid}')


if __name__ == '__main__':
    run()
