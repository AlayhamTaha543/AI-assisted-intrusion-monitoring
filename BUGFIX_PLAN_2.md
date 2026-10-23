# BUGFIX_PLAN_2.md: Remaining fixes

> **Audience:** opencode. **Source:** a second independent test run of your fixed project (PostgreSQL, Redis, Celery worker, Django API, and a fake Ollama server).
> Round 1 fixes that were verified working (do not touch): timeout, tool context, injection cleaning, conditional writes, broker-down latency, health 503, `first_seen_at`, filters, `event_id`, admin, detection logic.
> This plan covers **only what is still wrong or missing**.

---

## 0. Rules

1. **Do only what this plan says.** No new features, dependencies, or refactors.
2. Work in the order R1 to R9. After each item, run the **full** suite on PostgreSQL (`make test`) and keep it green.
3. **Every fix ships with the test that proves it, in the same commit.** Never weaken or delete an existing test.
4. Tests use mocks for Ollama (patch `agent.investigator.ollama.Client` or `agent.tasks.investigate`). Never call a real model in default tests.
5. Do not log prompts, payloads, or secrets.

### Commit rules (clean history)

- **You may commit.** Make **one commit per item** (R1 to R9; R8 may be split into the groups listed there). Each commit contains the fix and its tests together.
- Commit only when the item's gate is green and `git status` shows nothing unrelated.
- Message format: `<type>(<scope>): <summary>` with a short body that names the item. Types: `fix`, `test`, `chore`, `docs`. Example:
  ```text
  fix(ingest): reject NUL characters in raw payload

  R1: json.dumps escapes NUL as the text \u0000, so the old check never matched.
  Adds test_raw_with_nul_rejected.
  ```
- No `WIP`, `fix stuff`, or "address review" commits. If you need to correct your own commit before moving on, use `git commit --amend` on the latest commit only.
- **Do not** rewrite or squash earlier commits, force-push, or change history before this work.
- Never commit `.env`, `venv/`, `db.sqlite3`, `__pycache__/`, or `.pytest_cache/`.
- First, tidy the working tree: commit the pending deletion of `BUGSFIX_PLAN.md` as `chore: remove obsolete bugfix plan`, then add this file as `docs: add BUGFIX_PLAN_2`.
- Finish by printing `git log --oneline` and `git status`.

---

## R1. A NUL character in `raw` still returns HTTP 500

**Evidence (reproduced):** `POST /api/events/` with `"raw": {"k": "a\u0000b"}` returns 500. In `events/serializers.py`, `validate_raw` checks `'\u0000' in s or '\x00' in s`, but those literals are the NUL **character**, while `json.dumps` writes the **text** `\u0000` (backslash, `u`, `0000`). The check can never match. PostgreSQL then rejects the JSONB.

**Fix:** check for the escaped text: `if '\\u0000' in s:` raise `ValidationError`. Keep the length check. Also reject a NUL inside dictionary keys (covered by the same string check).

**Tests** (`tests/test_ingest.py`)
- `test_raw_with_nul_rejected`: NUL in a value gives 400 and no rows stored.
- `test_raw_with_nul_in_key_rejected`: NUL in a key gives 400.
- `test_raw_normal_object_accepted`: `{"k": "v"}` gives 201.

---

## R2. A dropped connection is not treated as transient

**Evidence (reproduced):** when the Ollama server closes the connection mid-request (`httpx.RemoteProtocolError`, as when Ollama crashes or restarts), the task records `unexpected_error` after **one** attempt. It should retry once and end as `llm_unavailable`.

**Fix** (`agent/investigator.py`): replace the tuple `(ConnectionError, httpx.ConnectError, httpx.TimeoutException)` with `(ConnectionError, httpx.TransportError)` in **both** `try` blocks. (`httpx.TransportError` is the parent of connect, timeout, read, write, and protocol errors.) Put the tuple in one module constant `TRANSIENT_ERRORS` and use it in both places.

**Tests** (`tests/test_investigation_task.py`; patch `agent.investigator.ollama.Client` and `time.sleep`)
- `test_remote_protocol_error_is_transient`: `chat` raises `httpx.RemoteProtocolError` on both calls; alert ends `failed`, `investigation_error == 'llm_unavailable'`, `investigation_attempts == 2`.
- `test_read_error_then_success`: first call raises `httpx.ReadError`, second attempt succeeds; alert `completed`, `investigation_attempts == 2`.
- `test_response_error_not_retried`: `ollama.ResponseError` gives `llm_error`, `investigation_attempts == 1`.
- `test_invalid_json_not_retried`: invalid JSON gives `invalid_output`, exactly 2 `chat` calls, attempts 1.

