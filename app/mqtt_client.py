"""MQTT bridge v6.0 - SmartDevice telemetri işleme."""

from __future__ import annotations

import json
import logging
from datetime import datetime
from typing import Any, Optional
from uuid import uuid4

import paho.mqtt.client as mqtt

from app.extensions import db, socketio
from app.models import SmartDevice, Gateway, DeviceTelemetry
from app.realtime import emit_sensor_alert

logger = logging.getLogger(__name__)

_client: Optional[mqtt.Client] = None


def _resolve_device(payload: dict[str, Any]) -> Optional[SmartDevice]:
    """
    Payload'dan SmartDevice çözümle.
    external_id veya device_id ile arama yapar.
    """
    # external_id ile ara (Shelly ID, MAC adresi vb.)
    external_id = (
        payload.get("external_id")
        or payload.get("device_id")
        or payload.get("deviceId")
        or payload.get("id")
    )
    
    if external_id:
        device = SmartDevice.query.filter_by(external_id=str(external_id)).first()
        if device:
            return device
    
    # UUID ile ara
    device_uuid = payload.get("device_uuid")
    if device_uuid:
        try:
            return SmartDevice.query.filter_by(id=device_uuid).first()
        except Exception:
            pass
    
    return None


def _resolve_gateway(payload: dict[str, Any]) -> Optional[Gateway]:
    """Gateway çözümle (serial_number ile)."""
    serial = (
        payload.get("gateway_serial")
        or payload.get("serial_number")
        or payload.get("serialNumber")
    )
    
    if serial:
        return Gateway.query.filter_by(serial_number=serial).first()
    
    return None


def _persist_telemetry(device: SmartDevice, data: dict[str, Any]):
    """Telemetri verisini DeviceTelemetry tablosuna kaydet."""
    telemetry = DeviceTelemetry(
        device_id=device.id,
        power_w=data.get("power") or data.get("power_w"),
        voltage=data.get("voltage"),
        current=data.get("current"),
        energy_total_kwh=data.get("energy") or data.get("energy_total_kwh"),
        temperature=data.get("temperature") or data.get("temp"),
        humidity=data.get("humidity"),
        raw_data=data,
    )
    db.session.add(telemetry)
    
    # Cihaz durumunu güncelle
    device.is_online = True
    device.last_seen = datetime.utcnow()
    
    db.session.commit()
    return telemetry


def _check_realtime_anomaly(device: SmartDevice, power_w: float):
    """
    Real-time anomaly kontrolü.
    Telemetri geldiğinde anında kontrol et ve bildirim oluştur.
    """
    try:
        from app.services.anomaly_service import get_anomaly_detector, create_anomaly_notification
        
        detector = get_anomaly_detector()
        anomaly = detector.check_power_anomaly(device.id, power_w)
        
        if anomaly:
            # Yüksek seviye anomaliler için bildirim
            if anomaly.get("severity") in ("high", "medium"):
                anomaly["device_name"] = device.name
                create_anomaly_notification(anomaly, device.organization_id)
                db.session.commit()
                logger.warning(f"[Anomaly] Real-time tespit: {device.name} - {anomaly['message']}")
                
                # Socket.IO ile anlık bildirim
                if device.organization_id:
                    from app.extensions import socketio
                    room = f"org_{device.organization_id}"
                    socketio.emit("anomaly_detected", {
                        "device_id": str(device.id),
                        "device_name": device.name,
                        "type": anomaly.get("type"),
                        "severity": anomaly.get("severity"),
                        "message": anomaly.get("message"),
                        "current_value": anomaly.get("current_value"),
                        "expected_value": anomaly.get("expected_value"),
                    }, room=room)
    except Exception as e:
        logger.debug(f"[Anomaly] Real-time kontrol hatası: {e}")


def _handle_sensor_payload(app, payload: dict[str, Any], topic: str):
    """
    MQTT mesajını işle:
    1. Device'ı çözümle
    2. Telemetri kaydet
    3. Socket.IO ile canlı veri gönder
    4. Real-time anomaly kontrolü
    """
    logger.debug(f"[MQTT] Payload alındı: {payload}")
    
    try:
        # Device'ı çözümle
        device = _resolve_device(payload)
        
        if not device:
            # Gateway üzerinden gelen veri olabilir
            gateway = _resolve_gateway(payload)
            if gateway:
                logger.info(f"[MQTT] Gateway verisi: {gateway.serial_number}")
            else:
                logger.warning(f"[MQTT] Bilinmeyen cihazdan veri: {payload}")
            return
        
        # Telemetri verisi
        data = payload.get("data", payload)
        
        # Telemetri kaydet
        try:
            telemetry = _persist_telemetry(device, data)
            logger.info(f"[MQTT] Telemetri kaydedildi: device={device.external_id}")
        except Exception as exc:
            logger.warning(f"Telemetri kaydedilemedi: {exc}")
            db.session.rollback()
            return
        
        # Real-time anomaly kontrolü
        power_w = data.get("power") or data.get("power_w")
        if power_w is not None:
            _check_realtime_anomaly(device, float(power_w))
        
        # Socket.IO ile canlı veri gönder
        if device.organization_id:
            room = f"org_{device.organization_id}"
            socketio.emit(
                "telemetry",
                {
                    "device_id": str(device.id),
                    "external_id": device.external_id,
                    "name": device.name,
                    "data": data,
                    "timestamp": datetime.utcnow().isoformat(),
                },
                room=room,
            )
        
        # Eski format için de emit et (geriye uyumluluk)
        emit_sensor_alert(
            None,  # user_id artık organization bazlı
            {
                "sensorType": data.get("sensor_type", "power"),
                "value": data.get("power") or data.get("value"),
                "device": {
                    "id": str(device.id),
                    "external_id": device.external_id,
                    "name": device.name,
                },
                "topic": topic,
            },
        )
    
    except Exception:
        logger.exception(f"MQTT payload işlenirken hata: topic={topic}")


