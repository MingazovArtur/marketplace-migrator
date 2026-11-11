#!/bin/bash
# ============================================================================
# Восстановление PostgreSQL из дампа, созданного backup.sh.
#
# Как:   bash /opt/prod/deploy/backup/restore-db.sh                # список
#       bash restore-db.sh latest            # последний по времени дамп
#       bash restore-db.sh marketplace_2026-11-10_0310.dump
#       bash restore-db.sh latest --yes      # без вопроса-подтверждения
#
# Что делает:
#   1) останавливает «писателей» (backend, celery*, redis не трогаем, db живёт)
#   2) pg_restore --clean --if-exists (пересоздаёт объекты в существующей БД)
#   3) поднимает сервисы обратно и проверяет /api/health
#
# ⚠️ Данные в БД на момент восстановления УДАЛЯЮТСЯ и заменяются данными
#    из дампа. Перед запуском сделай свежий backup.sh (будет что вернуть).
# ============================================================================
set -euo pipefail

PROJECT_DIR="${PROJECT_DIR:-/opt/prod}"
ENV_FILE="$PROJECT_DIR/.env"
COMPOSE_FILE="$PROJECT_DIR/docker-compose.prod.yml"
BACKUP_DIR="${BACKUP_DIR:-/backups/marketplace}"
WRITERS="backend celery celery_xlsx celery_specs"

log() { echo "[$(date '+%F %T')] $*"; }

POSTGRES_USER=$(grep -E '^POSTGRES_USER=' "$ENV_FILE" | head -1 | cut -d= -f2- | tr -d '\r"')
POSTGRES_DB=$(grep -E '^POSTGRES_DB=' "$ENV_FILE" | head -1 | cut -d= -f2- | tr -d '\r"')

# --- выбор дампа ------------------------------------------------------------
if [ $# -lt 1 ]; then
  echo "Доступные бэкапы в $BACKUP_DIR:"
  ls -lh "$BACKUP_DIR"/marketplace_*.dump 2>/dev/null || echo "  (пусто)"
  echo
  echo "Использование: restore-db.sh <файл.dump | latest> [--yes]"
  exit 1
fi

DUMP_NAME="$1"
ASSUME_YES="${2:-}"
if [ "$DUMP_NAME" = "latest" ]; then
  DUMP_NAME=$(ls -1t "$BACKUP_DIR"/marketplace_*.dump 2>/dev/null | head -1 || true)
  if [ -z "$DUMP_NAME" ]; then
    log "ERROR: в $BACKUP_DIR нет дампов"
    exit 1
  fi
  DUMP_NAME=$(basename "$DUMP_NAME")
fi
DUMP="$BACKUP_DIR/$DUMP_NAME"
if [ ! -f "$DUMP" ]; then
  log "ERROR: файл не найден: $DUMP"
  exit 1
fi

# валидация архива ДО остановки сервисов
if ! docker compose -f "$COMPOSE_FILE" exec -T db pg_restore -l < "$DUMP" > /dev/null; then
  log "ERROR: дамп не читается (pg_restore -l) — восстановление отменено"
  exit 1
fi

log "Восстановление: $DUMP ($(du -h "$DUMP" | cut -f1)) -> БД $POSTGRES_DB"
log "⚠️  Текущие данные БД будут заменены данными из дампа."
if [ "$ASSUME_YES" != "--yes" ]; then
  read -r -p "Продолжать? [yes/N] " answer
  case "$answer" in
    yes|Yes|YES|y|Y) ;;
    *) log "Отменено"; exit 1 ;;
  esac
fi

# --- стоп «писателей» (db остаётся работать) -------------------------------
log "останавливаю: $WRITERS"
docker compose -f "$COMPOSE_FILE" stop $WRITERS

restore_ok=0
if docker compose -f "$COMPOSE_FILE" exec -T db \
  pg_restore -U "$POSTGRES_USER" --dbname "$POSTGRES_DB" --clean --if-exists --no-owner < "$DUMP"; then
  restore_ok=1
fi

log "поднимаю сервисы обратно"
docker compose -f "$COMPOSE_FILE" up -d $WRITERS

if [ "$restore_ok" != "1" ]; then
  log "ERROR: pg_restore завершился с ошибками — смотри вывод выше."
  log "Возможные причины: миграции alembic новее, чем схема в дампе."
  log "Бэкап до восстановления уже сохранён? Если нет — сейчас сделать нельзя: данные перезаписаны частично."
  exit 1
fi

sleep 5
if curl -fsS http://127.0.0.1/api/health > /dev/null 2>&1; then
  log "OK: восстановлено, /api/health отвечает"
else
  log "WARN: /api/health не ответил за 5 с — проверь: docker compose -f $COMPOSE_FILE ps"
fi
