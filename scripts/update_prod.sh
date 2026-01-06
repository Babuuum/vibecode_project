#!/usr/bin/env bash
set -euo pipefail

COMPOSE_FILE="${COMPOSE_FILE:-docker-compose.prod.yml}"

docker compose -f "$COMPOSE_FILE" pull
docker compose -f "$COMPOSE_FILE" run --rm api alembic upgrade head
docker compose -f "$COMPOSE_FILE" up -d --remove-orphans
