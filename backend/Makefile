# Частые команды разработки (backend)
# Полная инструкция: ../docs/engineering.md

.PHONY: test lint lint-full format run

# Тесты (не требуют БД/Redis — чистые функции и стабы)
test:
	python -m pytest

# CI-гейт: только критические правила (синхронизировано с .github/workflows/ci.yml)
lint:
	ruff check --select E9,F63,F7,F82 .

# Полный набор правил проекта (pyproject.toml). Весь код пока не проходит —
# текущий долг и план ужесточения: docs/engineering.md
lint-full:
	ruff check .

# Авто-форматирование
format:
	black .
	ruff check --fix .

# Локальный запуск API (нужны .env с БД/Redis)
run:
	uvicorn main:app --reload --host 0.0.0.0 --port 8000
