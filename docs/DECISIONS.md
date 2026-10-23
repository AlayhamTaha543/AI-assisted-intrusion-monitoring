# Decisions

## Ollama tool result key
Tool results are sent back with `tool_name` (not `name`) because that is the message
shape expected by the Ollama chat API. Tool call names are read defensively from
either dict or object responses.

## Ingestion with `bulk_create(ignore_conflicts=True)`
Submitted events are inserted in one batch and duplicate `event_id` rows are ignored
by the database unique constraint. Deduplication therefore remains race-safe without
a per-event lookup, and alerts are computed only from the events actually stored.

## `runserver --insecure` is local-only
The local/demo setup serves static files through `runserver --insecure`. This is for
development convenience only and must not be used in production.

## Investigation error codes
| Code | Meaning |
| --- | --- |
| `llm_unavailable` | Ollama could not be reached after transient retries |
| `llm_error` | Ollama returned an unexpected/API error |
| `invalid_output` | Model output failed schema validation |
| `time_limit` | Celery soft time limit interrupted the task |
| `unexpected_error` | Any other unhandled task exception |
| `queue_unavailable` | The task could not be enqueued; the alert is marked failed |

## Step 0 results
Pending owner run with an Ollama model available. Run `python scripts/llm_poc.py`;
it appends a results table with tool call, valid JSON, latency, and model tag here.

| Run | Tool called | Valid JSON | Latency (ms) | Model |
| --- | --- | --- | --- | --- |
| _pending_ | | | | |
