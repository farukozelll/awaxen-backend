"""
Flask Extensions - Merkezi eklenti yönetimi.

Tüm Flask eklentileri burada tanımlanır ve create_app() içinde init edilir.
Bu sayede circular import sorunları önlenir.
"""
import os
from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate
from flask_socketio import SocketIO
from celery import Celery
from celery.schedules import crontab

# Database
db = SQLAlchemy()
migrate = Migrate()

# WebSocket
socketio = SocketIO(cors_allowed_origins="*")

# Celery - Application Factory Pattern için
celery = Celery(__name__)


def init_celery(app, celery_instance):
    """
    Celery'yi Flask app context'i ile entegre et.
    
    Bu sayede Celery task'ları içinde db.session kullanılabilir.
    """
    celery_instance.conf.update(
        broker_url=app.config.get('CELERY_BROKER_URL', 'redis://localhost:6379/0'),
        result_backend=app.config.get('CELERY_RESULT_BACKEND', 'redis://localhost:6379/0'),
        task_serializer='json',
        result_serializer='json',
        accept_content=['json'],
        timezone='Europe/Istanbul',
        enable_utc=True,
        # Beat schedule - Zamanlanmış görevler
        beat_schedule={
            # EPİAŞ Fiyatları - Her saat başı güncelle
            'fetch-epias-prices-hourly': {
                'task': 'app.tasks.market_tasks.fetch_epias_prices',
                'schedule': 3600.0,  # Her saat başı
            },
            # Yarının fiyatları - Her gün 14:30'da (EPİAŞ 14:00'te açıklar)
            'fetch-tomorrow-prices': {
                'task': 'app.tasks.market_tasks.fetch_tomorrow_prices',
                'schedule': crontab(hour=14, minute=30),
            },
            # Eski fiyatları temizle - Her gece 03:00
            'cleanup-old-prices': {
                'task': 'app.tasks.market_tasks.cleanup_old_prices',
                'schedule': crontab(hour=3, minute=0),
                'kwargs': {'days_to_keep': 90},
            },
            # Otomasyon kontrol - Her dakika
            'check-automations-every-minute': {
                'task': 'app.tasks.automation_tasks.check_automations',
                'schedule': 60.0,
            },
            # Entegrasyon senkronizasyonu - Her saat
            'sync-integrations-hourly': {
                'task': 'app.tasks.integration_tasks.sync_all_integrations',
                'schedule': 3600.0,
            },
        },
    )

    class ContextTask(celery_instance.Task):
        """Flask app context'ini Celery task'larına sağlar."""
        def __call__(self, *args, **kwargs):
            with app.app_context():
                return self.run(*args, **kwargs)

    celery_instance.Task = ContextTask
    return celery_instance
