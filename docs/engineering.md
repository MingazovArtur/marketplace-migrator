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

Девятнадцать монолитов разбиты на пакеты с сохранением публичного API импортов
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
| `services/ozon_specs.py` (635) — Р8 | пакет `ozon_specs/`: `_http`, `_tree`, `_attributes`, `_storage`, `_refresh` | `from services.ozon_specs import refresh_ozon_specs` |
| `services/specs_monitor.py` (419) — Р9 | пакет `specs_monitor/`: `_keys`, `_lifecycle`, `_pause`, `_queries` | `from services import specs_monitor` |
| `routers/products.py` (791) — Р10 | пакет `routers/products/`: `_support`, `_bulk`, `_lists`, `_single`, `_delete` | `from routers import products; products.router`, `products.repo` (точки патчинга тестов) |
| `services/tnved_mapper.py` (694) — Р11 | пакет `tnved_mapper/`: `_database_a`, `_database_b`, `_database` (склейка `{**A, **B}`), `_lookup` | `from services.tnved_mapper import suggest_tnved, get_tnved_description, search_tnved, TNVED_DATABASE` |
| `services/spec_validator.py` (618) — Р12 | пакет `spec_validator/`: `_canon`, `_ozon_base`, `_attributes`, `_entry` | `from services.spec_validator import validate_product_by_spec, validate_products_by_specs` (импортёр routers/export/preview.py) |
| `routers/import_router.py` (612) — Р13 | пакет `routers/import_router/`: `_support`, `_preview`, `_key_import`, `_file_import` | `from routers import import_router; import_router.router`, `import_router.repo`/`op_log`/`stats_repo` (точки патчинга) |
| `database/repository/products.py` (593) — Р14 | пакет `repository/products/`: `_serialize`, `_filters`, `_async_reads`, `_sync_reads`, `_writes`, `_bulk_import`, сборка класса `_repository` (миксины) | `from database.repository.products import ProductRepository, repo`; статические `ProductRepository._to_dict/_variant_rows/_attr_rows` (через класс — variants.py/attributes.py/test_money_helpers.py) |
| `tasks/migrate_tasks.py` (529) — Р15 | пакет `migrate_tasks/`: `_notify`, `_single`, `_batch` | `from tasks.migrate_tasks import migrate_batch_task, migrate_product_task` (импортёр tasks/__init__.py); Celery-имена явные `tasks.*` |
| `services/yandex_specs.py` (443) — Р16 | пакет `yandex_specs/`: `_http`, `_tree`, `_parameters`, `_storage`, `_refresh` | `from services.yandex_specs import refresh_yandex_specs` (импортёр tasks/catalog_tasks/_refresh.py — локальный импорт в теле задачи) |
| `services/wb_specs.py` (313) — Р17 | пакет `wb_specs/`: `_http`, `_subjects`, `_characteristics`, `_storage`, `_refresh` | `from services.wb_specs import refresh_wildberries_specs` (импортёр tasks/catalog_tasks/_refresh.py — локальный импорт в теле задачи) |
| `services/xlsx_generator/aliexpress.py` (604) — Р18 | под-пакет `xlsx_generator/aliexpress/`: `_layout`, `_rows`, `_workbook`, `_sheets`, `_utils` | `from services.xlsx_generator.aliexpress import build_aliexpress_workbook, ...` (импортёры export_builder.py, routers/export/files.py, routers/templates.py, xlsx_generator/__init__.py) |
| `services/xlsx_generator/columns.py` (597) — Р19 | под-пакет `xlsx_generator/columns/`: `_styles`, `_ozon`, `_yandex` | `from services.xlsx_generator.columns import ...` (импортёры common/yandex/ozon/simple) |
| `tasks/matching.py` (459) — Р20 | пакет `matching/`: `_text`, `_cache`, `_match`, `_attrs` | `from tasks.matching import _pick_target_category, _ensure_canonical_attributes, _base_source, _safe_float, _spec_cache_invalidate, _stem_ru` (импортёры tasks/migrate_tasks/_single+/_batch, tasks/catalog_tasks/_refresh, tests/test_money_helpers.py) |
| `routers/photos.py` (298) — Р21 | пакет `routers/photos/`: `_support`, `_proxy`, `_manage`, `_upload`, `_download` | `from routers import photos; photos.router` (импортёр main.py не менялся); порядок include_router — как порядок объявления в монолите |
| `tasks/catalog_tasks.py` (297) — Р22 | пакет `catalog_tasks/`: `_refresh`, `_reconcile` | `from tasks.catalog_tasks import refresh_specs_task` (импортёр tasks/__init__.py); Celery-имя явное `tasks.refresh_specs_task` |

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
- новые модули держим < 500 строк (справочник ТН ВЭД разбит на две части
  именно поэтому); `spec_validator.py` (618) и `import_router.py` (612)
  разбиты в Р12–Р13, `repository/products.py` (593) и `migrate_tasks.py`
  (529) — в Р14–Р15, `yandex_specs.py` (443) и `wb_specs.py` (313) — в
  Р16–Р17 (три sibling-сервиса спецификаций — ozon/yandex/wb — в
  одинаковом пакетном виде), `xlsx_generator/aliexpress.py` (604) и
  `xlsx_generator/columns.py` (597) — в Р18–Р19 (под-пакеты внутри
  пакета — прецедент `database/repository/products/`),
  `tasks/matching.py` (459), `routers/photos.py` (298) и
  `tasks/catalog_tasks.py` (297) — в Р20–Р22 (третий эшелон очереди);
  все модули backend теперь < 500 строк — исключение только
  `database/models.py` (409): единый файл моделей SQLAlchemy —
  единственная точка truth для Alembic autogenerate, разбиение
  нецелесообразно; линия разбиения монолитов закрыта;
