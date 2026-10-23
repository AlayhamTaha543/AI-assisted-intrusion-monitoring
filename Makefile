up:
	docker compose up --build

down:
	docker compose down

logs:
	docker compose logs -f

test:
	pytest

users:
	python manage.py create_demo_users

poc:
	python scripts/llm_poc.py

demo:
	python -m simulator.cli normal
