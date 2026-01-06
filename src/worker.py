"""
Celery Worker Configuration
Task queue for background jobs.
"""
from celery import Celery
from celery.schedules import crontab

from src.core.config import settings

celery_app = Celery(
    "awaxen",
    broker=settings.celery_broker_url,
    backend=settings.celery_result_backend,
    include=[
        "src.tasks.telemetry",
        "src.tasks.billing",
        "src.tasks.notifications",
        "src.tasks.integrations",
    ],
)

# Celery configuration
celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="Europe/Istanbul",
    enable_utc=True,
    task_track_started=True,
    task_time_limit=30 * 60,  # 30 minutes
    task_soft_time_limit=25 * 60,  # 25 minutes
    worker_prefetch_multiplier=1,
    worker_concurrency=4,
    result_expires=3600,  # 1 hour
    beat_schedule={
        # Billing tasks
        "check-overdue-invoices": {
            "task": "src.tasks.billing.check_overdue_invoices",
            "schedule": 3600.0,  # Every hour
        },
        # Telemetry tasks
        "cleanup-old-telemetry": {
            "task": "src.tasks.telemetry.cleanup_old_telemetry",
            "schedule": crontab(hour=3, minute=0),  # Daily at 03:00
        },
        # EPİAŞ price fetch - daily at 00:05
        "fetch-daily-prices": {
            "task": "src.tasks.integrations.fetch_daily_prices",
            "schedule": crontab(hour=0, minute=5),
        },
        # Price threshold check - every 15 minutes during peak hours
        "check-price-threshold": {
            "task": "src.tasks.integrations.check_price_threshold",
            "schedule": crontab(minute="*/15", hour="8-22"),
            "args": (2000.0,),  # Threshold: 2000 TRY/MWh
        },
    },
)