- в `database/repository/products/` класс собран из шести доменных
  миксинов (`_repository.py`), тела методов перенесены 1:1 без
  переопределений: и `self._to_dict` внутри методов, и статические
  `ProductRepository._variant_rows/_attr_rows/_to_dict` через КЛАСС
  (repository/variants.py, attributes.py, tests/test_money_helpers.py)
  работают как в монолите; MRO: `_SerializeMixin` первым;
- в `tasks/migrate_tasks/` Celery-задачи декорируются в подмодулях
  `_single`/`_batch`: имена явные (`name="tasks.*"`), регистрация
  срабатывает при импорте пакета (`celery_app.py: include=["tasks"]` →
  `tasks/__init__.py` → `migrate_tasks/__init__.py`), маршрутизация
  очередей от пути модуля не зависит; тесты подменяют зависимости
  (`repo`/`stats_repo`/`op_log`/`defaults_service`/`_pick_target_category`)
  в этих подмодулях и выполняют задачи eager-вызовом `.apply(throw=True)`;
- в `services/tnved_mapper/` порядок ключей справочника МАТЕРИАЛЕН
  (search_tnved отдаёт первые 10 совпадений в порядке справочника):
  части `_database_a`/`_database_b` — последовательные строки монолита,
  склейка `{**A, **B}` в `_database.py` воспроизводит порядок и значения
  байт-в-байт (позиция дублированного ключа — из A, значение — из B;
  тест test_key_order_and_cross_values);
- в `services/specs_monitor/` redis_client импортирован отдельно в
  `_lifecycle`/`_pause`/`_queries` — тесты подменяют клиент в этих модулях
  (helper `_set_redis` в tests/test_specs_monitor.py), патч на пакете
  после разбиения больше не работает;
- в `routers/products/` порядок include_router МАТЕРИАЛЕН: параметрические
  GET/PATCH/DELETE `/products/{product_id}` (`_single`) включаются ПОСЛЕ
  `_bulk` и `_lists`, где объявлены фиксированные GET-пути `/edit-history`,
  `/category-counts`, `/categories-suggest` — иначе они ловятся как
  product_id и отдают 422 (тест
  test_fixed_get_paths_not_swallowed_by_parametric);
- в `services/spec_validator/` канонические атрибуты (Бренд/Модель/Тип/
  Маркировка) проверяются ОДИН раз в конце `_validate_attributes` через
  filled_canons: пустой СИНОНИМ («Модель» при заполненном «Объединить
  на одной карточке») ошибкой не считается; severity=error дают только
  13 канонических колонок XLS-шаблона Ozon, прочие required-атрибуты —
  warning (v3, согласование с XLS-шаблоном);
