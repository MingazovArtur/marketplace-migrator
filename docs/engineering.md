# Инженерные основы: разработка, тесты, CI, гигиена репозитория

Этот документ — единая точка входа для инженерных практик проекта.
Патч «Неделя 4: инженерные основы» (код-ревью): тесты, CI, pre-commit,
разбиение монолитных файлов, DNS-pinning в SSRF-защите, чистка репозитория.

---

## 1. Локальная разработка

### Первый запуск

```bash
# backend
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt -r requirements-dev.txt
cp ../.env.example ../.env   # и заполнить секреты

# frontend
cd frontend
npm ci
```

### Тесты

```bash
cd backend
make test          # или: python -m pytest

cd ../frontend
npm run test       # Vitest: хук debounce, чистые функции api/client, useProducts
```

Тесты не требуют БД, Redis и интернета: покрывают чистую логику
(SSRF-валидация и DNS-pinning, шифрование Celery-payload, денежные
преобразования Decimal→float, восстановление зависших статусов, хелперы
генерации XLSX). Фронтенд-тесты (Vitest + Testing Library, jsdom) тоже
без сети — API замокан. Новая функциональность без тестов — не мержится.

### Линтеры

```bash
cd backend
make lint          # CI-гейт: только критические правила (E9,F63,F7,F82)
make lint-full     # полный набор из pyproject.toml (весь код пока не проходит)
make format        # black + ruff --fix

cd ../frontend
npm run lint       # eslint
npm run format     # prettier
```

**Текущий долг по стилю** (полный набор ruff): ~400 замечаний в старом коде —
в основном `W293/W292` (пробелы/переводы строк), `B008` (FastAPI `Depends()` в
дефолтах — норма для FastAPI), `UP006/UP035` (старые аннотации), `I001`
(сортировка импортов). План:

1. CI гейтится только на `E9,F63,F7,F82` (падения и критические ошибки);
2. новые файлы обязаны проходить полный набор (все файлы недели 4 проходят);
3. долг закрывается постепенно: `ruff check --fix` по каталогу за PR
   (`routers/`, затем `services/`, затем `parsers/`), один каталог — один PR.

### Pre-commit

```bash
pip install pre-commit
pre-commit install        # хуки на каждый коммит
pre-commit run --all-files
```

Хуки: гигиена файлов (пробелы, YAML/JSON, конфликт-маркеры, запрет файлов
>1 МБ), ruff + black (backend), eslint + prettier (frontend). Все
авто-фиксы применяются к коммиту автоматически.

**Важно (первый запуск):** `pre-commit run --all-files` и первый коммит
после установки поправят пробелы/импорты/форматирование примерно в ~100
старых файлах (долг из §1). Сделайте это ОДНИМ отдельным коммитом
`style: pre-commit autofix (whitespace, imports, formatting)` — не
смешивайте с логическими изменениями.

## 2. CI (GitHub Actions)

`.github/workflows/ci.yml`, три job'а на каждый push/PR:

| Job | Что делает |
|---|---|
| **backend** | `ruff check --select E9,F63,F7,F82 .` + `python -m pytest` (Python 3.12) |
| **frontend** | `npm ci` + `npm run lint` + `npm run test` (Vitest) + `npm run build` (Node 22) |
| **docker** | сборка `backend/Dockerfile.prod` и `frontend/Dockerfile.prod` |

Требование: **main всегда зелёный**. Красный CI — блокер для мержа.

## 3. Структура кода (после недели 4)

Семь монолитов разбиты на пакеты с сохранением публичного API импортов
(ни один импортёр не менялся):