---

## R3. `time_limit` is never recorded

**Evidence (reproduced):** `SoftTimeLimitExceeded` raised inside `investigate()` is caught by the inner `except Exception` in `run_investigation`, so the alert gets `unexpected_error` instead of `time_limit`.

**Fix** (`agent/tasks.py`): in the retry loop, add `except SoftTimeLimitExceeded: raise` **before** the `except Exception:` clause, so the existing outer handler records `time_limit`.

**Tests**
- `test_soft_time_limit_recorded`: patch `agent.tasks.investigate` to raise `SoftTimeLimitExceeded`; call `run_investigation.run(alert_id)` on a `queued` alert; alert is `failed` with `investigation_error == 'time_limit'` and the task does not raise.
- `test_unexpected_error_still_contained`: a `RuntimeError` gives `unexpected_error`, one attempt, no raise.

---

## R4. `make users` and `make demo` run on the host and will not work with Compose

**Evidence (config review):** `make users` runs `python manage.py create_demo_users` on the host, but `db` publishes no port and `.env` sets `POSTGRES_HOST=db`. `make demo` needs `INGEST_TOKEN` exported and the README does not say so.

**Fix**
- Makefile:
  ```make
  users:
  	docker compose exec api python manage.py create_demo_users

  demo:
  	docker compose exec -e INGEST_TOKEN=$(INGEST_TOKEN) api sh -c 'for s in normal brute_force port_scan injection; do python -m simulator.cli $$s; done'
  ```
  `make demo` must fail with a clear message if `INGEST_TOKEN` is empty (`test -n "$(INGEST_TOKEN)" || (echo "usage: INGEST_TOKEN=<key> make demo" && exit 1)`).
- README setup section: `make up`, `make users` (copy `INGEST_TOKEN`), `INGEST_TOKEN=<key> make demo`, then open `/admin/`.

**Tests** (`tests/test_deploy_config.py`, plain text checks)
- `test_make_users_and_demo_use_compose`: the `users` and `demo` recipes contain `docker compose exec` and do not start with a bare `python`.
- `test_readme_documents_demo_flow`: README contains `INGEST_TOKEN=` and `make users`.
- Manual: with the stack up, `make users` prints tokens; `INGEST_TOKEN=<key> make demo` exits 0.

---

## R5. `make users` silently rotates the analyst password on every run

**Evidence (reproduced):** running `create_demo_users` twice prints two different `ANALYST_PASSWORD` values and the first one stops working.

**Fix** (`events/management/commands/create_demo_users.py`): set a password **only** when the user is created, or when `DEMO_USER_PASSWORD` is set. If the user exists and no env password is given, leave the password unchanged and print `ANALYST_PASSWORD=(unchanged)`. Same for `ingestor1`. Rewrite the duplicated branches into one small helper.

**Tests** (`tests/test_demo_users.py`)
- `test_create_demo_users_prints_tokens`: output contains `INGEST_TOKEN=` and `ANALYST_TOKEN=`, matching the DB.
- `test_second_run_keeps_password`: run twice (capture output); the password printed by the first run still logs in via `client.login`.
- `test_env_password_applied`: with `DEMO_USER_PASSWORD=abc12345XYZ` set, the analyst can log in with it.
- `test_analyst_group_has_view_alert`: `analyst1` has `alerts.view_alert`.

---

## R6. Fresh clone: `make up` crashes because of the placeholder secret key

**Evidence (reproduced):** `make env` copies `.env.example` unchanged (`DJANGO_SECRET_KEY=replace-me`). The new check in `settings.py` then raises `ImproperlyConfigured`, so `migrate`, `api`, and `worker` all crash on a fresh clone.

**Fix** (Makefile `env` target): generate a random key when creating `.env`:
```make
env:
	@test -f .env || (cp .env.example .env && \
	  KEY=$$(python3 -c "import secrets; print(secrets.token_urlsafe(48))") && \
	  sed -i.bak "s|^DJANGO_SECRET_KEY=.*|DJANGO_SECRET_KEY=$$KEY|" .env && rm -f .env.bak)
```
Keep the settings check as is.

**Tests**
- `test_secret_key_required_when_not_debug` (`tests/test_settings.py`): with `DJANGO_SECRET_KEY` unset or `replace-me` and `DJANGO_DEBUG=false`, importing settings in a subprocess (`python -c "import config.settings"`) exits non-zero with `ImproperlyConfigured`; with a real key it exits 0.
- `test_make_env_generates_key` (text check): the Makefile `env` recipe replaces `DJANGO_SECRET_KEY`.
- Manual: `rm .env && make env && grep DJANGO_SECRET_KEY .env` shows a random value; `make up` starts cleanly.

