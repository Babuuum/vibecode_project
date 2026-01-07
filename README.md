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
poetry run uvicorn src.autocontent.api.main:app --host 0.0.0.0 --port 8000 --reload
```

Bot and worker entrypoints are available via scripts:
- `poetry run autocontent-bot`
- `poetry run autocontent-worker`

## Docker
```bash
make up
# API: http://localhost:8000/healthz
```

## Production
Create a production env file:
```bash
cp .env.prod.example .env.prod
```

Use the production compose file and the update script:
```bash
./scripts/update_prod.sh
```

Postgres backup (host cron):
```bash
ENV_FILE=.env.prod ./scripts/backup_postgres.sh
```

Example cron (daily at 03:15):
```
15 3 * * * ENV_FILE=/path/to/project/.env.prod RETENTION_DAYS=7 /bin/bash /path/to/project/scripts/backup_postgres.sh >> /path/to/project/backups/cron.log 2>&1
```

### Runbook
Update:
1) `git pull`
2) `docker compose -f docker-compose.prod.yml up -d --build`
3) `docker compose -f docker-compose.prod.yml run --rm api alembic upgrade head`
4) Smoke: `curl -fsS http://localhost:8000/healthz`

Rollback (minimal):
1) `git checkout <known-good-commit>`
2) `docker compose -f docker-compose.prod.yml up -d --build`
3) `docker compose -f docker-compose.prod.yml run --rm api alembic upgrade head`

Smoke scenario (real or mock):
1) Add a test channel and ensure bot has publish rights.
2) Add a source, run `Fetch now`, generate a draft, and approve/publish via bot.
3) Or call admin API to publish a known draft: `POST /admin/drafts/{id}/publish` with `X-API-Key`.

## Migrations
- Placeholder: add Alembic revisions under `migrations/versions/` and run `make migrate`.