- в `routers/import_router/` все 3 маршрута фиксированные — порядок
  include_router на матчинг не влияет (сохранён как в монолите:
  preview, import, file); точки патчинга `repo`/`op_log`/`stats_repo` —
  модули database.repository, те же объекты, что в подмодулях; логгеры
  подмодулей — иерархические дети `routers.import_router` (конфиг
  логирования по имени родителя продолжает действовать);
- в `services/yandex_specs/` и `services/wb_specs/` (как и в `ozon_specs/`)
  кооперативная пауза на разных границах: Яндекс — между чанками записи
  (блок дообрабатывается и коммитится, `DB_CHUNK` в `_refresh` — тесты
  подменяют его monkeypatch'ем), WB — перед каждым предметом (построчный
  upsert, отклик почти мгновенный); задержка `WB_REQUEST_DELAY` между
  предметами — константа `_refresh` (тесты подменяют её на 0, чтобы не
  спать на реальных интервалах); HTTP-запросы замокаются в тех подмодулях,
  где они используются (`_tree._post_ym`, `_parameters._post_ym`,
  `_subjects`/`_characteristics` — стаб-клиент), а не на пакете;
- в `services/xlsx_generator/columns/` (Р19) данные шаблонов разложены по
  площадкам (`_ozon`/`_yandex`), а общие тексты групп Ozon (G_*) и
  подсказки — в `_styles`: `OZON_BASE_COLUMNS` ссылается на те же
  объекты `G_NAME`/`G_PRICE`/…, что и монолит (реэкспорт через
  `__init__` пакета), порядок кортежей перенесён 1:1 —
  YANDEX_GROUP_MERGES (10 групп) покрывают все 48 колонок без дыр;
- в `tasks/matching/` (Р20) P-3 кэш живёт в `_cache`, и тесты наполняют
  оригинальные сторы напрямую (`_fill_cache` в test_matching_split.py)
  со свежей TTL-меткой — `_spec_cache_load` выходит по метрике, не
  открывая сессию БД; `_match.py` импортировал `_spec_cache_names`/
  `_spec_name_exists`/… ПО ССЫЛКЕ (`from … import`), поэтому
  `monkeypatch.setattr(cache_mod, "_spec_cache_names", …)` на него НЕ
  действует — работаем с оригинальными словарями и чистим их
  `_spec_cache_invalidate()`; точки патчинга
  `_pick_target_category`/`_ensure_canonical_attributes` в тестах
  миграций — подмодули tasks/migrate_tasks/_single и _batch (имена
  импортированы туда), при разбиении не сдвинулись;
- в `routers/photos/` (Р21) порядок include_router МАТЕРИАЛЕН:
  фиксированный GET `/photos/proxy` подключается ПЕРЕД параметрическими
  `/{product_id}/photos*` — как порядок объявления в монолите (тест
  test_proxy_route_registered_before_parametric); rate-limiter
  остаётся на эндпоинте `_proxy` (slowapi + Redis, тестовое окружение
  без Redis — в сплит-тесте не вызывается, SSRF-фильтр покрыт
  test_ssrf.py); `_build_public_media_url` — в `_support`: полный URL
  нужен и `_upload`, и `_download` (dev-фронт :5173 не подставляется
  в XLSX-экспорт);
- в `tasks/catalog_tasks/` (Р22) тело `refresh_specs_task` перенесено
  в `_refresh` 1:1, включая ЛОКАЛЬНЫЕ импорты загрузчиков спеков в теле
  (`from services.ozon_specs import refresh_ozon_specs` и sibling):
  точки патчинга тестов — модули services.* (строковые пути
  `monkeypatch.setattr("services.ozon_specs.refresh_ozon_specs", …)`),
  eager-вызов `.apply(throw=True)`; обработчик `worker_ready`
  (`_reconcile_specs_registry_on_worker_start`) подключается к сигналу
  при импорте `_reconcile` — `__init__` пакета импортирует его для
  side-effect, как раньше при импорте монолита;
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
