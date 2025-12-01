"""MQTT bridge that listens sensor events and pushes them through Socket.IO."""

from __future__ import annotations

import json
import logging
from typing import Any, Optional

import paho.mqtt.client as mqtt

from . import db
from .models import Device, SensorData, Site
from .realtime import emit_sensor_alert

logger = logging.getLogger(__name__)


_client: Optional[mqtt.Client] = None


def _resolve_device(payload: dict[str, Any]) -> Optional[Device]:
    device_identifier = payload.get("device_id") or payload.get("deviceId")
    serial_number = payload.get("serial_number") or payload.get("serialNumber")

    if device_identifier:
        try:
            numeric_id = int(device_identifier)
        except (TypeError, ValueError):
            numeric_id = None

        if numeric_id is not None:
            device = Device.query.filter_by(id=numeric_id).first()
            if device:
                return device

    serial_candidate = serial_number or device_identifier
    if serial_candidate:
        return Device.query.filter_by(serial_number=serial_candidate).first()

    return None


def _persist_sensor_data(device_identifier: str, sensor_type: str, value: float, metadata: dict[str, Any]):
    record = SensorData(
        device_id=device_identifier,
        sensor_type=sensor_type,
        value=value,
        metadata_info=metadata,  # type: ignore[arg-type]
    )
    db.session.add(record)
    db.session.commit()


def _handle_sensor_payload(app, payload: dict[str, Any], topic: str):
    print(f"[MQTT] _handle_sensor_payload başladı: {payload}", flush=True)
    try:
        device = _resolve_device(payload)
        print(f"[MQTT] Device resolved: {device}", flush=True)
        user_id = payload.get("user_id") or payload.get("userId")

        if not user_id and device:
            site: Site | None = device.site
            user_id = site.user_id if site else None

        sensor_type = payload.get("sensor_type") or payload.get("sensorType") or "sensor"
        value = payload.get("value")

        metadata = {
            "topic": topic,
            "raw": payload,
        }

        if device:
            metadata["device_id"] = device.id
            metadata["device_serial"] = device.serial_number

        try:
            numeric_value = float(value) if value is not None else None
            if numeric_value is not None:
                identifier = device.serial_number if device else payload.get("device_id", "unknown")
                _persist_sensor_data(identifier, sensor_type, numeric_value, metadata)
        except Exception as exc:  # noqa: BLE001
            app.logger.warning("SensorData kaydı oluşturulamadı: %s", exc)
            db.session.rollback()

        emit_sensor_alert(
            user_id,
            {
                "sensorType": sensor_type,
                "value": value,
                "label": payload.get("label") or payload.get("message") or "Sensör uyarısı",
                "severity": payload.get("severity", "info"),
                "topic": topic,
                "device": {
                    "id": device.id if device else None,
                    "serial": device.serial_number if device else None,
                    "name": device.name if device else None,
                },
            },
        )

    except Exception:
        app.logger.exception("MQTT payload işlenirken hata oluştu: topic=%s payload=%s", topic, payload)


def _on_connect(client: mqtt.Client, userdata, flags, reason_code):  # type: ignore[override]
    app = userdata["app"]
    topic = app.config["MQTT_SENSOR_TOPIC"]
    print(f"[MQTT] on_connect callback: rc={reason_code}")
    if reason_code != 0:
        print(f"[MQTT] Broker bağlantı hatası: rc={reason_code}")
        return

    result, mid = client.subscribe(topic)
    print(f"[MQTT] Subscribe: topic={topic}, result={result}, mid={mid}")


def _on_message(client: mqtt.Client, userdata, message):  # type: ignore[override]
    import sys
    app = userdata["app"]
    payload_text = message.payload.decode("utf-8", errors="ignore")
    print(f"[MQTT] Mesaj alındı: topic={message.topic}, payload={payload_text[:200]}", flush=True)
    sys.stdout.flush()

    try:
        payload = json.loads(payload_text)
    except json.JSONDecodeError:
        payload = {"raw": payload_text}

    with app.app_context():
        _handle_sensor_payload(app, payload, message.topic)


def _sanitize_broker_url(raw: str) -> str:
    """Remove protocol prefix if present (paho expects bare hostname)."""
    for prefix in ("mqtt://", "mqtts://", "tcp://", "ssl://"):
        if raw.lower().startswith(prefix):
            return raw[len(prefix):].rstrip("/")
    return raw.rstrip("/")


def init_mqtt_client(app, max_retries: int = 5, retry_delay: float = 2.0):
    """Initialize and start the MQTT client with retry logic."""
    import time

    global _client
    if _client is not None:
        return _client

    raw_url = app.config.get("MQTT_BROKER_URL")
    if not raw_url:
        print("[MQTT] MQTT_BROKER_URL tanımlı değil, MQTT dinleyicisi başlamayacak")
        return None

    broker_host = _sanitize_broker_url(raw_url)
    port = int(app.config.get("MQTT_BROKER_PORT", 1883))

    client = mqtt.Client(client_id=app.config.get("MQTT_CLIENT_ID", "awaxen-backend"), clean_session=True)

    username = app.config.get("MQTT_USERNAME")
    password = app.config.get("MQTT_PASSWORD")
    if username:
        client.username_pw_set(username=username, password=password)

    client.user_data_set({"app": app})
    client.on_connect = _on_connect
    client.on_message = _on_message

    for attempt in range(1, max_retries + 1):
        try:
            print(f"[MQTT] Broker'a bağlanılıyor: {broker_host}:{port} (deneme {attempt}/{max_retries})")
            client.connect(broker_host, port, keepalive=60)
            client.loop_start()
            _client = client
            print(f"[MQTT] Bağlantı başarılı -> {broker_host}:{port}")
            return _client
        except Exception as exc:
            print(f"[MQTT] Bağlantı hatası (deneme {attempt}): {exc}")
            if attempt < max_retries:
                time.sleep(retry_delay)

    print(f"[MQTT] {max_retries} deneme sonrası broker'a bağlanılamadı")
    return None
