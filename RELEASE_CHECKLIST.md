Release Checklist (MVP v0)

Environment variables
- Copy `.env.prod.example` to `.env.prod` and fill: `BOT_TOKEN`, `ADMIN_API_KEY`, `SENTRY_DSN`, `POSTGRES_*`, `REDIS_URL`.
- Set `LLM_PROVIDER`, `LLM_BASE_URL`, `LLM_API_KEY` (if real LLM).
- Review limits: `DRAFTS_PER_DAY`, `PUBLISHES_PER_DAY`, `PUBLISHES_PER_HOUR`, `LLM_CALLS_PER_DAY`.

Start / Update / Migrations
- Start: `docker compose -f docker-compose.prod.yml up -d --build`
- Migrate: `docker compose -f docker-compose.prod.yml run --rm api alembic upgrade head`
- Update: `./scripts/update_prod.sh`

Backups
- Run: `ENV_FILE=.env.prod ./scripts/backup_postgres.sh`
- Retention: set `RETENTION_DAYS` in cron.
- Cron example in `README.md`.

Monitoring / Errors
- Sentry enabled when `SENTRY_DSN` is set.
- API health: `GET /healthz`.
- Worker errors flow to Sentry via `celery_app`.

Limits / Quotas / Safety
- Safe mode defaults: `safe_mode=true`, `autopost_enabled=false`.
- LLM calls capped per day via `LLM_CALLS_PER_DAY`.
- Draft and publish quotas enforced via Redis.
- Rate limit per hour for publishes via `PUBLISHES_PER_HOUR`.
- Source sanitization enabled before LLM.

Critical behaviors to verify
- `publish_due` idempotency (unique scheduled publish).
- RSS/URL dedup works by `external_id` and `link`.
- Safe mode routes drafts to approval queue (`needs_approval`).

Smoke scenario
- Start stack, check `/healthz`.
- Add a test channel (bot has publish rights).
- Add a source, run fetch, generate a draft, approve and publish.
