"""Socket.IO event handlers and helpers for user scoped notifications."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from flask_socketio import disconnect, emit, join_room, leave_room

from app.extensions import socketio

ROOM_PREFIX = "user:"


def _user_room(user_id: int | str) -> str:
    return f"{ROOM_PREFIX}{user_id}"


def emit_to_user(event: str, payload: dict[str, Any], user_id: int | str) -> None:
    if user_id in (None, ""):
        return
    socketio.emit(event, dict(payload), room=_user_room(user_id))


def emit_sensor_alert(user_id: int | str, payload: dict[str, Any]) -> None:
    message = dict(payload)
    message.setdefault("receivedAt", datetime.now(timezone.utc).isoformat())
    emit_to_user("sensor_alert", message, user_id)


@socketio.on("connect")
def handle_connect():
    emit("socket_connected", {"message": "Socket.IO bağlantısı kuruldu"})


@socketio.on("disconnect")
def handle_disconnect():
    # Flask-SocketIO otomatik olarak bağlantıyı kapatır, biz sadece log/fallback mesajı gönderebiliriz.
    pass


@socketio.on("join_user_room")
def handle_join_user_room(data):
    user_id = data.get("user_id") if isinstance(data, dict) else None
    if not user_id:
        emit("join_error", {"error": "user_id zorunludur"})
        disconnect()
        return

    room = _user_room(user_id)
    join_room(room)
    emit("join_ack", {"room": room})


@socketio.on("leave_user_room")
def handle_leave_user_room(data):
    user_id = data.get("user_id") if isinstance(data, dict) else None
    if not user_id:
        emit("leave_error", {"error": "user_id zorunludur"})
        return

    room = _user_room(user_id)
    leave_room(room)
    emit("leave_ack", {"room": room})
