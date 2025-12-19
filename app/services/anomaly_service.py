"""
Anomaly Detection Service - İstatistiksel Anormallik Tespiti.

"Bu saatte bu priz normalde 50W çekerdi, şu an 2000W çekiyor."
Basit istatistik ile olağandışı aktivite tespiti.

Best Practices:
- Z-Score tabanlı tespit (standart sapma)
- Saatlik/günlük pattern analizi
- Sliding window ortalama
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple
from uuid import UUID

from sqlalchemy import func, and_

from app.extensions import db
from app.models import SmartDevice, DeviceTelemetry, Notification

logger = logging.getLogger(__name__)

# Anomaly Detection Configuration
ZSCORE_THRESHOLD = 3.0  # 3 standart sapma = %99.7 dışında
MIN_SAMPLES = 10  # Minimum veri noktası (istatistik için)
LOOKBACK_DAYS = 7  # Kaç günlük veri kullanılsın
POWER_SPIKE_MULTIPLIER = 4.0  # Ani güç artışı çarpanı


class AnomalyDetector:
    """
    İstatistiksel anormallik tespit servisi.
    
    Kullanım:
        detector = AnomalyDetector()
        anomalies = detector.check_device(device_id, current_power=2000)
    """

    def __init__(
        self,
        zscore_threshold: float = ZSCORE_THRESHOLD,
        min_samples: int = MIN_SAMPLES,
        lookback_days: int = LOOKBACK_DAYS,
    ):
        self.zscore_threshold = zscore_threshold
        self.min_samples = min_samples
        self.lookback_days = lookback_days

    def get_device_stats(
        self,
        device_id: UUID,
        hour: Optional[int] = None,
    ) -> Dict[str, float]:
        """
        Cihazın geçmiş istatistiklerini hesapla.
        
        Args:
            device_id: Cihaz UUID
            hour: Belirli saat için istatistik (0-23), None ise tüm günü al
        
        Returns:
            {mean, std, min, max, count}
        """
        cutoff = datetime.now(timezone.utc) - timedelta(days=self.lookback_days)
        
        query = db.session.query(
            func.avg(DeviceTelemetry.power_w).label("mean"),
            func.stddev(DeviceTelemetry.power_w).label("std"),
            func.min(DeviceTelemetry.power_w).label("min"),
            func.max(DeviceTelemetry.power_w).label("max"),
            func.count(DeviceTelemetry.id).label("count"),
        ).filter(
            DeviceTelemetry.device_id == device_id,
            DeviceTelemetry.created_at >= cutoff,
            DeviceTelemetry.power_w.isnot(None),
        )
        
        # Saatlik pattern için filtrele
        if hour is not None:
            query = query.filter(
                func.extract("hour", DeviceTelemetry.created_at) == hour
            )
        
        result = query.first()
        
        return {
            "mean": float(result.mean) if result.mean else 0.0,
            "std": float(result.std) if result.std else 0.0,
            "min": float(result.min) if result.min else 0.0,
            "max": float(result.max) if result.max else 0.0,
            "count": int(result.count) if result.count else 0,
        }

    def calculate_zscore(
        self,
        value: float,
        mean: float,
        std: float,
    ) -> float:
        """
        Z-Score hesapla.
        
        Z = (X - μ) / σ
        
        |Z| > 3 ise anormallik var demektir (%99.7 dışında)
        """
        if std == 0:
            return 0.0
        return (value - mean) / std

    def check_power_anomaly(
        self,
        device_id: UUID,
        current_power: float,
        use_hourly_pattern: bool = True,
    ) -> Optional[Dict[str, Any]]:
        """
        Güç tüketimi anormalliği kontrol et.
        
        Args:
            device_id: Cihaz UUID
            current_power: Anlık güç değeri (W)
            use_hourly_pattern: Saatlik pattern kullan
        
        Returns:
            Anomaly dict veya None
        """
        current_hour = datetime.now(timezone.utc).hour if use_hourly_pattern else None
        
        stats = self.get_device_stats(device_id, hour=current_hour)
        
        # Yeterli veri yoksa kontrol etme
        if stats["count"] < self.min_samples:
            logger.debug(f"[Anomaly] Yetersiz veri: device={device_id}, count={stats['count']}")
            return None
        
        # Z-Score hesapla
        zscore = self.calculate_zscore(current_power, stats["mean"], stats["std"])
        
        # Ani güç artışı kontrolü (basit çarpan)
        power_ratio = current_power / stats["mean"] if stats["mean"] > 0 else 0
        
        anomaly = None
        
        # Z-Score anormalliği
        if abs(zscore) > self.zscore_threshold:
            anomaly_type = "high_power" if zscore > 0 else "low_power"
            anomaly = {
                "type": anomaly_type,
                "severity": "high" if abs(zscore) > 4 else "medium",
                "current_value": current_power,
                "expected_value": stats["mean"],
                "zscore": round(zscore, 2),
                "deviation_percent": round((current_power - stats["mean"]) / stats["mean"] * 100, 1) if stats["mean"] > 0 else 0,
                "message": self._generate_message(anomaly_type, current_power, stats["mean"], zscore),
            }
        
        # Ani güç artışı (Z-Score'dan bağımsız)
        elif power_ratio > POWER_SPIKE_MULTIPLIER:
            anomaly = {
                "type": "power_spike",
                "severity": "high",
                "current_value": current_power,
                "expected_value": stats["mean"],
                "zscore": round(zscore, 2),
                "deviation_percent": round((power_ratio - 1) * 100, 1),
                "message": f"Ani güç artışı! Normal: {stats['mean']:.0f}W, Şu an: {current_power:.0f}W ({power_ratio:.1f}x)",
            }
        
        if anomaly:
            anomaly["device_id"] = str(device_id)
            anomaly["stats"] = stats
            anomaly["hour"] = current_hour
            logger.warning(f"[Anomaly] Tespit edildi: {anomaly['type']} - device={device_id}")
        
        return anomaly

    def _generate_message(
        self,
        anomaly_type: str,
        current: float,
        expected: float,
        zscore: float,
    ) -> str:
        """Kullanıcı dostu anomaly mesajı oluştur."""
        if anomaly_type == "high_power":
            if current > expected * 10:
                return f"🚨 Olağandışı yüksek tüketim! Normal: {expected:.0f}W, Şu an: {current:.0f}W. Ek cihaz takılmış olabilir."
            elif current > expected * 4:
                return f"⚠️ Beklenenden çok yüksek tüketim. Normal: {expected:.0f}W, Şu an: {current:.0f}W"
            else:
                return f"📊 Normalin üzerinde tüketim tespit edildi. ({current:.0f}W vs {expected:.0f}W)"
        
        elif anomaly_type == "low_power":
            if current < expected * 0.1:
                return f"🔌 Cihaz kapalı veya bağlantı kopmuş olabilir. Beklenen: {expected:.0f}W, Şu an: {current:.0f}W"
            else:
                return f"📉 Beklenenden düşük tüketim. ({current:.0f}W vs {expected:.0f}W)"
        
        return f"Anormallik tespit edildi: {current:.0f}W (beklenen: {expected:.0f}W)"

    def check_all_devices(
        self,
        organization_id: UUID,
    ) -> List[Dict[str, Any]]:
        """
        Organizasyondaki tüm cihazları kontrol et.
        
        Returns:
            Anomaly listesi
        """
        devices = SmartDevice.query.filter_by(
            organization_id=organization_id,
            is_online=True,
        ).all()
        
        anomalies = []
        
        for device in devices:
            # Son telemetri verisini al
            latest = DeviceTelemetry.query.filter_by(
                device_id=device.id
            ).order_by(
                DeviceTelemetry.created_at.desc()
            ).first()
            
            if not latest or latest.power_w is None:
                continue
            
            anomaly = self.check_power_anomaly(device.id, latest.power_w)
            if anomaly:
                anomaly["device_name"] = device.name
                anomaly["device_external_id"] = device.external_id
                anomalies.append(anomaly)
        
        return anomalies


def create_anomaly_notification(
    anomaly: Dict[str, Any],
    organization_id: UUID,
    user_id: Optional[UUID] = None,
) -> Notification:
    """
    Anomaly için bildirim oluştur.
    
    Args:
        anomaly: Anomaly dict
        organization_id: Organizasyon UUID
        user_id: Hedef kullanıcı (opsiyonel)
    
    Returns:
        Notification instance
    """
    from app.models.enums import NotificationStatus
    
    severity_emoji = {"high": "🚨", "medium": "⚠️", "low": "📊"}
    emoji = severity_emoji.get(anomaly.get("severity", "low"), "📊")
    
    notification = Notification(
        organization_id=organization_id,
        user_id=user_id,
        title=f"{emoji} Olağandışı Aktivite Tespit Edildi",
        message=anomaly.get("message", "Anormallik tespit edildi"),
        notification_type="anomaly",
        priority=anomaly.get("severity", "medium"),
        data={
            "anomaly_type": anomaly.get("type"),
            "device_id": anomaly.get("device_id"),
            "device_name": anomaly.get("device_name"),
            "current_value": anomaly.get("current_value"),
            "expected_value": anomaly.get("expected_value"),
            "zscore": anomaly.get("zscore"),
        },
        status=NotificationStatus.PENDING,
    )
    
    db.session.add(notification)
    return notification


# Singleton instance
_anomaly_detector: Optional[AnomalyDetector] = None


def get_anomaly_detector() -> AnomalyDetector:
    """Anomaly detector singleton'ı döndür."""
    global _anomaly_detector
    if _anomaly_detector is None:
        _anomaly_detector = AnomalyDetector()
    return _anomaly_detector
