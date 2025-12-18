"""
Awaxen Real-Time Module - Socket.IO & Redis Pub/Sub.

IoT platformu için gerçek zamanlı veri akışı:
- Dashboard canlı güncelleme
- Cihaz durumu değişiklikleri
- Fiyat alarmları
- Bildirimler
- Telemetri stream

Room yapısı:
- user:{user_id} - Kullanıcıya özel bildirimler
- org:{org_id} - Organizasyon geneli
- device:{device_id} - Cihaz telemetrisi
- dashboard:{org_id} - Dashboard güncellemeleri
- prices - Fiyat güncellemeleri (global)
"""

from __future__ import annotations

import os
import json
import logging
from datetime import datetime, timezone
from typing import Any, Optional
from functools import wraps

from flask import request
from flask_socketio import disconnect, emit, join_room, leave_room, rooms

from app.extensions import socketio

logger = logging.getLogger(__name__)

# Room prefixes
ROOM_USER = "user:"
ROOM_ORG = "org:"
ROOM_DEVICE = "device:"
ROOM_DASHBOARD = "dashboard:"
ROOM_PRICES = "prices"
ROOM_ALERTS = "alerts:"


# ==========================================
# Room Helpers
# ==========================================

def _user_room(user_id: int | str) -> str:
    return f"{ROOM_USER}{user_id}"

def _org_room(org_id: int | str) -> str:
    return f"{ROOM_ORG}{org_id}"

def _device_room(device_id: int | str) -> str:
    return f"{ROOM_DEVICE}{device_id}"

def _dashboard_room(org_id: int | str) -> str:
    return f"{ROOM_DASHBOARD}{org_id}"

def _alert_room(org_id: int | str) -> str:
    return f"{ROOM_ALERTS}{org_id}"


# ==========================================
# Emit Helpers - Backend'den Frontend'e
# ==========================================

def emit_to_user(event: str, payload: dict[str, Any], user_id: int | str) -> None:
    """Belirli bir kullanıcıya event gönder."""
    if user_id in (None, ""):
        return
    message = _add_timestamp(payload)
    socketio.emit(event, message, room=_user_room(user_id))
    logger.debug(f"Emit to user {user_id}: {event}")


def emit_to_org(event: str, payload: dict[str, Any], org_id: int | str) -> None:
    """Organizasyondaki tüm kullanıcılara event gönder."""
    if org_id in (None, ""):
        return
    message = _add_timestamp(payload)
    socketio.emit(event, message, room=_org_room(org_id))
    logger.debug(f"Emit to org {org_id}: {event}")


def emit_to_device_subscribers(event: str, payload: dict[str, Any], device_id: int | str) -> None:
    """Cihazı dinleyen tüm kullanıcılara event gönder."""
    if device_id in (None, ""):
        return
    message = _add_timestamp(payload)
    socketio.emit(event, message, room=_device_room(device_id))


def emit_to_dashboard(event: str, payload: dict[str, Any], org_id: int | str) -> None:
    """Dashboard'u dinleyen kullanıcılara event gönder."""
    if org_id in (None, ""):
        return
    message = _add_timestamp(payload)
    socketio.emit(event, message, room=_dashboard_room(org_id))


def broadcast_price_update(payload: dict[str, Any]) -> None:
    """Fiyat güncellemesini tüm dinleyicilere gönder."""
    message = _add_timestamp(payload)
    socketio.emit("price_update", message, room=ROOM_PRICES)
    logger.info(f"Price update broadcast: {payload.get('price', 'N/A')} TL/kWh")


def broadcast_global(event: str, payload: dict[str, Any]) -> None:
    """Tüm bağlı kullanıcılara event gönder."""
    message = _add_timestamp(payload)
    socketio.emit(event, message, broadcast=True)


def _add_timestamp(payload: dict) -> dict:
    """Payload'a timestamp ekle."""
    message = dict(payload)
    message.setdefault("timestamp", datetime.now(timezone.utc).isoformat())
    return message