---

## R7. Simulator is not deterministic

**Evidence (reproduced):** `simulator/generator.py` is unchanged: no `--seed` or `--start`, random `uuid4` IDs, so a rerun stores 40 more events (80 stored for one `brute_force` run twice).

**Fix** (`simulator/generator.py`, `simulator/cli.py`)
- Pure functions `generate_scenario(name, seed, start) -> list[dict]` (no network). Use `rng = random.Random(seed)` and IDs `str(uuid.UUID(int=rng.getrandbits(128), version=4))`. Use `datetime.now(timezone.utc)` (not `utcnow()`).
- CLI: add `--seed` (default 42) and `--start` (ISO timestamp; default now minus the scenario duration). Send in chronological batches of at most `MAX_BATCH_SIZE`. Remove the unused `traceback` and `urllib.request` imports.
- Keep the scenario IPs and shapes as they are today (`continue_attack` already uses the `brute_force` IP).

**Tests** (`tests/test_simulator.py`)
- `test_same_seed_same_events`, `test_different_seed_different_ids`.
- `test_ids_unique`, `test_chronological`, `test_not_in_future`.
- `test_all_events_pass_serializer`: every event validates with `LogEventSerializer`.
- `test_normal_creates_no_alert`: ingest `normal`; zero alerts.
- `test_brute_force_shape`: 40 failures, 8 usernames, span at most 60 s. `test_port_scan_shape`: 50 distinct ports.
- `test_injection_payload_present`: exactly one username contains `ignore previous instructions`.
- `test_rerun_same_seed_is_idempotent`: ingest `brute_force` twice with the same seed and start; stored events unchanged after the second run; still one alert; second response has `inserted == 0`.

---

## R8. Test suite: 5 smoke tests, one of them vacuous

**Evidence:** `tests/test_health.py` now asserts `status_code in [200, 503]`, which always passes. No tests were added for the earlier fixes, so nothing prevents regressions. Add the tests below (some are specified in R1 to R7; do not duplicate them). Use helpers in `tests/conftest.py` (`make_events`, `post_events`, an alert factory). Commit in these groups:

**R8a, health and settings** (`tests/test_health.py`, `tests/test_settings.py`) (replace the vacuous test)
- `test_health_ok`: patch the Redis ping to succeed; 200, `db` and `redis` true.
- `test_health_redis_down_503`: ping raises; 503, `status == 'degraded'`.
- `test_health_db_down_503`: patch the DB execute to raise; 503.
- `test_health_uses_redis_timeouts`: `redis.from_url` called with `socket_connect_timeout` and `socket_timeout`.
- `test_celery_settings`: soft limit 270, hard 300, `acks_late` false, prefetch 1, `task_ignore_result` true, publish retry false.

**R8b, ingestion and alert API** (`tests/test_ingest.py`, `tests/test_alert_api.py`)
- `test_bytes_sent_overflow_400`, `test_event_id_required_400`, `test_error_names_item_index`, `test_batch_too_large_400`, `test_future_and_too_old_timestamp_400`.
- `test_duplicate_batch_inserts_zero`: second post `inserted == 0`, `duplicates == n`, no new rows.
- `test_duplicate_race_returns_201`: patch the "already stored" lookup to return an empty set while the rows exist; response 201, one row per `event_id`.
- `test_page_size_invalid_400` (`abc`, `0`, `-5`), `test_page_size_capped_100`, `test_source_ip_filter_invalid_400`, `test_source_ip_filter_ipv6_normalized`.
- `test_time_filters_work_and_reject_garbage`, `test_filters_combine_with_and`.
- `test_patch_non_object_body_400`, `test_patch_extra_field_400`, `test_status_transitions` (including `resolved` to `open` gives 400, `status_changed_by` set).
- `test_role_permissions`: ingestor cannot read or patch alerts; analyst cannot ingest; anonymous gets 401.

**R8c, detection** (`tests/test_detection.py`)
- `test_exact_thresholds` (parametrize: 19 vs 20 failed logins; 14 vs 15 distinct ports).
- `test_sliding_window_crosses_minute_boundary`, `test_events_70s_apart_do_not_combine`, `test_same_port_20_times_not_scan`, `test_split_batches_detected`.
- `test_continued_attack_updates_one_incident_no_second_investigation`.
- `test_resolved_then_new_incident`, `test_ipv6_normalized`.
- `test_first_seen_is_earliest_event` and `test_last_seen_never_moves_backwards`.
- `test_integrity_race_handled`: patch the initial lookup to return `None` while an active alert exists; no exception, still one alert.
- `test_brute_force_evidence_and_severity` and `test_port_scan_evidence_and_severity` (exact evidence keys, integer `distinct_usernames`).

