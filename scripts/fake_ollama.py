#!/usr/bin/env python3
"""Tiny stand-in for the Ollama /api/chat endpoint (standard library only).

Use it to demo or test the project on a machine WITHOUT a local model.

    python scripts/fake_ollama.py            # listens on 0.0.0.0:11434
    python scripts/fake_ollama.py --port 11500

What it does (deterministic, no AI involved):
  1st call (tools offered)  -> asks for the `get_related_context` tool
  2nd call (format given)   -> returns a JSON assessment built from the
                               BACKEND_EVIDENCE numbers found in the prompt

Important: output produced with this stub is NOT model output. Label any
screenshots or results made with it as "stub LLM" in your README.
"""
import argparse
import json
import re
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer


def build_assessment(prompt: str) -> dict:
    rule = (re.search(r'Rule:\s*(\w+)', prompt) or [None, 'unknown'])[1]
    evidence = {}
    m = re.search(r'Evidence:\s*(\{.*\})', prompt, re.S)
    if m:
        try:
            evidence = json.loads(m.group(1))
        except ValueError:
            pass
    window = evidence.get('window_seconds', 60)
    if rule == 'brute_force':
        summary = (f"{evidence.get('failed_logins', 'Many')} failed logins from one source within {window}s, "
                   f"targeting {evidence.get('distinct_usernames', 'several')} distinct accounts. "
                   "Pattern is consistent with a password-guessing attempt.")
        actions = ['Review the targeted accounts for lockouts or resets',
                   'Check for any successful login from this source',
                   'Consider rate-limiting or blocking the source after analyst review']
    elif rule == 'port_scan':
        summary = (f"One source contacted {evidence.get('distinct_ports', 'many')} distinct destination ports "
                   f"within {window}s. Pattern is consistent with network service discovery.")
        actions = ['Identify which hosts and ports were probed',
                   'Check whether the source is a known scanner or internal asset',
                   'Review firewall logs for follow-up connections']
    else:
        summary = 'Rule-based detection fired; review the backend evidence.'
        actions = ['Review the backend evidence']
    return {'summary': summary[:500], 'recommended_actions': [a[:200] for a in actions]}


class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        pass

    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers.get('Content-Length', 0))) or b'{}')
        messages = body.get('messages', [])
        prompt = next((m.get('content', '') for m in messages if m.get('role') == 'user'), '')
        message = {'role': 'assistant', 'content': ''}
        if body.get('format'):
            message['content'] = json.dumps(build_assessment(prompt))
        elif body.get('tools') and not any(m.get('role') == 'tool' for m in messages):
            message['tool_calls'] = [{'function': {'name': 'get_related_context', 'arguments': {}}}]
        else:
            message['content'] = json.dumps(build_assessment(prompt))
        out = json.dumps({'model': body.get('model', 'stub'), 'created_at': '2026-01-01T00:00:00Z',
                          'message': message, 'done': True, 'done_reason': 'stop'}).encode()
        self.send_response(200)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Content-Length', str(len(out)))
        self.end_headers()
        self.wfile.write(out)


if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    ap.add_argument('--host', default='0.0.0.0')
    ap.add_argument('--port', type=int, default=11434)
    args = ap.parse_args()
    print(f'Stub Ollama listening on http://{args.host}:{args.port} (NOT a real model)')
    ThreadingHTTPServer((args.host, args.port), Handler).serve_forever()
