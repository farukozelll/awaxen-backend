"""MQTT bridge that listens sensor events and pushes them through Socket.IO."""

from __future__ import annotations

import json
import logging
from typing import Any, Optional

import paho.mqtt.client as mqtt

from . import db, socketio
from .models import Device, Node, SensorData, Site, DiscoveryQueue, DiscoveryStatus
from .realtime import emit_sensor_alert

logger = logging.getLogger(__name__)


_client: Optional[mqtt.Client] = None


def _resolve_gateway(payload: dict[str, Any]) -> Optional[Device]:
    """
    Gateway (Core cihazı) çözümle.
    Gateway, veriyi toplayan ve backend'e ileten ana cihaztır.
    """
    gateway_serial = (
        payload.get("gateway_serial") 
        or payload.get("gatewaySerial") 
        or payload.get("serial_number") 
        or payload.get("serialNumber")
    )
    
    if gateway_serial:
        return Device.query.filter_by(serial_number=gateway_serial).first()
    
    # Fallback: device_id ile dene
    device_id = payload.get("device_id") or payload.get("deviceId")
    if device_id:
        try:
            numeric_id = int(device_id)
            return Device.query.filter_by(id=numeric_id).first()
        except (TypeError, ValueError):
            return Device.query.filter_by(serial_number=device_id).first()
    
    return None


def _resolve_node(payload: dict[str, Any], gateway: Device) -> Optional[Node]:
    """
    Payload içindeki node (uç cihaz) bilgisini çözümle.
    Node, gateway'e bağlı sensör/inverter/actuator'dır.
    """
    node_identifier = (
        payload.get("node_id") 
        or payload.get("nodeId")
        or payload.get("dev_eui")  # LoRa DevEUI
        or payload.get("devEui")
        or payload.get("node_address")
    )
    
    if not node_identifier:
        return None
    
    # Önce bu gateway'e bağlı node'larda ara
    node = Node.query.filter_by(
        device_id=gateway.id,
        node_address=str(node_identifier)
    ).first()
    
    if node:
        return node
    
    # Tüm node'larda ara (farklı gateway'e kayıtlı olabilir)
    return Node.query.filter_by(node_address=str(node_identifier)).first()


def _resolve_device(payload: dict[str, Any]) -> Optional[Device]:
    """Legacy: Geriye uyumluluk için eski çözümleme."""
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


def _add_to_discovery_queue(
    gateway: Device,
    node_identifier: str,
    payload: dict[str, Any],
) -> Optional[DiscoveryQueue]:
    """
    Bilinmeyen cihazı keşif kuyruğuna ekle veya güncelle.
    Eğer zaten varsa seen_count artırılır.
    """
    # Zaten kuyrukta mı?
    existing = DiscoveryQueue.query.filter_by(
        reported_by_device_id=gateway.id,
        device_identifier=node_identifier,
        status=DiscoveryStatus.PENDING.value,
    ).first()
    
    if existing:
        # Görülme sayısını artır, son görülme zamanını güncelle
        existing.seen_count = (existing.seen_count or 1) + 1
        existing.raw_data = payload  # Son veriyi sakla
        if "rssi" in payload:
            existing.signal_strength = payload.get("rssi")
        db.session.commit()
        logger.info(f"[Discovery] Mevcut keşif güncellendi: {node_identifier} (görülme: {existing.seen_count})")
        return None  # Yeni değil, bildirim gönderme
    
    # Protokol tahmini
    protocol = payload.get("protocol", "UNKNOWN")
    if "dev_eui" in payload or "devEui" in payload:
        protocol = "LORA"
    elif "ip" in payload or "modbus" in str(payload).lower():
        protocol = "MODBUS"
    
    # Cihaz tipi tahmini
    guessed_type = payload.get("device_type") or payload.get("deviceType")
    if not guessed_type:
        # Payload içeriğinden tahmin et
        payload_str = str(payload).lower()
        if "inverter" in payload_str or "pv" in payload_str:
            guessed_type = "INVERTER"
        elif "battery" in payload_str or "soc" in payload_str:
            guessed_type = "BATTERY_STORAGE"
        elif "temp" in payload_str or "humidity" in payload_str:
            guessed_type = "SENSOR_NODE"
    
    # Marka/model tahmini (Modbus cevabından)
    guessed_brand = payload.get("brand") or payload.get("manufacturer")
    guessed_model = payload.get("model")
    
    discovery = DiscoveryQueue(
        reported_by_device_id=gateway.id,
        device_identifier=node_identifier,
        protocol=protocol,
        guessed_type=guessed_type,
        guessed_brand=guessed_brand,
        guessed_model=guessed_model,
        raw_data=payload,
        signal_strength=payload.get("rssi"),
    )
    db.session.add(discovery)
    db.session.commit()
    
    logger.info(f"[Discovery] Yeni cihaz keşfedildi: {node_identifier} (gateway: {gateway.serial_number})")
    return discovery


