#!/bin/bash
set -euo pipefail

PROJECT_DIR=/opt/marketplace-migrator
BACKUP_DIR=/backups/marketplace
RETENTION_DAYS=7
STAMP=$(date +%F_%H%M)

mkdir -p "$BACKUP_DIR"

# Дамп в custom-формате (сжатый, выборочное восстановление)
docker compose -f "$PROJECT_DIR/docker-compose.prod.yml" exec -T db \
  pg_dump -U "$POSTGRES_USER" -Fc "$POSTGRES_DB" > "$BACKUP_DIR/marketplace_$STAMP.dump"

# Копия вне сервера (раскомментируйте под ваш storage: rclone / mc / scp)
# rclone copy "$BACKUP_DIR/marketplace_$STAMP.dump" remote:marketplace-backups/

# Ротация
find "$BACKUP_DIR" -name "marketplace_*.dump" -mtime +$RETENTION_DAYS -delete

echo "[$(date)] backup ok: marketplace_$STAMP.dump ($(du -h "$BACKUP_DIR/marketplace_$STAMP.dump" | cut -f1))"