**R8d, agent and task** (`tests/test_agent.py`, `tests/test_investigation_task.py`, `tests/test_admin.py`)
- `test_client_built_with_host_and_timeout`: `ollama.Client` called with `host` and `timeout` from settings; `options` has `temperature == 0` and no `timeout` key.
- `test_tool_works_when_previous_alert_exists`: valid JSON tool message, `used_tool is True`.
- `test_no_dangling_tool_call_on_tool_failure`: tool function raises; no assistant tool-call message without a following tool message.
- `test_tool_message_has_tool_name`, `test_tool_scoped_to_alert_ip_and_read_only`, `test_tool_respects_limits`.
- `test_system_prompt_marks_data_untrusted`, `test_username_control_chars_cleaned`, `test_ai_output_cleaned_and_truncated`.
- `test_injection_cannot_change_backend_fields`: ingest the `injection` scenario, run the task with a scripted model that "obeys" it; `severity`, `evidence`, `rule_name`, `source_ip`, `mitre_id`, `incident_status` unchanged.
- `test_claim_runs_once`: calling the task twice calls `investigate` once.
- `test_result_discarded_if_status_reset_mid_run`: `investigate` resets the alert to `queued` during the call; afterwards the alert is `queued` with empty `ai_summary`.
- `test_queue_failure_returns_201_and_marks_alert`: `apply_async` raises; ingestion returns 201; alert `failed/queue_unavailable`; evidence intact.
- `test_dispatch_not_called_before_commit` and `test_dispatch_not_called_on_rollback` (use `django_capture_on_commit_callbacks`).
- Admin: `test_analyst_can_view_alerts_in_admin`, `test_admin_is_read_only` (add and delete give 403), `test_admin_escapes_ai_text` (`<script>` stored in `ai_summary` renders as `&lt;script&gt;`), `test_admin_sections_present`, `test_rerun_requeues_failed_and_skips_completed`, `test_rerun_clears_ai_fields`.

**Mutation check (do once, do not commit):** change the brute-force comparison in `detection/rules.py` from `<` to `<=`; `test_exact_thresholds` must fail. Revert.

---

## R9. Cleanup and documentation

**Evidence:** `pyflakes` reports 9 unused imports/variables; `docs/DECISIONS.md` is two lines; `scripts/llm_poc.py` records no results; `db.sqlite3` and `venv/` are still in the project folder.

**Fix**
- Remove every item `python -m pyflakes config events alerts detection agent simulator scripts tests` reports (`config/urls.py`, `alerts/models.py`, `simulator/cli.py`, `simulator/generator.py`, and the test files).
- Delete `db.sqlite3` and `venv/` from the working tree. Add `.pytest_cache/` and `celerybeat-schedule*` to `.gitignore`.
- `docs/DECISIONS.md`: record, in a few lines each, the Ollama `tool_name` message key, `bulk_create(ignore_conflicts=True)` ingestion, `runserver --insecure` for local development only, the error-code mapping (`llm_unavailable`, `llm_error`, `invalid_output`, `time_limit`, `unexpected_error`, `queue_unavailable`), and a `## Step 0 results` section left for the owner.
- `scripts/llm_poc.py`: after its runs, append a small results table (tool called, valid JSON, latency, model tag) under `## Step 0 results` in `docs/DECISIONS.md`.

**Tests**
- `test_docs.py`: `DECISIONS.md` contains `tool_name`, `ignore_conflicts`, and `llm_unavailable`; README contains `Limitations`.
- Gate: `python -m pyflakes ...` prints nothing; `git ls-files | grep -E "venv|sqlite"` prints nothing.

---

## Final acceptance (all must hold)

1. `make test` is green; the suite has well over the original 5 tests and every item above has its test.
2. `rm .env && make up` starts every service; `make users` prints tokens; `INGEST_TOKEN=<key> make demo` exits 0.
3. `POST` with NUL in `raw` returns 400 (never 500).
4. With Ollama's connection dropped, the alert ends `failed/llm_unavailable` after 2 attempts.
5. A soft time limit leaves `investigation_error == 'time_limit'`.
6. Running `create_demo_users` twice keeps the analyst password valid.
7. Running `brute_force` twice with the same seed stores each event once.
8. `pyflakes` is clean and `git log --oneline` shows one clear commit per item with no WIP commits.