def _emit_discovery_notification(gateway: Device, discovery: DiscoveryQueue):
    """
    Frontend'e Socket.IO ile yeni keşif bildirimi gönder.
    Sadece gateway sahibine gönderilir.
    """
    user_id = gateway.site.user_id if gateway.site else None
    if not user_id:
        return
    
    room = f"user_{user_id}"
    socketio.emit(
        "device_discovered",
        {
            "discovery_id": discovery.id,
            "device_identifier": discovery.device_identifier,
            "protocol": discovery.protocol,
            "guessed_type": discovery.guessed_type,
            "gateway_name": gateway.name,
            "site_name": gateway.site.name if gateway.site else None,
        },
        room=room,
    )
    logger.info(f"[Discovery] Bildirim gönderildi: user_{user_id} -> {discovery.device_identifier}")


def _handle_sensor_payload(app, payload: dict[str, Any], topic: str):
    """
    MQTT mesajını işle:
    1. Gateway'ı çözümle
    2. Node'u çözümle
    3. Kayıtlıysa telemetri kaydet
    4. Kayıtlı değilse DiscoveryQueue'ya ekle
    """
    print(f"[MQTT] _handle_sensor_payload başladı: {payload}", flush=True)
    
    try:
        # 1. Gateway'ı çözümle
        gateway = _resolve_gateway(payload)
        print(f"[MQTT] Gateway resolved: {gateway}", flush=True)
        
        if not gateway:
            # Gateway bulunamadı - legacy modu dene
            device = _resolve_device(payload)
            if device:
                gateway = device
            else:
                logger.warning(f"[MQTT] Bilinmeyen gateway'den veri: {payload}")
                return
        
        user_id = payload.get("user_id") or payload.get("userId")
        if not user_id and gateway.site:
            user_id = gateway.site.user_id
        
        # 2. Node identifier'ı çıkar
        node_identifier = (
            payload.get("node_id") 
            or payload.get("nodeId")
            or payload.get("dev_eui")
            or payload.get("devEui")
            or payload.get("node_address")
        )
        
        # 3. Node'u çözümle
        node = None
        if node_identifier:
            node = _resolve_node(payload, gateway)
            print(f"[MQTT] Node resolved: {node} (identifier: {node_identifier})", flush=True)
        
        # 4. Kayıtlı node varsa telemetri kaydet
        if node:
            sensor_type = payload.get("sensor_type") or payload.get("sensorType") or "sensor"
            value = payload.get("value")
            
            metadata = {
                "topic": topic,
                "raw": payload,
                "gateway_id": gateway.id,
                "gateway_serial": gateway.serial_number,
                "node_id": node.id,
                "node_address": node.node_address,
            }
            
            try:
                numeric_value = float(value) if value is not None else None
                if numeric_value is not None:
                    _persist_sensor_data(gateway.serial_number, sensor_type, numeric_value, metadata)
            except Exception as exc:
                app.logger.warning("SensorData kaydı oluşturulamadı: %s", exc)
                db.session.rollback()
            
            # Socket.IO ile canlı veri gönder
            emit_sensor_alert(
                user_id,
                {
                    "sensorType": sensor_type,
                    "value": value,
                    "label": payload.get("label") or payload.get("message") or "Sensör uyarısı",
                    "severity": payload.get("severity", "info"),
                    "topic": topic,
                    "device": {
                        "id": gateway.id,
                        "serial": gateway.serial_number,
                        "name": gateway.name,
                    },
                    "node": {
                        "id": node.id,
                        "name": node.name,
                        "address": node.node_address,
                    },
                },
            )
        
        # 5. Kayıtlı node yoksa ve node_identifier varsa -> Discovery Queue
        elif node_identifier:
            discovery = _add_to_discovery_queue(gateway, str(node_identifier), payload)
            if discovery:
                # Yeni keşif, frontend'e bildir
                _emit_discovery_notification(gateway, discovery)
        
        # 6. Node identifier yoksa, doğrudan gateway verisi olarak işle (legacy)
        else:
            sensor_type = payload.get("sensor_type") or payload.get("sensorType") or "sensor"
            value = payload.get("value")
            
            metadata = {
                "topic": topic,
                "raw": payload,
                "device_id": gateway.id,
                "device_serial": gateway.serial_number,
            }
            
            try:
                numeric_value = float(value) if value is not None else None
                if numeric_value is not None:
                    _persist_sensor_data(gateway.serial_number, sensor_type, numeric_value, metadata)
            except Exception as exc:
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
                        "id": gateway.id,
                        "serial": gateway.serial_number,
                        "name": gateway.name,
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
