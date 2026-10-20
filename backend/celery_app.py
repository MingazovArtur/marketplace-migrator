import os

from celery import Celery
from kombu import Queue

# Берем URL из переменных окружения (задается в docker-compose)
broker_url = os.getenv("CELERY_BROKER_URL", "redis://localhost:6379/0")
result_backend = os.getenv("CELERY_RESULT_BACKEND", broker_url)

celery_app = Celery(
    "marketplace_migrator",
    broker=broker_url,
    backend=result_backend,
    include=["tasks"],
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="Europe/Moscow",
    enable_utc=True,
    task_track_started=True,
    worker_prefetch_multiplier=1,
    # Выделенные очереди: default (миграции, фото, спеки) и xlsx_export (тяжёлый openpyxl)
    task_default_queue="default",
    task_queues=(
        Queue("default", routing_key="default"),
        Queue("xlsx_export", routing_key="xlsx_export"),
    ),
    task_routes={
        "tasks.generate_xlsx_export_task": {
            "queue": "xlsx_export",
            "routing_key": "xlsx_export",
        },
    },
)