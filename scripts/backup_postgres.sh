#!/usr/bin/env bash
set -euo pipefail

COMPOSE_FILE="${COMPOSE_FILE:-docker-compose.prod.yml}"
BACKUP_DIR="${BACKUP_DIR:-./backups}"

if [ -f .env ]; then
  set -a
  . ./.env
  set +a
fi

POSTGRES_USER="${POSTGRES_USER:-postgres}"
POSTGRES_PASSWORD="${POSTGRES_PASSWORD:-postgres}"
POSTGRES_DB="${POSTGRES_DB:-autocontent}"

mkdir -p "$BACKUP_DIR"
timestamp="$(date +%Y%m%d_%H%M%S)"
backup_path="$BACKUP_DIR/postgres_${POSTGRES_DB}_${timestamp}.sql"

PGPASSWORD="$POSTGRES_PASSWORD" docker compose -f "$COMPOSE_FILE" exec -T postgres \
  pg_dump -U "$POSTGRES_USER" "$POSTGRES_DB" > "$backup_path"

echo "Backup saved to $backup_path"
