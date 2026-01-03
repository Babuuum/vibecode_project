PYPROJECT=pyproject.toml

.PHONY: install fmt lint test up down logs migrate precommit health

install:
	poetry install --with dev,test

fmt:
	poetry run ruff format .

lint:
	poetry run ruff check .
	poetry run mypy src tests

test:
	poetry run pytest

up:
	docker compose up -d --build

down:
	docker compose down

logs:
	docker compose logs -f

migrate:
	poetry run alembic upgrade head

precommit:
	poetry run pre-commit run --all-files

health:
	curl -f http://localhost:8000/healthz
