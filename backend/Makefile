# Частые команды разработки (backend)
# Полная инструкция: ../docs/engineering.md

.PHONY: test lint lint-full format run

# Тесты (не требуют БД/Redis — чистые функции и стабы)
test:
	python -m pytest

# CI-гейт: полный набор правил проекта (pyproject.toml), синхронизировано
# с .github/workflows/ci.yml. До Round 34 гейт был только E9,F63,F7,F82 —
# стилевой долг закрыт в Round 21 (447 → 0), см. docs/engineering.md
lint:
	ruff check .

# Историческое имя (полный набор): с Round 34 то же, что make lint.
# Оставлено для совместимости с документацией и привычками.
lint-full: lint

# Авто-форматирование
format:
	black .
	ruff check --fix .

# Локальный запуск API (нужны .env с БД/Redis)
run:
	uvicorn main:app --reload --host 0.0.0.0 --port 8000
