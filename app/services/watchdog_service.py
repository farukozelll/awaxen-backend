"""
Watchdog Service - Cihaz Sağlık İzleme.

Saha cihazları (RPi) bazen kilitlenir.
5 dakika tepki vermeyen cihazları tespit et ve bildir.

Best Practices:
- Heartbeat tabanlı izleme
- Otomatik reset komutu (MQTT üzerinden)
- Bildirim sistemi entegrasyonu
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional
from uuid import UUID

from app.extensions import db
from app.models import SmartDevice, Gateway, Notification

logger = logging.getLogger(__name__)

# Watchdog Configuration
DEVICE_TIMEOUT_MINUTES = 5  # Cihaz timeout süresi
GATEWAY_TIMEOUT_MINUTES = 10  # Gateway timeout süresi
CRITICAL_TIMEOUT_MINUTES = 30  # Kritik alarm süresi


class WatchdogService:
    """
    Cihaz sağlık izleme servisi.
    
    Kullanım:
        watchdog = WatchdogService()
        unresponsive = watchdog.check_all_devices(organization_id)
    """

    def __init__(
        self,
        device_timeout: int = DEVICE_TIMEOUT_MINUTES,
        gateway_timeout: int = GATEWAY_TIMEOUT_MINUTES,
        critical_timeout: int = CRITICAL_TIMEOUT_MINUTES,
    ):
        self.device_timeout = timedelta(minutes=device_timeout)
        self.gateway_timeout = timedelta(minutes=gateway_timeout)
        self.critical_timeout = timedelta(minutes=critical_timeout)

    def check_device_health(self, device: SmartDevice) -> Optional[Dict[str, Any]]:
        """
        Tek bir cihazın sağlık durumunu kontrol et.
        
        Returns:
            Sorun varsa dict, yoksa None
        """
        if not device.last_seen:
            return {
                "device_id": str(device.id),
                "device_name": device.name,
                "external_id": device.external_id,
                "status": "never_seen",
                "severity": "warning",
                "message": f"Cihaz hiç veri göndermedi: {device.name}",
                "last_seen": None,
                "offline_duration": None,
            }
        
        now = datetime.now(timezone.utc)
        
        # last_seen timezone-aware değilse dönüştür
        last_seen = device.last_seen
        if last_seen.tzinfo is None:
            last_seen = last_seen.replace(tzinfo=timezone.utc)
        
        offline_duration = now - last_seen
        
        # Kritik timeout
        if offline_duration > self.critical_timeout:
            return {
                "device_id": str(device.id),
                "device_name": device.name,
                "external_id": device.external_id,
                "status": "critical",
                "severity": "critical",
                "message": f"🚨 Cihaz {offline_duration.seconds // 60} dakikadır yanıt vermiyor: {device.name}",
                "last_seen": last_seen.isoformat(),
                "offline_duration_minutes": offline_duration.seconds // 60,
            }
        
        # Normal timeout
        if offline_duration > self.device_timeout:
            return {
                "device_id": str(device.id),
                "device_name": device.name,
                "external_id": device.external_id,
                "status": "unresponsive",
                "severity": "warning",
                "message": f"⚠️ Cihaz {offline_duration.seconds // 60} dakikadır yanıt vermiyor: {device.name}",
                "last_seen": last_seen.isoformat(),
                "offline_duration_minutes": offline_duration.seconds // 60,
            }
        
        return None

    def check_gateway_health(self, gateway: Gateway) -> Optional[Dict[str, Any]]:
        """
        Gateway sağlık durumunu kontrol et.
        
        Returns:
            Sorun varsa dict, yoksa None
        """
        if not gateway.last_seen:
            return {
                "gateway_id": str(gateway.id),
                "gateway_name": gateway.name,
                "serial_number": gateway.serial_number,
                "status": "never_seen",
                "severity": "warning",
                "message": f"Gateway hiç veri göndermedi: {gateway.name}",
                "last_seen": None,
                "offline_duration": None,
            }
        
        now = datetime.now(timezone.utc)
        
        last_seen = gateway.last_seen
        if last_seen.tzinfo is None:
            last_seen = last_seen.replace(tzinfo=timezone.utc)
        
        offline_duration = now - last_seen
        
        if offline_duration > self.gateway_timeout:
            severity = "critical" if offline_duration > self.critical_timeout else "warning"
            return {
                "gateway_id": str(gateway.id),
                "gateway_name": gateway.name,
                "serial_number": gateway.serial_number,
                "status": "unresponsive",
                "severity": severity,
                "message": f"🔌 Gateway {offline_duration.seconds // 60} dakikadır yanıt vermiyor: {gateway.name}",
                "last_seen": last_seen.isoformat(),
                "offline_duration_minutes": offline_duration.seconds // 60,
            }
        
        return None

    def check_all_devices(
        self,
        organization_id: UUID,
    ) -> List[Dict[str, Any]]:
        """
        Organizasyondaki tüm cihazları kontrol et.
        
        Returns:
            Sorunlu cihaz listesi
        """
        issues = []
        
        # Cihazları kontrol et
        devices = SmartDevice.query.filter_by(
            organization_id=organization_id,
            is_active=True,
        ).all()
        
        for device in devices:
            issue = self.check_device_health(device)
            if issue:
                issue["type"] = "device"
                issues.append(issue)
                
                # Cihazı offline olarak işaretle
                if device.is_online:
                    device.is_online = False
                    logger.info(f"[Watchdog] Cihaz offline: {device.name}")
        
        # Gateway'leri kontrol et
        gateways = Gateway.query.filter_by(
            organization_id=organization_id,
            is_active=True,
        ).all()
        
        for gateway in gateways:
            issue = self.check_gateway_health(gateway)
            if issue:
                issue["type"] = "gateway"
                issues.append(issue)
        
        if issues:
            db.session.commit()
            logger.warning(f"[Watchdog] {len(issues)} sorunlu cihaz tespit edildi")
        
        return issues

    def send_reset_command(
        self,
        device: SmartDevice,
    ) -> bool:
        """
        Cihaza MQTT üzerinden reset komutu gönder.
        
        Args:
            device: Hedef cihaz
        
        Returns:
            Başarılı mı
        """
        try:
            from app.mqtt_client import _client as mqtt_client
            
            if mqtt_client is None:
                logger.warning("[Watchdog] MQTT client mevcut değil")
                return False
            
            # Reset komutu topic'i
            topic = f"awaxen/devices/{device.external_id}/command"
            payload = '{"action": "reset", "source": "watchdog"}'
            
            result = mqtt_client.publish(topic, payload, qos=1)
            
            if result.rc == 0:
                logger.info(f"[Watchdog] Reset komutu gönderildi: {device.name}")
                return True
            else:
                logger.warning(f"[Watchdog] Reset komutu gönderilemedi: {device.name}")
                return False
                
        except Exception as e:
            logger.error(f"[Watchdog] Reset komutu hatası: {e}")
            return False


def create_watchdog_notification(
    issue: Dict[str, Any],
    organization_id: UUID,
) -> Notification:
    """
    Watchdog sorunu için bildirim oluştur.
    """
    from app.models.enums import NotificationStatus
    
    severity_map = {
        "critical": "high",
        "warning": "medium",
        "info": "low",
    }
    
    notification = Notification(
        organization_id=organization_id,
        title=f"🔔 Cihaz Sağlık Uyarısı",
        message=issue.get("message", "Cihaz sorunu tespit edildi"),
        notification_type="watchdog",
        priority=severity_map.get(issue.get("severity", "warning"), "medium"),
        data={
            "issue_type": issue.get("type"),
            "device_id": issue.get("device_id") or issue.get("gateway_id"),
            "device_name": issue.get("device_name") or issue.get("gateway_name"),
            "status": issue.get("status"),
            "offline_duration_minutes": issue.get("offline_duration_minutes"),
        },
        status=NotificationStatus.PENDING,
    )
    
    db.session.add(notification)
    return notification


# Singleton instance
_watchdog_service: Optional[WatchdogService] = None


def get_watchdog_service() -> WatchdogService:
    """Watchdog service singleton'ı döndür."""
    global _watchdog_service
    if _watchdog_service is None:
        _watchdog_service = WatchdogService()
    return _watchdog_service
