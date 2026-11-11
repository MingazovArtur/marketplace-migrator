# Бэкапы и восстановление (прод)

Два скрипта (работают на хосте прод-сервера):

| Скрипт | Что делает |
|---|---|
| `backup.sh` | `pg_dump` (custom-формат) → `/backups/marketplace/`, валидация архива, ротация 14 дней |
| `restore-db.sh` | Восстановление БД из дампа: стоп «писателей» → `pg_restore --clean` → проверка `/api/health` |

Оба читают `POSTGRES_USER` / `POSTGRES_DB` из `/opt/prod/.env`.

## 1. Установка (один раз)

```bash
cd /opt/prod
git pull   # скрипты лежат в deploy/backup/
mkdir -p /backups/marketplace
```

## 2. Cron — каждую ночь в 03:10

```bash
crontab -e
# добавить строку:
10 3 * * * /opt/prod/deploy/backup/backup.sh >> /var/log/marketplace-backup.log 2>&1
```

Первый раз запусти руками и посмотри лог:

```bash
bash /opt/prod/deploy/backup/backup.sh
tail -5 /var/log/marketplace-backup.log   # при ручном запуске вывод идёт в консоль
```

Должно быть: `backup ok: .../marketplace_YYYY-MM-DD_HHMM.dump (размер)`.

## 3. Что делает backup.sh

- **pg_dump -Fc** (custom-формат: сжатие + можно восстановить выборочно);
- дамп сначала пишется в `.tmp`, **валидируется** (`pg_restore -l`) и только потом
  переименовывается — битый/оборванный дамп не останется под финальным именем;
- **ротация**: хранит последние 14 дней (`RETENTION_DAYS`);
- защита от параллельного запуска (`flock`);
- отказ при свободном месте < 2 ГБ (`MIN_FREE_MB`), чтобы диск не забился;
- `(опция) BACKUP_MEDIA=1` — дополнительно tar-архив тома `media` (фото товаров);
  по умолчанию выключено: фото перекачиваются с площадок, БД — источник истины.

Переопределение параметров — переменными окружения:

```bash
BACKUP_MEDIA=1 RETENTION_DAYS=30 bash /opt/prod/deploy/backup/backup.sh
```

## 4. Восстановление

```bash
bash /opt/prod/deploy/backup/restore-db.sh              # покажет список дампов
bash /opt/prod/deploy/backup/restore-db.sh latest       # последний дамп, с вопросом
bash /opt/prod/deploy/backup/restore-db.sh marketplace_2026-11-10_0310.dump --yes
```

Что происходит: останавливаются `backend` + все `celery*` (чтобы никто не писал),
дамп проверяется, `pg_restore --clean --if-exists` пересоздаёт объекты в БД,
сервисы поднимаются, проверяется `/api/health`. Redis не трогается.

⚠️ **Данные БД на момент восстановления заменяются данными из дампа.**
Перед восстановлением (если прод ещё жив) — сделай свежий бэкап: будет что вернуть.

## 5. Куда смотреть, если что-то не так

```bash
tail -50 /var/log/marketplace-backup.log        # история бэкапов
ls -lh /backups/marketplace/                    # файлы и размеры
df -h /backups                                  # не кончилось ли место
docker compose -f /opt/prod/docker-compose.prod.yml ps
```

## 6. Проверка восстановления (репетиция, раз в квартал)

Лучший тест бэкапа — восстановить его. Без риска для прода:

```bash
# поднимаем копию БД на другом порте и восстанавливаем туда
docker run -d --name restore-test -e POSTGRES_PASSWORD=test -p 55432:5432 postgres:15
cat /backups/marketplace/marketplace_<дата>.dump | \
  docker exec -i restore-test pg_restore -U postgres --dbname postgres --clean --if-exists --no-owner
docker exec -it restore-test psql -U postgres -c "SELECT count(*) FROM products;"
docker rm -f restore-test
```

Если `restore-test` поднялся и таблицы читаются — бэкапы реально рабочие.