def _on_connect(client: mqtt.Client, userdata, flags, reason_code):
    app = userdata["app"]
    topic = app.config["MQTT_SENSOR_TOPIC"]
    logger.info(f"[MQTT] Bağlandı: rc={reason_code}")
    
    if reason_code != 0:
        logger.error(f"[MQTT] Bağlantı hatası: rc={reason_code}")
        return

    result, mid = client.subscribe(topic)
    logger.info(f"[MQTT] Subscribe: topic={topic}, result={result}")


def _on_message(client: mqtt.Client, userdata, message):
    app = userdata["app"]
    payload_text = message.payload.decode("utf-8", errors="ignore")
    logger.debug(f"[MQTT] Mesaj: topic={message.topic}")

    try:
        payload = json.loads(payload_text)
    except json.JSONDecodeError:
        payload = {"raw": payload_text}

    with app.app_context():
        _handle_sensor_payload(app, payload, message.topic)


def _sanitize_broker_url(raw: str) -> str:
    """Protokol prefix'ini kaldır."""
    for prefix in ("mqtt://", "mqtts://", "tcp://", "ssl://"):
        if raw.lower().startswith(prefix):
            return raw[len(prefix):].rstrip("/")
    return raw.rstrip("/")


def _on_disconnect(client: mqtt.Client, userdata, reason_code):
    """Bağlantı koptuğunda çağrılır - otomatik reconnect tetikler."""
    logger.warning(f"[MQTT] Bağlantı koptu: rc={reason_code}")
    # Paho MQTT v2.0+ otomatik reconnect yapıyor, sadece log


def init_mqtt_client(app, reconnect_delay_min: float = 1.0, reconnect_delay_max: float = 120.0):
    """
    MQTT client'ı başlat - sonsuz reconnect döngüsü ile.
    
    Args:
        app: Flask application
        reconnect_delay_min: Minimum reconnect bekleme süresi (saniye)
        reconnect_delay_max: Maximum reconnect bekleme süresi (saniye)
    """
    import time
    import threading

    global _client
    if _client is not None:
        return _client

    raw_url = app.config.get("MQTT_BROKER_URL")
    if not raw_url:
        logger.warning("[MQTT] MQTT_BROKER_URL tanımlı değil")
        return None

    broker_host = _sanitize_broker_url(raw_url)
    port = int(app.config.get("MQTT_BROKER_PORT", 1883))

    base_client_id = app.config.get("MQTT_CLIENT_ID", "awaxen-backend")
    suffix = uuid4().hex[:6]
    max_len = 23  # MQTT spec limit for client IDs
    max_base_len = max_len - len(suffix) - 1  # leave room for "-" and suffix
    if max_base_len < 1:
        max_base_len = max_len
    trimmed_base = (base_client_id or "awaxen-backend")[:max_base_len]
    if not trimmed_base:
        trimmed_base = "awaxen"
    unique_client_id = f"{trimmed_base}-{suffix}"

    client = mqtt.Client(
        client_id=unique_client_id,
        clean_session=True
    )

    username = app.config.get("MQTT_USERNAME")
    password = app.config.get("MQTT_PASSWORD")
    if username:
        client.username_pw_set(username=username, password=password)

    client.user_data_set({"app": app})
    client.on_connect = _on_connect
    client.on_message = _on_message
    client.on_disconnect = _on_disconnect
    
    # Paho MQTT v2.0+ için otomatik reconnect ayarları
    client.reconnect_delay_set(
        min_delay=reconnect_delay_min,
        max_delay=reconnect_delay_max
    )

    def connect_with_infinite_retry():
        """Sonsuz döngüde bağlanmaya çalış."""
        global _client
        attempt = 0
        current_delay = reconnect_delay_min
        
        while True:
            attempt += 1
            try:
                logger.info(f"[MQTT] Bağlanılıyor: {broker_host}:{port} (deneme #{attempt})")
                client.connect(broker_host, port, keepalive=60)
                client.loop_start()
                _client = client
                logger.info(f"[MQTT] Bağlantı başarılı: {broker_host}:{port}")
                return
            except Exception as exc:
                logger.warning(f"[MQTT] Bağlantı hatası (#{attempt}): {exc}")
                logger.info(f"[MQTT] {current_delay:.1f}s sonra tekrar denenecek...")
                time.sleep(current_delay)
                # Exponential backoff with max limit
                current_delay = min(current_delay * 2, reconnect_delay_max)

    # İlk bağlantıyı dene, başarısız olursa arka planda devam et
    try:
        logger.info(f"[MQTT] İlk bağlantı deneniyor: {broker_host}:{port}")
        client.connect(broker_host, port, keepalive=60)
        client.loop_start()
        _client = client
        logger.info(f"[MQTT] Bağlantı başarılı: {broker_host}:{port}")
        return _client
    except Exception as exc:
        logger.warning(f"[MQTT] İlk bağlantı başarısız: {exc}")
        logger.info("[MQTT] Arka planda sonsuz reconnect başlatılıyor...")
        # Arka plan thread'inde sonsuz döngü başlat
        reconnect_thread = threading.Thread(
            target=connect_with_infinite_retry,
            daemon=True,
            name="mqtt-reconnect"
        )
        reconnect_thread.start()
        return None  # İlk bağlantı başarısız ama arka planda denenecek
