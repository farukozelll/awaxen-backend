"""
Monitoring Tasks - Watchdog & Anomaly Detection.

Periyodik olarak çalışan izleme görevleri:
- Cihaz sağlık kontrolü (Watchdog)
- Anormallik tespiti (Anomaly Detection)
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List

from celery import shared_task

from app.extensions import db
from app.models import Organization
from app.services.watchdog_service import (
    get_watchdog_service,
    create_watchdog_notification,
)
from app.services.anomaly_service import (
    get_anomaly_detector,
    create_anomaly_notification,
)

logger = logging.getLogger(__name__)


@shared_task(bind=True, max_retries=2)
def check_device_health(self) -> Dict[str, Any]:
    """
    Tüm organizasyonlardaki cihazların sağlık durumunu kontrol et.
    
    Celery Beat ile her 5 dakikada bir çalıştırılmalı.
    
    Returns:
        İşlem özeti
    """
    from app import create_app
    
    app = create_app()
    
    with app.app_context():
        watchdog = get_watchdog_service()
        
        # Tüm aktif organizasyonları al
        organizations = Organization.query.filter_by(is_active=True).all()
        
        total_issues = 0
        notifications_created = 0
        
        for org in organizations:
            try:
                issues = watchdog.check_all_devices(org.id)
                total_issues += len(issues)
                
                # Her sorun için bildirim oluştur
                for issue in issues:
                    # Kritik sorunlar için bildirim
                    if issue.get("severity") in ("critical", "warning"):
                        create_watchdog_notification(issue, org.id)
                        notifications_created += 1
                
                if issues:
                    db.session.commit()
                    
            except Exception as e:
                logger.error(f"[Watchdog] Org kontrolü hatası: {org.id} - {e}")
                db.session.rollback()
        
        logger.info(f"[Watchdog] Kontrol tamamlandı: {total_issues} sorun, {notifications_created} bildirim")
        
        return {
            "organizations_checked": len(organizations),
            "total_issues": total_issues,
            "notifications_created": notifications_created,
        }


@shared_task(bind=True, max_retries=2)
def check_anomalies(self) -> Dict[str, Any]:
    """
    Tüm organizasyonlardaki cihazlarda anormallik kontrolü yap.
    
    Celery Beat ile her 10 dakikada bir çalıştırılmalı.
    
    Returns:
        İşlem özeti
    """
    from app import create_app
    
    app = create_app()
    
    with app.app_context():
        detector = get_anomaly_detector()
        
        organizations = Organization.query.filter_by(is_active=True).all()
        
        total_anomalies = 0
        notifications_created = 0
        
        for org in organizations:
            try:
                anomalies = detector.check_all_devices(org.id)
                total_anomalies += len(anomalies)
                
                for anomaly in anomalies:
                    # Yüksek ve orta seviye anomaliler için bildirim
                    if anomaly.get("severity") in ("high", "medium"):
                        create_anomaly_notification(anomaly, org.id)
                        notifications_created += 1
                
                if anomalies:
                    db.session.commit()
                    
            except Exception as e:
                logger.error(f"[Anomaly] Org kontrolü hatası: {org.id} - {e}")
                db.session.rollback()
        
        logger.info(f"[Anomaly] Kontrol tamamlandı: {total_anomalies} anormallik, {notifications_created} bildirim")
        
        return {
            "organizations_checked": len(organizations),
            "total_anomalies": total_anomalies,
            "notifications_created": notifications_created,
        }


@shared_task
def send_device_reset(device_id: str) -> Dict[str, Any]:
    """
    Belirli bir cihaza reset komutu gönder.
    
    Args:
        device_id: Cihaz UUID
    
    Returns:
        İşlem sonucu
    """
    from uuid import UUID
    from app import create_app
    from app.models import SmartDevice
    
    app = create_app()
    
    with app.app_context():
        try:
            device = SmartDevice.query.get(UUID(device_id))
            if not device:
                return {"success": False, "error": "Device not found"}
            
            watchdog = get_watchdog_service()
            success = watchdog.send_reset_command(device)
            
            return {
                "success": success,
                "device_id": device_id,
                "device_name": device.name,
            }
            
        except Exception as e:
            logger.error(f"[Watchdog] Reset hatası: {device_id} - {e}")
            return {"success": False, "error": str(e)}
