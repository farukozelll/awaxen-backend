"""
Celery Tasks - Asenkron görevler.

Bu modül tüm Celery task'larını içerir:
- market_tasks: EPİAŞ fiyat çekme
- automation_tasks: Otomasyon kurallarını değerlendirme
- integration_tasks: Bulut entegrasyonlarını senkronize etme
- ai_tasks: YOLO + SAM2 ile görüntü analizi
- monitoring_tasks: Watchdog & Anomaly Detection
"""

from .market_tasks import fetch_epias_prices
from .automation_tasks import check_automations
from .integration_tasks import sync_all_integrations, sync_integration_devices
from .ai_tasks import process_ai_detection, cleanup_old_ai_results
from .monitoring_tasks import check_device_health, check_anomalies, send_device_reset

__all__ = [
    'fetch_epias_prices',
    'check_automations', 
    'sync_all_integrations',
    'sync_integration_devices',
    'process_ai_detection',
    'cleanup_old_ai_results',
    'check_device_health',
    'check_anomalies',
    'send_device_reset',
]
