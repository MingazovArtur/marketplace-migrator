#!/bin/bash
set -euo pipefail

PROJECT_DIR=/opt/marketplace-migrator
ENV_FILE="$PROJECT_DIR/.env"
BACKUP_DIR=/backups/marketplace
RETENTION_DAYS=7
STAMP=$(date +%F_%H%M)

POSTGRES_USER=$(grep -E '^POSTGRES_USER=' "$ENV_FILE" | head -1 | cut -d= -f2- | tr -d '\r"')
POSTGRES_DB=$(grep -E '^POSTGRES_DB='  "$ENV_FILE" | head -1 | cut -d= -f2- | tr -d '\r"')

if [ -z "$POSTGRES_USER" ] || [ -z "$POSTGRES_DB" ]; then
  echo "ERROR: не удалось прочитать POSTGRES_USER/POSTGRES_DB из $ENV_FILE" >&2
  exit 1
fi

mkdir -p "$BACKUP_DIR"

docker compose -f "$PROJECT_DIR/docker-compose.prod.yml" exec -T db \
  pg_dump -U "$POSTGRES_USER" -Fc "$POSTGRES_DB" > "$BACKUP_DIR/marketplace_$STAMP.dump"

find "$BACKUP_DIR" -name "marketplace_*.dump" -mtime +$RETENTION_DAYS -delete

echo "[$(date)] backup ok: marketplace_$STAMP.dump ($(du -h "$BACKUP_DIR/marketplace_$STAMP.dump" | cut -f1))"