| Было | Стало | Публичный API |
|---|---|---|
| `tasks.py` (1331 строк) | пакет `tasks/`: `recovery`, `matching`, `progress`, `migrate_tasks`, `media_tasks`, `catalog_tasks`, `export_tasks` | `from tasks import get_progress, migrate_product_task, ...` |
| `database/repository.py` (1087) | пакет `repository/`: `products`, `operation_logs`, `attributes`, `variants`, `stats` | `from database.repository import repo, op_log, attr_repo, variant_repo, stats_repo` |
| `services/xlsx_generator.py` (1455) | пакет `xlsx_generator/`: `columns`, `common`, `yandex`, `ozon`, `simple` | `from services.xlsx_generator import generate_export` |
| `routers/export.py` (985) — Р1 | пакет `routers/export/`: `_support`, `_queries`, `_xlsx_dispatch`, `templates`, `preview`, `files`, `xlsx` | `from routers import export; export.router` |
| `services/template_filler.py` (993) — Р2 | пакет `template_filler/`: `_common`, `_sheet_scan`, `_storage`, `_values`, `_filler` | `from services.template_filler import fill_official_template, ...` |
| `services/category_service.py` (709) — Р6 | пакет `category_service/`: `_mocks`, `_api_loaders`, `_storage`, `_service` | `from services.category_service import category_service, CategoryService` |
| `routers/categories.py` (687) — Р7 | пакет `routers/categories/`: `_support`, `specs_refresh`, `specs_admin`, `specs`, `catalog`, `mappings` | `from routers import categories; categories.router` |

Фронтенд (Р3–Р5): `pages/SpecsPage.jsx` (1115) → оркестрация 437 строк +
`components/specs/`; `pages/ProductsPage.jsx` (1095) → 641 строка +
`components/products/` (таблица/пагинация/баннер/хуки); `src/api.js` (1016,
82 метода) → пакет `src/api/` из 10 доменных модулей с агрегатором
`api/index.js` (`import { api } from '../api'` работает без изменений).

Фронтенд-модернизация (Round 7):

- **React Router 7 (HashRouter)** — маршруты вместо стейта `currentView`:
  рабочие виды `/dashboard`, `/products`, `/import`, `/mapping`, `/specs`,
  `/specs-monitor` (только админ), `/templates`, `/history`; публичные
  страницы на прежних хэш-URL (`/privacy`, `/terms`, `/help`,
  `/verify-email`, `/forgot-password`, `/reset-password`). HashRouter —
  осознанно: SPA отдаётся с `/` без catch-all на сервере, а публичные
  страницы уже жили на хэше. Восстановление последней вкладки сохранено
  (localStorage `marketplace_active_view`, значения 1:1 = имена маршрутов);
- **TanStack Query v5** — серверный кэш вместо ручных useState+useEffect:
  ключи `['products', …]` (список страницы + App-список), `['stats']`,
  `['gaps']`, `['spec-names']`, `['edit-history']`; мутации заканчиваются
  инвалидацией префикса — проброс `refreshKey` из App в ProductsPage
  удалён; при логауте кэш очищается целиком (`queryClient.clear()`);
- **Debounce поиска** — `hooks/useDebouncedValue` (300 мс): в queryKey
  уходит задержанное значение, инпут остаётся мгновенным;
- **Vitest** — `vitest.config.js` (jsdom) + `src/test/setup.js`, тесты в
  `src/**/*.test.{js,jsx}`; в CI добавлен шаг `npm run test`.

Push вместо polling + миниатюры (Round 8):

- **SSE-прогресс задач** — `backend/core/sse.py::task_events` (первый кадр
  мгновенно, дедуп неизменных снимков, keepalive каждые 15 с, лимит жизни
  потока 600 с, терминальный статус закрывает поток). Эндпоинты:
  `GET /api/migrate/batch/{id}/events` (completed/failed),
  `GET /api/specs/{p}/refresh/{id}/events` (+paused — терминальный:
  продолжение на странице мониторинга), `GET /api/admin/specs-tasks/events`
  (мониторинг без терминала: поток живёт до лимита, фронт переподключается).
  Заголовок `X-Accel-Buffering: no` отключает буферизацию nginx; старые
  polling-эндпоинты `/progress` остаются рабочим резервом;
