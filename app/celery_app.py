"""
Celery Application Factory.

Bu dosya Celery worker ve beat tarafından import edilir.
Flask app context'i ile entegre çalışır.
"""
from celery import Celery

from app import create_app
from app.extensions import init_celery, celery

# Flask app'i oluştur
flask_app = create_app()

# Celery'yi Flask ile entegre et
celery_app = init_celery(flask_app, celery)

# Task'ları import et (autodiscover)
celery_app.autodiscover_tasks(['app.tasks'])
