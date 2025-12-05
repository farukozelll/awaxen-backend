"""Komut yönetimi endpoint'leri."""
from flask import jsonify, request

from . import api_bp
from .helpers import get_or_create_user
from .. import db
from ..models import Command, Device, Node, Site
from ..auth import requires_auth


@api_bp.route('/commands', methods=['POST'])
@requires_auth
def send_command():
    """
    Bir node'a komut gönder.
    ---
    tags:
      - Komut
    consumes:
      - application/json
    parameters:
      - in: body
        name: command
        schema:
          type: object
          properties:
            node_id:
              type: integer
            command_type:
              type: string
              example: SET_POWER
            payload:
              type: object
              example: {"state": "ON"}
    responses:
      201:
        description: Komut eklendi
    """
    user = get_or_create_user()
    data = request.json

    node = Node.query.join(Device).join(Site).filter(
        Node.id == data.get("node_id"),
        Site.user_id == user.id
    ).first()

    if not node:
        return jsonify({"error": "Node bulunamadı"}), 404

    command = Command(
        node_id=node.id,
        user_id=user.id,
        command_type=data.get("command_type", "SET_STATE"),
        payload=data.get("payload"),
        status="PENDING",
    )
    db.session.add(command)
    db.session.commit()

    return jsonify({"message": "Komut gönderildi", "command_id": command.id}), 201


@api_bp.route('/commands/<int:device_id>', methods=['GET'])
@requires_auth
def get_command_history(device_id):
    """
    Bir cihazın komut geçmişini getir.
    ---
    tags:
      - Komut
    parameters:
      - in: path
        name: device_id
        required: true
        schema:
          type: integer
    responses:
      200:
        description: Komut geçmişi döner
    """
    user = get_or_create_user()
    if not user:
        return jsonify({"error": "Kullanıcı bulunamadı"}), 401

    device = Device.query.join(Site).filter(
        Device.id == device_id,
        Site.user_id == user.id,
    ).first()

    if not device:
        return jsonify({"error": "Cihaz bulunamadı"}), 404

    commands = (
        Command.query.join(Node)
        .filter(Node.device_id == device_id)
        .order_by(Command.created_at.desc())
        .limit(200)
        .all()
    )

    return jsonify([
        {
            "id": cmd.id,
            "node_id": cmd.node_id,
            "command_type": cmd.command_type,
            "payload": cmd.payload,
            "status": cmd.status,
            "created_at": cmd.created_at.isoformat() if cmd.created_at else None,
            "executed_at": cmd.executed_at.isoformat() if cmd.executed_at else None,
        }
        for cmd in commands
    ])