# ==========================================
# Specialized Event Emitters
# ==========================================

def emit_sensor_alert(user_id: int | str, payload: dict[str, Any]) -> None:
    """Sensör alarmı gönder."""
    message = dict(payload)
    message.setdefault("receivedAt", datetime.now(timezone.utc).isoformat())
    emit_to_user("sensor_alert", message, user_id)


def emit_device_status(org_id: str, device_id: str, status: dict) -> None:
    """
    Cihaz durumu değişikliği bildirimi.
    
    Args:
        org_id: Organizasyon ID
        device_id: Cihaz ID
        status: {"is_online": True, "last_seen": "...", "power_w": 1200}
    """
    payload = {
        "device_id": device_id,
        "status": status,
        "event_type": "device_status"
    }
    emit_to_org("device_status", payload, org_id)
    emit_to_device_subscribers("device_update", payload, device_id)


def emit_telemetry(org_id: str, device_id: str, telemetry: dict) -> None:
    """
    Canlı telemetri verisi gönder.
    
    Dashboard grafikleri için real-time veri akışı.
    """
    payload = {
        "device_id": device_id,
        "data": telemetry,
        "event_type": "telemetry"
    }
    emit_to_dashboard("telemetry", payload, org_id)
    emit_to_device_subscribers("telemetry", payload, device_id)


def emit_automation_triggered(org_id: str, automation: dict) -> None:
    """Otomasyon tetiklendiğinde bildirim."""
    payload = {
        "automation_id": automation.get("id"),
        "name": automation.get("name"),
        "action": automation.get("action"),
        "event_type": "automation_triggered"
    }
    emit_to_org("automation_triggered", payload, org_id)


def emit_notification(user_id: str, notification: dict) -> None:
    """Kullanıcıya bildirim gönder."""
    payload = {
        "id": notification.get("id"),
        "title": notification.get("title"),
        "message": notification.get("message"),
        "type": notification.get("type", "info"),
        "event_type": "notification"
    }
    emit_to_user("notification", payload, user_id)


def emit_price_alert(org_id: str, alert: dict) -> None:
    """Fiyat alarmı gönder."""
    payload = {
        "current_price": alert.get("current_price"),
        "threshold": alert.get("threshold"),
        "direction": alert.get("direction"),  # "above" or "below"
        "message": alert.get("message"),
        "event_type": "price_alert"
    }
    emit_to_org("price_alert", payload, org_id)


def emit_energy_summary(org_id: str, summary: dict) -> None:
    """Dashboard enerji özeti güncelle."""
    payload = {
        "total_consumption_kwh": summary.get("total_consumption_kwh"),
        "total_cost": summary.get("total_cost"),
        "savings": summary.get("savings"),
        "active_devices": summary.get("active_devices"),
        "event_type": "energy_summary"
    }
    emit_to_dashboard("energy_summary", payload, org_id)


# ==========================================
# Socket.IO Event Handlers
# ==========================================

@socketio.on("connect")
def handle_connect():
    """Yeni bağlantı kurulduğunda."""
    sid = request.sid
    logger.info(f"Client connected: {sid}")
    emit("connected", {
        "message": "Awaxen Real-Time bağlantısı kuruldu",
        "sid": sid,
        "timestamp": datetime.now(timezone.utc).isoformat()
    })


@socketio.on("disconnect")
def handle_disconnect():
    """Bağlantı koptuğunda."""
    sid = request.sid
    logger.info(f"Client disconnected: {sid}")


@socketio.on("authenticate")
def handle_authenticate(data):
    """
    Kullanıcı kimlik doğrulama ve room'lara katılma.
    
    Client gönderir:
    {
        "token": "JWT_TOKEN",
        "user_id": "uuid",
        "org_id": "uuid"
    }
    """
    user_id = data.get("user_id")
    org_id = data.get("org_id")
    
    if not user_id:
        emit("auth_error", {"error": "user_id required"})
        return
    
    # Kullanıcı room'una katıl
    join_room(_user_room(user_id))
    
    # Organizasyon room'una katıl
    if org_id:
        join_room(_org_room(org_id))
        join_room(_dashboard_room(org_id))
        join_room(_alert_room(org_id))
    
    emit("authenticated", {
        "user_id": user_id,
        "org_id": org_id,
        "rooms": list(rooms()),
        "message": "Başarıyla doğrulandı"
    })
    logger.info(f"User authenticated: {user_id}, org: {org_id}")


