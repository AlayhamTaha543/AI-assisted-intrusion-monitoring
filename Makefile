env:
	test -f .env || cp .env.example .env

up: env
	docker compose up --build

down:
	docker compose down

logs:
	docker compose logs -f

test:
	docker compose run --rm api pytest

users:
	docker compose exec api python manage.py create_demo_users

poc:
	python scripts/llm_poc.py

demo:
	@test -n "$(INGEST_TOKEN)" || (echo "usage: INGEST_TOKEN=<key> make demo" && exit 1)
	docker compose exec -e INGEST_TOKEN=$(INGEST_TOKEN) api sh -c 'for s in normal brute_force port_scan injection; do python -m simulator.cli $$s; done'
