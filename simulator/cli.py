import argparse
import json
import os
import sys
from datetime import datetime, timezone
from urllib import error, request

from .generator import SCENARIOS, default_start, generate_scenario


def _parse_start(value, scenario):
    if not value:
        return default_start(scenario)
    dt = datetime.fromisoformat(value)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def _post(base_url, token, events):
    data = json.dumps(events).encode('utf-8')
    req = request.Request(base_url.rstrip('/') + '/api/events/', data=data, method='POST')
    req.add_header('Content-Type', 'application/json')
    req.add_header('Authorization', f'Token {token}')
    with request.urlopen(req) as resp:
        return resp.read().decode('utf-8')


def send_batches(base_url, token, events, batch_size=None):
    size = batch_size or int(os.environ.get('MAX_BATCH_SIZE', '200'))
    results = []
    for i in range(0, len(events), size):
        results.append(_post(base_url, token, events[i:i + size]))
    return results


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('scenario', choices=sorted(SCENARIOS))
    parser.add_argument('--base-url', default='http://localhost:8000')
    parser.add_argument('--token', default=None)
    parser.add_argument('--seed', type=int, default=42)
    parser.add_argument('--start', default=None, help='ISO timestamp')
    args = parser.parse_args()

    token = args.token or os.environ.get('INGEST_TOKEN')
    if not token:
        print('set INGEST_TOKEN or pass --token', file=sys.stderr)
        sys.exit(1)

    start = _parse_start(args.start, args.scenario)
    events = generate_scenario(args.scenario, seed=args.seed, start=start)
    try:
        for result in send_batches(args.base_url, token, events):
            print(result)
    except error.HTTPError as e:
        print(f'HTTP {e.code}', file=sys.stderr)
        try:
            print(e.read().decode(), file=sys.stderr)
        except Exception:
            pass
        sys.exit(1)
    except Exception as e:
        print(str(e), file=sys.stderr)
        sys.exit(1)


if __name__ == '__main__':
    main()
