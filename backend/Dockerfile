FROM python:3.15-slim

# PyPI за DPI-сетями обрывается по TLS (РФ, с 01.06.2026): сборка с зеркалом —
# PIP_INDEX_URL=https://mirrors.cloud.tencent.com/pypi/simple (Round 28)
ARG PIP_INDEX_URL=https://pypi.org/simple

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DEFAULT_TIMEOUT=100 \
    PIP_INDEX_URL=${PIP_INDEX_URL}

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir --default-timeout=100 --retries 10 -r requirements.txt

COPY . .

# R29: non-root, как в Dockerfile.prod — dev-контейнеры (uvicorn и все три
# celery-воркера) больше не стартуют от root (celery 5.7 печатает
# SecurityWarning: superuser privileges). Volume media/ozon_templates,
# созданные до этого раунда от root, нужно пересоздать: см. README-round29
RUN useradd -m app && mkdir -p /app/media /app/templates/ozon && chown -R app:app /app
USER app

EXPOSE 8000

CMD ["sh", "-c", "alembic upgrade head && uvicorn main:app --host 0.0.0.0 --port 8000 --reload"]
