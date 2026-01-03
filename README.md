# AutoContent TG (MVP)

Bootstrap for the AutoContent Telegram project with FastAPI API, aiogram bot, async SQLAlchemy, Alembic, Celery, Redis, and Postgres.

## Requirements
- Python 3.12
- Poetry
- Docker + Docker Compose

## Setup
```bash
cp .env.example .env
poetry install --with dev,test
pre-commit install
```

## Make targets
- `make fmt` — format with ruff.
- `make lint` — ruff check + mypy.
- `make test` — run pytest (async enabled).
- `make up` / `make down` — docker compose stack.
- `make logs` — tail docker compose logs.
- `make health` — HTTP health probe.
- `make migrate` — run Alembic migrations.

## Run locally
```bash
poetry run uvicorn autocontent.api.main:app --host 0.0.0.0 --port 8000 --reload
```

Bot and worker entrypoints are available via scripts:
- `poetry run autocontent-bot`
- `poetry run autocontent-worker`

## Docker
```bash
make up
# API: http://localhost:8000/healthz
```

## Migrations
- Placeholder: add Alembic revisions under `migrations/versions/` and run `make migrate`.