@socketio.on("join_user_room")
def handle_join_user_room(data):
    """Kullanıcı room'una katıl."""
    user_id = data.get("user_id") if isinstance(data, dict) else None
    if not user_id:
        emit("join_error", {"error": "user_id zorunludur"})
        return

    room = _user_room(user_id)
    join_room(room)
    emit("room_joined", {"room": room, "type": "user"})


@socketio.on("leave_user_room")
def handle_leave_user_room(data):
    """Kullanıcı room'undan ayrıl."""
    user_id = data.get("user_id") if isinstance(data, dict) else None
    if not user_id:
        emit("leave_error", {"error": "user_id zorunludur"})
        return

    room = _user_room(user_id)
    leave_room(room)
    emit("room_left", {"room": room})


@socketio.on("subscribe_device")
def handle_subscribe_device(data):
    """
    Cihaz telemetrisine abone ol.
    
    Dashboard'da belirli bir cihazın grafiğini izlemek için.
    """
    device_id = data.get("device_id")
    if not device_id:
        emit("subscribe_error", {"error": "device_id required"})
        return
    
    room = _device_room(device_id)
    join_room(room)
    emit("subscribed", {"device_id": device_id, "room": room})
    logger.debug(f"Client subscribed to device: {device_id}")


@socketio.on("unsubscribe_device")
def handle_unsubscribe_device(data):
    """Cihaz aboneliğinden çık."""
    device_id = data.get("device_id")
    if not device_id:
        return
    
    room = _device_room(device_id)
    leave_room(room)
    emit("unsubscribed", {"device_id": device_id})


@socketio.on("subscribe_prices")
def handle_subscribe_prices(data=None):
    """Fiyat güncellemelerine abone ol."""
    join_room(ROOM_PRICES)
    emit("subscribed", {"room": ROOM_PRICES, "type": "prices"})
    logger.debug("Client subscribed to price updates")


@socketio.on("unsubscribe_prices")
def handle_unsubscribe_prices(data=None):
    """Fiyat aboneliğinden çık."""
    leave_room(ROOM_PRICES)
    emit("unsubscribed", {"room": ROOM_PRICES})


@socketio.on("subscribe_dashboard")
def handle_subscribe_dashboard(data):
    """Dashboard güncellemelerine abone ol."""
    org_id = data.get("org_id")
    if not org_id:
        emit("subscribe_error", {"error": "org_id required"})
        return
    
    room = _dashboard_room(org_id)
    join_room(room)
    emit("subscribed", {"room": room, "type": "dashboard"})


@socketio.on("ping")
def handle_ping(data=None):
    """Heartbeat - bağlantı kontrolü."""
    emit("pong", {"timestamp": datetime.now(timezone.utc).isoformat()})


# ==========================================
# Redis Pub/Sub Integration
# ==========================================

