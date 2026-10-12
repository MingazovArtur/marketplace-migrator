import os

from celery import Celery

# Берем URL из переменных окружения (задается в docker-compose)
broker_url = os.getenv("CELERY_BROKER_URL", "redis://localhost:6379/0")

celery_app = Celery(
    "marketplace_migrator", broker=broker_url, backend=broker_url, include=["tasks"]
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="Europe/Moscow",
    enable_utc=True,
)
