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


def _parse_homeassistant_topic(topic: str, payload_text: str) -> Optional[dict[str, Any]]:
    """
    Home Assistant mqtt_statestream topic formatını parse et.
    
    Topic format: awaxen/sensors/<domain>/<entity_id>/<attribute>
    Örnek: awaxen/sensors/switch/tapo_priz_103/state -> ON
           awaxen/sensors/sensor/tapo_priz_103_current_consumption/state -> 45.5
    
    Returns:
        Parsed payload dict veya None
    """
    parts = topic.split('/')
    
    # awaxen/sensors/<domain>/<entity_id>/<attribute> formatı
    if len(parts) >= 5 and parts[0] == 'awaxen' and parts[1] == 'sensors':
        domain = parts[2]      # switch, sensor, light, etc.
        entity_id = parts[3]   # tapo_priz_103 veya tapo_priz_103_current_consumption
        attribute = parts[4]   # state, attributes, etc.
        
        # Entity ID'den cihaz adını ve metrik tipini ayıkla
        # Örn: tapo_priz_103_current_consumption -> device: tapo_priz_103, metric: current_consumption
        device_name = entity_id
        metric = None
        
        # Bilinen metrik suffix'leri
        metric_suffixes = [
            '_current_consumption', '_today_energy', '_power', '_energy',
            '_voltage', '_current', '_temperature', '_humidity',
            '_total_energy', '_daily_energy'
        ]
        
        for suffix in metric_suffixes:
            if entity_id.endswith(suffix):
                device_name = entity_id[:-len(suffix)]
                metric = suffix[1:]  # Remove leading underscore
                break
        
        # Değeri parse et
        value = payload_text.strip()
        
        # Sayısal değer mi kontrol et
        numeric_value = None
        try:
            numeric_value = float(value)
        except (ValueError, TypeError):
            pass
        
        # Payload oluştur
        payload = {
            "external_id": f"{domain}.{entity_id}",  # HA entity_id formatı
            "device_name": device_name,
            "domain": domain,
            "attribute": attribute,
            "ha_entity_id": entity_id,
        }
        
        # Switch durumu (ON/OFF)
        if domain == 'switch' and attribute == 'state':
            payload["state"] = value.upper()
            payload["is_on"] = value.upper() == 'ON'
        
        # Sensor değerleri
        elif domain == 'sensor' and numeric_value is not None:
            payload["value"] = numeric_value
            
            # Metrik tipine göre alan adı belirle
            if metric:
                if 'power' in metric or 'consumption' in metric:
                    payload["power"] = numeric_value
                    payload["power_w"] = numeric_value
                elif 'energy' in metric:
                    payload["energy"] = numeric_value
                    payload["energy_total_kwh"] = numeric_value
                elif 'voltage' in metric:
                    payload["voltage"] = numeric_value
                elif 'current' in metric and 'consumption' not in metric:
                    payload["current"] = numeric_value
                elif 'temperature' in metric:
                    payload["temperature"] = numeric_value
                elif 'humidity' in metric:
                    payload["humidity"] = numeric_value
        
        # Light durumu
        elif domain == 'light' and attribute == 'state':
            payload["state"] = value.upper()
            payload["is_on"] = value.upper() == 'ON'
        
        # Binary sensor
        elif domain == 'binary_sensor' and attribute == 'state':
            payload["state"] = value.lower()
            payload["is_on"] = value.lower() in ('on', 'true', '1')
        
        return payload
    
    return None


def _resolve_device_by_ha_entity(entity_id: str, device_name: str) -> Optional[SmartDevice]:
    """
    Home Assistant entity_id veya device_name ile cihaz bul.
    Önce external_id ile, sonra isim benzerliği ile arar.
    """
    # 1. Tam external_id eşleşmesi (switch.tapo_priz_103)
    device = SmartDevice.query.filter_by(external_id=entity_id).first()
    if device:
        return device
    
    # 2. Entity ID'nin son kısmı ile ara (tapo_priz_103)
    short_id = entity_id.split('.')[-1] if '.' in entity_id else entity_id
    device = SmartDevice.query.filter_by(external_id=short_id).first()
    if device:
        return device
    
    # 3. Device name ile ara
    device = SmartDevice.query.filter_by(external_id=device_name).first()
    if device:
        return device
    
    # 4. İsim benzerliği ile ara (LIKE query)
    device = SmartDevice.query.filter(
        SmartDevice.external_id.ilike(f"%{device_name}%")
    ).first()
    if device:
        return device
    
    # 5. Name alanında ara
    device = SmartDevice.query.filter(
        SmartDevice.name.ilike(f"%{device_name}%")
    ).first()
    
    return device


