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
	python manage.py create_demo_users

poc:
	python scripts/llm_poc.py

demo:
	python -m simulator.cli normal
	python -m simulator.cli brute_force
	python -m simulator.cli port_scan
	python -m simulator.cli injection