- **api/sse.js** — клиент поверх fetch+ReadableStream (EventSource не умеет
  наши cookie+CSRF): `watchTask` — SSE с автопереподключением, при сбое
  SSE до первого события или 3 сбоев подряд — тихий откат на polling тех же
  данных, общий timeout на SSE и резерв. Потребители: useMigration,
  MigrateModal, BatchMigrateModal (проп `pollProgress` из App удалён),
  SpecsPage, SpecsMonitorPage (setInterval'ы удалены);
- **Миниатюры /media/thumbs** — WebP ≤ 320px, генерируются Pillow'ом при
  первом запросе и кэшируются на диске (`media/thumbs/<путь оригинала>.webp`,
  атомарный os.replace). Права идентичны /media: ownership проверяется по
  пути ОРИГИНАЛА; дерево thumbs/ напрямую через /media/{path} не отдаётся
  (маршрут /media/thumbs/{path} объявлен до catch-all, а catch-all режет
  `thumbs/`). Pillow вернулся в requirements (движок миниатюр);
  галерея PhotosModal грузит миниатюры, цепочка ошибок: миниатюра →
  оригинал → прокси.

Правила:

- имена Celery-задач заданы явно (`name="tasks.*"`) и НЕ зависят от пути
  модуля — маршрутизация очередей в `celery_app.py` стабильна;
- порядок include_router в пакетах роутеров МАТЕРИАЛЕН: в
  `routers/categories/` фиксированные пути (`/specs/{p}/names`,
  `/key-source`, `/refresh/...`) регистрируются ДО catch-all
  `/specs/{p}/{category_id:path}` — иначе они ловятся как category_id
  (тест test_fixed_spec_paths_not_swallowed_by_catch_all);
- тесты роутеров собирают маршруты через OpenAPI-схему
  (`tests/_route_helpers.py::served_routes`) — плоский обход
  `router.routes` ломается на Starlette >= 1.10;
- в `routers/media.py` порядок МАТЕРИАЛЕН: `/media/thumbs/{path}` объявлен
  ДО catch-all `/media/{path}`, а catch-all отклоняет `thumbs/` — иначе
  миниатюры раздавались бы без ownership-контроля оригинала
  (тест test_thumbs_tree_not_served_by_catch_all);
- SSE-тайминги (POLL/HEARTBEAT/MAX_STREAM_SECONDS) — константы модуля
  `core/sse.py`, а не дефолты в сигнатуре: эндпоинты их не дублируют,
  тесты подменяют monkeypatch'ем (иначе SSE-тесты спят на реальных интервалах);
- новые модули держим < 500 строк; следующие кандидаты на разбиение —
  `services/ozon_specs.py` (635) и `services/specs_monitor.py` (при росте);
- маппинг «модуль → домен» описан в docstring каждого пакета.

## 4. SSRF и DNS-rebinding (E-4)

`core/ssrf.py` — теперь полная защита от DNS-rebinding (TOCTOU):

- `safe_get()` резолвит имя **один раз**, валидирует **все** A/AAAA-записи
  и **пиннит** их на время запроса через обёртку `socket.getaddrinfo`;
- соединение физически не может уйти на адрес, отличный от проверенного
  (даже если DNS «переключится» между проверкой и запросом);
- пин пересчитывается на **каждом** переходе редиректа;
- SNI, проверка TLS-сертификата и заголовок Host сохранены без изменений.

Тесты: `backend/tests/test_ssrf.py` (включая сценарии имитации
DNS-rebinding без сети).

## 5. Гигиена репозитория

### Что вычищено (неделя 4)

Из git удалены (файлы остаются в истории — см. следующий раздел):

- корневые curl-пейлоады: `login.json` (содержал `admin/admin123`!), `bulk.json`, `migrate.json`;
- сэмплы и мусор: `magnit_sample.xlsx` (715 КБ, дублирован в `backend/data/`), `template_wb.xlsx`, `upload_wb2.xlsx`, `4.xlsx`, `init_test.sql`, `settings.json`, корневые `package.json`/`package-lock.json`;
- runtime-данные: `backend/photos/mock_*/` (62 файла, 1.8 МБ мок-фото), `backend/migrator.db`;
- ad-hoc скрипт `backend/test_magnit.py`.

`.gitignore` дополнен так, чтобы всё это не вернулось. Pre-commit hook
`check-added-large-files` (>1 МБ) — страховка от повторного попадания
бинарников.

### Правила

- в git не попадают: `.env`, сэмплы данных, скриншоты, бинарники, БД;
- тестовые фикстуры живут в `backend/tests/` (маленькие, текстовые);
- если файлу >1 МБ — это не git, это объектное хранилище.

## 6. Чистка истории git (опционально, деструктивно)

Секретов в истории **нет** (проверено: `.env` никогда не коммитился),
но в истории остались тяжёлые бинарники (~4 МБ: дубли xlsx-сэмплов и
мок-фото) и `login.json` с дефолтным паролем dev-админа.

Если репозиторий приватный и команда маленькая — можно оставить как есть.
Если хочется вычистить (и уменьшить клон):

```bash
pip install git-filter-repo

# СНАЧАЛА: свежий клон отдельно (не рабочий!), все ветки локально
git clone --mirror <url> marketplace-migrator.git
cd marketplace-migrator.git

# убрать бинарники и junk из ВСЕЙ истории
git filter-repo --invert-paths \
  --path magnit_sample.xlsx \
  --path template_wb.xlsx \
  --path upload_wb2.xlsx \
  --path init_test.sql \
  --path login.json \
  --path bulk.json \
  --path migrate.json \
  --path settings.json \
  --path package-lock.json \
  --path backend/4.xlsx \
  --path backend/data/magnit_sample.xlsx \
  --path backend/migrator.db \
  --path backend/test_magnit.py \
  --path-glob 'backend/photos/mock_*'

# проверить размер и целостность
git count-objects -vH
git log --oneline | head

# публикация (ПЕРЕЗАПИСЫВАЕТ историю — согласовать с командой!)
git push --force --mirror
```

После force-push **все** клоны нужно пересоздать (`git pull` не сработает),
открытые PR переоткрыть. GitHub после переписания всё ещё хранит старые
объекты в кэше — недоступные коммиты удаляются support-запросом или сами
через ~90 дней; параноикам — сменить все секреты всё равно (см. §7).

## 7. Чек-лист секретов (после любой утечки/публики репо)

1. Сменить `SECRET_KEY`/`JWT_SECRET`, `POSTGRES_PASSWORD`, `ADMIN_PASSWORD` (и пароль dev-админа `admin123`, если использовался).
2. Перевыпустить API-ключи маркетплейсов, хранящиеся в БД (шифруются `SECRET_KEY` — смена ключа делает старые токены нечитаемыми, их нужно ввести заново).
3. `ENVIRONMENT=production` в проде — с ним приложение не стартует с dev-ключами.

## 8. Шпаргалка

| Действие | Команда |
|---|---|
| Тесты | `cd backend && make test` |
| Гейт CI локально | `cd backend && make lint` |
| Полный линт | `cd backend && make lint-full` |
| Хуки коммита | `pre-commit run --all-files` |
| Celery-воркер (dev) | `celery -A celery_app worker -Q default --loglevel=info` |
| Celery-воркер (спеки) | `celery -A celery_app worker -Q specs --loglevel=info -n specs_worker@%h` (env `SPECS_WORKER=1` — включает сверку реестра на старте) |
| Celery-воркер (xlsx) | `celery -A celery_app worker -Q xlsx_export --loglevel=info -n xlsx@%h` |
