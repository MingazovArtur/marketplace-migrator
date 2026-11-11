# Marketplace Migrator

Перенос товарных карточек между маркетплейсами (Ozon, Wildberries, Яндекс Маркет,
Магнит Маркет) через Excel-шаблоны: импорт из любого источника → нормализация →
маппинг категорий → готовые XLSX по официальным эталонам площадок.

[![CI](https://github.com/MingazovArtur/marketplace-migrator/actions/workflows/ci.yml/badge.svg)](https://github.com/MingazovArtur/marketplace-migrator/actions/workflows/ci.yml)
[![CodeQL](https://github.com/MingazovArtur/marketplace-migrator/actions/workflows/codeql.yml/badge.svg)](https://github.com/MingazovArtur/marketplace-migrator/actions/workflows/codeql.yml)
![Python 3.12](https://img.shields.io/badge/Python-3.12-3776AB?logo=python&logoColor=white)
![FastAPI](https://img.shields.io/badge/FastAPI-0.115-009688?logo=fastapi&logoColor=white)
![React 19](https://img.shields.io/badge/React-19-61DAFB?logo=react&logoColor=black)
![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)

## Быстрый старт (Docker, весь стек)

```bash
git clone https://github.com/MingazovArtur/marketplace-migrator.git
cd marketplace-migrator
cp .env.example .env        # заполнить секреты (CHANGE_ME -> сгенерировать)
docker compose up --build   # API: localhost:8000 (swagger: /docs), фронт: localhost:5173
```

Прод-конфигурация (nginx, 8 сервисов, HTTPS): [docker-compose.prod.yml](docker-compose.prod.yml)
+ [deploy/](deploy/) (nginx-конфиги, HTTPS одной командой, бэкапы БД).
Разработка и тесты (без Docker): [docs/engineering.md](docs/engineering.md).

---

## 1. Идея и смысл проекта

**Marketplace Migrator** — это SaaS-платформа для селлеров маркетплейсов, которая автоматизирует процесс переноса товарных карточек между различными площадками (Ozon, Wildberries, Яндекс Маркет, Магнит Маркет).

**Проблема, которую решает проект:**
Селлеры, работающие на нескольких маркетплейсах одновременно, сталкиваются с необходимостью вручную адаптировать карточки товаров под требования каждой площадки. Разные форматы файлов, разные категории, разные обязательные атрибуты (ТН ВЭД, НДС, габариты упаковки), разные шаблоны XLSX — всё это приводит к огромным временным затратам и ошибкам при загрузке товаров.

**Решение:**
Платформа импортирует товары из любого источника (файл Excel/CSV, API-ключ площадки, YML-фид), нормализует данные, позволяет настроить маппинг категорий между площадками, автоматически подбирает коды ТН ВЭД и формирует готовые XLSX-файлы по официальным эталонным шаблонам маркетплейсов.

---

## 2. Технологический стек

### Backend
- **FastAPI (0.115+)** — основной асинхронный фреймворк API
- **SQLAlchemy 2.0** — ORM для работы с БД
- **PostgreSQL 15** — основная реляционная база данных (SQLite fallback для локальной разработки)
- **Redis 7** — кэширование справочников/спеков, хранение лимитов/банов и брокер задач
- **Celery 5** — фоновые задачи (миграции, загрузка спеков Ozon, скачивание фото)
- **Alembic** — управление миграциями схемы БД
- **OpenPyXL / Pandas** — парсинг и генерация XLSX/CSV со сложным форматированием и валидацией ячеек (`DataValidation`)
- **SlowAPI** — rate limiting и автоблокировка нарушителей
- **Pydantic v2 + pydantic-settings** — валидация схем и конфигурация окружения
- **bcrypt + python-jose** — хэширование паролей и JWT-аутентификация

### Frontend
- **React 19** + **Vite** — клиентское SPA-приложение
- **Custom Hooks** — управление состоянием (`useAuth`, `useProducts`, `useMigration`, `useCategoryMapping`)
- **CSS Variables** — адаптивная дизайн-система с поддержкой тёмной и светлой тем
- **Hash-based routing** — легковесная навигация без внешних зависимостей

### Инфраструктура
- **Docker + Docker Compose** — изолированная конфигурация для `dev` и `prod` с лимитами памяти и CPU
- **Nginx** — reverse proxy, раздача статики/медиа, сжатие gzip и rate-limiting на уровне периметра
- **Certbot** — автоматический выпуск и обновление SSL-сертификатов Let's Encrypt

---

## 3. Архитектура

```text
┌─────────────────────────────────────────────────────────────┐
│  Nginx (порт 80/443)                                        │
│  ├── /api/*   → backend:8000 (FastAPI)                      │
│  ├── /media/* → /var/media (статические копии фото)         │
│  └── /*       → frontend (React SPA)                        │
└───────────────┬───────────────────────────┬─────────────────┘
                │                           │
                ▼                           ▼
       ┌───────────────┐           ┌──────────────────┐
       │   Frontend    │           │     Backend      │
       │  (React 19)   │◄─────────►│    (FastAPI)     │
       └───────────────┘           └────────┬─────────┘
                                            │
                ┌───────────────────────────┼───────────────────────────┐
                │                           │                           │
                ▼                           ▼                           ▼
       ┌───────────────┐           ┌───────────────┐           ┌──────────────────┐
       │  PostgreSQL   │           │     Redis     │           │      Celery      │
       │ (основная БД) │           │ (кэш / брокер)│           │ (фоновые задачи) │
       └───────────────┘           └───────────────┘           └──────────────────┘
---

## 4. Разработка (инженерные основы)

Тесты, линтеры, CI, pre-commit, структура пакетов и гигиена репозитория —
в **[docs/engineering.md](docs/engineering.md)**.

Быстрый старт:

```bash
cd backend
pip install -r requirements.txt -r requirements-dev.txt
make test    # pytest — не требует БД/Redis
make lint    # CI-гейт (ruff, критические правила)
```

CI (GitHub Actions) на каждый push/PR: линт+тесты backend, линт+сборка
frontend, сборка Docker-образов. Пакетная структура: `tasks/`,
`database/repository/`, `services/xlsx_generator/` (публичные API импортов
сохранены).