class RedisPubSub:
    """
    Redis Pub/Sub entegrasyonu.
    
    Birden fazla backend instance'ı arasında mesaj senkronizasyonu.
    Celery task'larından real-time event gönderimi.
    """
    
    def __init__(self):
        self._redis = None
        self._pubsub = None
        self._channels = {
            "awaxen:telemetry": self._handle_telemetry,
            "awaxen:device_status": self._handle_device_status,
            "awaxen:price_update": self._handle_price_update,
            "awaxen:notification": self._handle_notification,
            "awaxen:automation": self._handle_automation,
            "awaxen:broadcast": self._handle_broadcast,
        }
    
    def init_app(self, app):
        """Flask app ile initialize et."""
        redis_url = app.config.get("REDIS_URL", os.getenv("REDIS_URL", "redis://localhost:6379/1"))
        
        try:
            import redis
            self._redis = redis.from_url(redis_url)
            self._pubsub = self._redis.pubsub()
            logger.info(f"Redis Pub/Sub initialized: {redis_url}")
        except Exception as e:
            logger.warning(f"Redis Pub/Sub initialization failed: {e}")
            self._redis = None
    
    def publish(self, channel: str, message: dict) -> bool:
        """Redis channel'a mesaj yayınla."""
        if not self._redis:
            logger.warning("Redis not available, skipping publish")
            return False
        
        try:
            self._redis.publish(channel, json.dumps(message))
            return True
        except Exception as e:
            logger.error(f"Redis publish error: {e}")
            return False
    
    def subscribe(self):
        """Tüm channel'lara abone ol."""
        if not self._pubsub:
            return
        
        try:
            self._pubsub.subscribe(**{ch: self._message_handler for ch in self._channels})
            logger.info(f"Subscribed to Redis channels: {list(self._channels.keys())}")
        except Exception as e:
            logger.error(f"Redis subscribe error: {e}")
    
    def _message_handler(self, message):
        """Redis'ten gelen mesajları işle."""
        if message["type"] != "message":
            return
        
        channel = message["channel"]
        if isinstance(channel, bytes):
            channel = channel.decode("utf-8")
        
        try:
            data = json.loads(message["data"])
            handler = self._channels.get(channel)
            if handler:
                handler(data)
        except Exception as e:
            logger.error(f"Redis message handler error: {e}")
    
    def _handle_telemetry(self, data):
        """Telemetri mesajını Socket.IO'ya ilet."""
        org_id = data.get("org_id")
        device_id = data.get("device_id")
        telemetry = data.get("data", {})
        
        if org_id and device_id:
            emit_telemetry(org_id, device_id, telemetry)
    
    def _handle_device_status(self, data):
        """Cihaz durumu mesajını Socket.IO'ya ilet."""
        org_id = data.get("org_id")
        device_id = data.get("device_id")
        status = data.get("status", {})
        
        if org_id and device_id:
            emit_device_status(org_id, device_id, status)
    
    def _handle_price_update(self, data):
        """Fiyat güncellemesini Socket.IO'ya ilet."""
        broadcast_price_update(data)
    
    def _handle_notification(self, data):
        """Bildirimi Socket.IO'ya ilet."""
        user_id = data.get("user_id")
        if user_id:
            emit_notification(user_id, data)
    
    def _handle_automation(self, data):
        """Otomasyon event'ini Socket.IO'ya ilet."""
        org_id = data.get("org_id")
        if org_id:
            emit_automation_triggered(org_id, data)
    
    def _handle_broadcast(self, data):
        """Global broadcast mesajını ilet."""
        event = data.get("event", "broadcast")
        payload = data.get("payload", {})
        broadcast_global(event, payload)
    
    # Convenience methods for publishing
    def publish_telemetry(self, org_id: str, device_id: str, data: dict):
        """Telemetri verisi yayınla."""
        return self.publish("awaxen:telemetry", {
            "org_id": org_id,
            "device_id": device_id,
            "data": data
        })
    
    def publish_device_status(self, org_id: str, device_id: str, status: dict):
        """Cihaz durumu yayınla."""
        return self.publish("awaxen:device_status", {
            "org_id": org_id,
            "device_id": device_id,
            "status": status
        })
    
    def publish_price_update(self, price: float, hour: int, date: str):
        """Fiyat güncellemesi yayınla."""
        return self.publish("awaxen:price_update", {
            "price": price,
            "hour": hour,
            "date": date
        })
    
    def publish_notification(self, user_id: str, notification: dict):
        """Bildirim yayınla."""
        return self.publish("awaxen:notification", {
            "user_id": user_id,
            **notification
        })


# Global instance
redis_pubsub = RedisPubSub()
