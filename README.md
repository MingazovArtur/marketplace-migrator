#  Marketplace Migrator

**Универсальный инструмент для переноса карточек товаров между маркетплейсами**

[![Python](https://img.shields.io/badge/Python-3.12+-blue.svg)](https://python.org)
[![React](https://img.shields.io/badge/React-19.2+-61dafb.svg)](https://react.dev)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.115+-009688.svg)](https://fastapi.tiangolo.com)
[![PostgreSQL](https://img.shields.io/badge/PostgreSQL-15-336791.svg)](https://postgresql.org)
[![Docker](https://img.shields.io/badge/Docker-Ready-2496ed.svg)](https://docker.com)

---

## 📖 О проекте

**Marketplace Migrator** — это веб-приложение для автоматизации переноса карточек товаров между популярными маркетплейсами: **Ozon**, **Wildberries** и **Яндекс Маркет**.

### 🎯 Основные возможности

- ✅ **Импорт товаров** из Excel/CSV файлов или по API ключу
- ✅ **Автоматический маппинг категорий** между площадками
- ✅ **Пакетная миграция** с отслеживанием прогресса в реальном времени
- ✅ **Предпросмотр изменений** перед переносом (название, цена, категория)
- ✅ **Экспорт отчётов** в Excel с историей миграций
- ✅ **Многопользовательский режим** с изоляцией данных
- ✅ **Роли пользователей** (Admin/User)
- ✅ **Современный UI** с тёмной темой и анимациями

### 🚀 Для кого этот проект?

- **Селлеры маркетплейсов**, которые продают на нескольких площадках одновременно
- **Менеджеры по маркетплейсам**, отвечающие за расширение ассортимента
- **E-commerce компании**, автоматизирующие процессы переноса товаров

---

## ️ Технологический стек

### Backend
- **FastAPI** — современный асинхронный фреймворк
- **SQLAlchemy 2.0** — ORM для работы с базой данных
- **PostgreSQL 15** — production-ready база данных
- **Celery + Redis** — фоновые задачи и очереди
- **Alembic** — миграции схемы БД
- **Pydantic** — валидация данных
- **Pandas + OpenPyXL** — работа с Excel/CSV
- **bcrypt** — хэширование паролей
- **JWT** — аутентификация

### Frontend
- **React 19** — UI библиотека
- **Vite** — сборщик
- **Custom Hooks** — управление состоянием
- **CSS Variables** — темизация
- **SVG Icons** — векторные иконки

### Инфраструктура
- **Docker + Docker Compose** — контейнеризация
- **PostgreSQL** — база данных
- **Redis** — брокер задач

---

##  Установка и запуск

### Требования

- **Docker** и **Docker Compose** (версия 2.0+)
- **Git**
- Минимум **4 GB RAM**
- **10 GB** свободного места на диске

### Быстрый старт

1. **Клонируйте репозиторий:**
   ```bash
   git clone https://github.com/YOUR_USERNAME/marketplace-migrator.git
   cd marketplace-migrator