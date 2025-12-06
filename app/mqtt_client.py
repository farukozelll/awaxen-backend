"""MQTT bridge v6.0 - SmartDevice telemetri işleme."""

from __future__ import annotations

import json
import logging
from datetime import datetime
from typing import Any, Optional

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


def _handle_sensor_payload(app, payload: dict[str, Any], topic: str):
    """
    MQTT mesajını işle:
    1. Device'ı çözümle
    2. Telemetri kaydet
    3. Socket.IO ile canlı veri gönder
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


def init_mqtt_client(app, max_retries: int = 5, retry_delay: float = 2.0):
    """MQTT client'ı başlat."""
    import time

    global _client
    if _client is not None:
        return _client

    raw_url = app.config.get("MQTT_BROKER_URL")
    if not raw_url:
        logger.warning("[MQTT] MQTT_BROKER_URL tanımlı değil")
        return None

    broker_host = _sanitize_broker_url(raw_url)
    port = int(app.config.get("MQTT_BROKER_PORT", 1883))

    client = mqtt.Client(
        client_id=app.config.get("MQTT_CLIENT_ID", "awaxen-backend"),
        clean_session=True
    )

    username = app.config.get("MQTT_USERNAME")
    password = app.config.get("MQTT_PASSWORD")
    if username:
        client.username_pw_set(username=username, password=password)

    client.user_data_set({"app": app})
    client.on_connect = _on_connect
    client.on_message = _on_message

    for attempt in range(1, max_retries + 1):
        try:
            logger.info(f"[MQTT] Bağlanılıyor: {broker_host}:{port} ({attempt}/{max_retries})")
            client.connect(broker_host, port, keepalive=60)
            client.loop_start()
            _client = client
            logger.info(f"[MQTT] Bağlantı başarılı: {broker_host}:{port}")
            return _client
        except Exception as exc:
            logger.warning(f"[MQTT] Bağlantı hatası ({attempt}): {exc}")
            if attempt < max_retries:
                time.sleep(retry_delay)

    logger.error(f"[MQTT] {max_retries} deneme sonrası bağlanılamadı")
    return None