def _handle_homeassistant_message(app, ha_payload: dict[str, Any], topic: str):
    """
    Home Assistant formatındaki MQTT mesajını işle.
    """
    entity_id = ha_payload.get("external_id", "")
    device_name = ha_payload.get("device_name", "")
    domain = ha_payload.get("domain", "")
    
    logger.info(f"[MQTT-HA] Mesaj: entity={entity_id}, domain={domain}, data={ha_payload}")
    
    # Cihazı bul
    device = _resolve_device_by_ha_entity(entity_id, device_name)
    
    if not device:
        logger.debug(f"[MQTT-HA] Cihaz bulunamadı: {entity_id} / {device_name}")
        # Cihaz bulunamadı ama yine de Frontend'e gönder (keşif için)
        socketio.emit(
            "ha_device_update",
            {
                "entity_id": entity_id,
                "device_name": device_name,
                "domain": domain,
                "data": ha_payload,
                "timestamp": datetime.utcnow().isoformat(),
                "registered": False,
            },
            namespace="/",
        )
        return
    
    # Cihaz durumunu güncelle
    device.is_online = True
    device.last_seen = datetime.utcnow()
    
    # State değişikliği varsa kaydet (savings için)
    if "state" in ha_payload and domain in ('switch', 'light'):
        new_state = 'on' if ha_payload.get("is_on") else 'off'
        try:
            from app.services.savings_service import SavingsService
            SavingsService.record_device_state_change(
                device_id=str(device.id),
                new_state=new_state,
                triggered_by="homeassistant"
            )
        except Exception as e:
            logger.debug(f"[MQTT-HA] Savings kaydedilemedi: {e}")
    
    # Telemetri verisi varsa kaydet
    if any(k in ha_payload for k in ('power', 'power_w', 'energy', 'voltage', 'current', 'temperature', 'humidity')):
        try:
            telemetry = _persist_telemetry(device, ha_payload)
            logger.info(f"[MQTT-HA] Telemetri kaydedildi: {device.name}")
        except Exception as e:
            logger.warning(f"[MQTT-HA] Telemetri kaydedilemedi: {e}")
            db.session.rollback()
    else:
        db.session.commit()
    
    # Socket.IO ile Frontend'e gönder
    if device.organization_id:
        room = f"org_{device.organization_id}"
        
        # Telemetri event'i
        socketio.emit(
            "telemetry",
            {
                "device_id": str(device.id),
                "external_id": device.external_id,
                "name": device.name,
                "data": ha_payload,
                "timestamp": datetime.utcnow().isoformat(),
            },
            room=room,
        )
        
        # Device update event'i (state değişiklikleri için)
        if "state" in ha_payload:
            socketio.emit(
                "device_status",
                {
                    "device_id": str(device.id),
                    "external_id": device.external_id,
                    "name": device.name,
                    "is_online": True,
                    "is_on": ha_payload.get("is_on"),
                    "state": ha_payload.get("state"),
                    "timestamp": datetime.utcnow().isoformat(),
                },
                room=room,
            )
    
    # Global broadcast (tüm bağlı client'lara)
    socketio.emit(
        "device_update",
        {
            "device_id": str(device.id) if device else None,
            "entity_id": entity_id,
            "device_name": device.name if device else device_name,
            "domain": domain,
            "data": ha_payload,
            "timestamp": datetime.utcnow().isoformat(),
        },
        namespace="/",
    )


def _on_message(client: mqtt.Client, userdata, message):
    app = userdata["app"]
    payload_text = message.payload.decode("utf-8", errors="ignore")
    topic = message.topic
    
    logger.debug(f"[MQTT] Mesaj: topic={topic}, payload={payload_text[:100]}")

    with app.app_context():
        # Home Assistant mqtt_statestream formatını kontrol et
        ha_payload = _parse_homeassistant_topic(topic, payload_text)
        
        if ha_payload:
            # Home Assistant formatı
            _handle_homeassistant_message(app, ha_payload, topic)
        else:
            # Standart JSON format (Shelly, vb.)
            try:
                payload = json.loads(payload_text)
            except json.JSONDecodeError:
                payload = {"raw": payload_text}
            
            _handle_sensor_payload(app, payload, topic)


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
