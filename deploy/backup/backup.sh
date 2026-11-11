#!/bin/bash
# ============================================================================
# Бэкап PostgreSQL (prod) — pg_dump в custom-формате + ротация.
#
# Где: работает НА ХОСТЕ прод-сервера (не в контейнере).
# Как:  bash /opt/prod/deploy/backup/backup.sh
# Cron: 10 3 * * * /opt/prod/deploy/backup/backup.sh >> /var/log/marketplace-backup.log 2>&1
#
# Переопределение (переменными окружения):
#   PROJECT_DIR=/opt/prod   BACKUP_DIR=/backups/marketplace   RETENTION_DAYS=14
#   BACKUP_MEDIA=1  — дополнительно tar-архив тома media (фото товаров)
# ============================================================================
set -euo pipefail

PROJECT_DIR="${PROJECT_DIR:-/opt/prod}"
ENV_FILE="$PROJECT_DIR/.env"
COMPOSE_FILE="$PROJECT_DIR/docker-compose.prod.yml"
BACKUP_DIR="${BACKUP_DIR:-/backups/marketplace}"
RETENTION_DAYS="${RETENTION_DAYS:-14}"
BACKUP_MEDIA="${BACKUP_MEDIA:-0}"
MIN_FREE_MB="${MIN_FREE_MB:-2048}"   # ниже этого места на диске — отказ

STAMP=$(date +%F_%H%M)
log() { echo "[$(date '+%F %T')] $*"; }

# --- защита от параллельного запуска (cron + ручной запуск) ---------------
exec 9> "/tmp/marketplace-backup.lock"
if ! flock -n 9; then
  log "ERROR: уже запущен другой экземпляр — выходим"
  exit 1
fi

# --- параметры БД из .env (свои переменные env имеют приоритет) -----------
POSTGRES_USER="${POSTGRES_USER:-$(grep -E '^POSTGRES_USER=' "$ENV_FILE" | head -1 | cut -d= -f2- | tr -d '\r"')}"
POSTGRES_DB="${POSTGRES_DB:-$(grep -E '^POSTGRES_DB=' "$ENV_FILE" | head -1 | cut -d= -f2- | tr -d '\r"')}"
if [ -z "$POSTGRES_USER" ] || [ -z "$POSTGRES_DB" ]; then
  log "ERROR: не удалось прочитать POSTGRES_USER/POSTGRES_DB из $ENV_FILE"
  exit 1
fi
if [ ! -f "$COMPOSE_FILE" ]; then
  log "ERROR: не найден $COMPOSE_FILE (PROJECT_DIR=$PROJECT_DIR?)"
  exit 1
fi

# --- место на диске ---------------------------------------------------------
free_mb=$(df -Pm "$BACKUP_DIR" 2>/dev/null | awk 'NR==2 {print $4}' || echo 0)
if [ "${free_mb:-0}" -lt "$MIN_FREE_MB" ]; then
  log "ERROR: на разделе $BACKUP_DIR свободно ${free_mb} МБ < ${MIN_FREE_MB} МБ — бэкап не запускаю"
  exit 1
fi

mkdir -p "$BACKUP_DIR"

# --- дамп БД: сначала во временный файл, валидация, потом атомарный mv -----
DUMP="$BACKUP_DIR/marketplace_$STAMP.dump"
TMP="$DUMP.tmp"

log "pg_dump: $POSTGRES_DB (custom format) -> $DUMP"
docker compose -f "$COMPOSE_FILE" exec -T db \
  pg_dump -U "$POSTGRES_USER" -Fc "$POSTGRES_DB" > "$TMP"

size_h=$(du -h "$TMP" | cut -f1)

# валидация: заголовок архива должен читаться pg_restore
if ! docker compose -f "$COMPOSE_FILE" exec -T db \
  pg_restore -l < "$TMP" > /dev/null; then
  log "ERROR: дамп не прошёл валидацию (pg_restore -l) — удаляю битый файл"
  rm -f "$TMP"
  exit 1
fi
mv "$TMP" "$DUMP"
log "backup ok: $DUMP ($size_h)"

# --- (опция) том media: tar через контейнер backend (том смонтирован) ------
if [ "$BACKUP_MEDIA" = "1" ]; then
  MEDIA="$BACKUP_DIR/media_$STAMP.tar.gz"
  docker compose -f "$COMPOSE_FILE" exec -T backend \
    tar czf - -C /app/media . > "$MEDIA.tmp"
  if ! tar -tzf "$MEDIA.tmp" > /dev/null 2>&2; then
    log "ERROR: media-архив битый — удаляю"
    rm -f "$MEDIA.tmp"
    exit 1
  fi
  mv "$MEDIA.tmp" "$MEDIA"
  log "media ok: $MEDIA ($(du -h "$MEDIA" | cut -f1))"
fi

# --- ротация ---------------------------------------------------------------
find "$BACKUP_DIR" -name "marketplace_*.dump"     -mtime +"$RETENTION_DAYS" -delete
[ "$BACKUP_MEDIA" = "1" ] && find "$BACKUP_DIR" -name "media_*.tar.gz" -mtime +"$RETENTION_DAYS" -delete

log "done (retention ${RETENTION_DAYS} дн.)"
