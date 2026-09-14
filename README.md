# 🚀 Marketplace Migrator v3.1

[![Python 3.12+](https://img.shields.io/badge/Python-3.12+-blue.svg)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.115+-green.svg)](https://fastapi.tiangolo.com/)
[![React 19](https://img.shields.io/badge/React-19-61DAFB.svg)](https://react.dev/)
[![Docker](https://img.shields.io/badge/Docker-Ready-2496ED.svg)](https://www.docker.com/)

**Профессиональный инструмент для автоматической миграции карточек товаров** между Ozon, Wildberries и Яндекс Маркетом.

> 💡 **Ключевая особенность:** Production-ready архитектура (SQLAlchemy, Celery, Redis, Docker) с возможностью редактирования данных перед переносом и пакетной обработкой с прогресс-баром.

---

## ✨ Основные возможности (v3.1)

- 🔄 **Мультиплатформенность:** Импорт и экспорт для Ozon, Wildberries, Яндекс Маркет.
- 📥 **Гибкий импорт:** По API-ключам, через YML-фиды (без регистрации) или из Excel/CSV.
- ✏️ **Редактирование перед переносом:** Изменение названия, цены и категории в окне предпросмотра.
- ⚡ **Пакетная миграция:** Перенос десятков товаров одной кнопкой с live-прогресс-баром.
- 📊 **Экспорт отчетов:** Генерация Excel-файла с историей миграций и расчетом новых цен.
- 🧠 **Умный маппинг:** Автоматическое определение категорий целевой площадки.
- 🏗️ **Архитектура:** SQLAlchemy (SQLite/PostgreSQL), Celery + Redis для фоновых задач, Repository Pattern.

---

## 🚀 Быстрый старт (Docker)

Самый простой способ запустить всё сразу (Backend, Frontend, Redis, Celery):

```bash
git clone https://github.com/ВАШ_НИК/marketplace-migrator.git
cd marketplace-migrator
docker compose up --build