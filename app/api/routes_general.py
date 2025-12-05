"""Genel endpoint'ler (sağlık kontrolü, dashboard)."""
from flask import jsonify

from . import api_bp
from .helpers import get_or_create_user
from .. import db
from ..models import Device, Node, Site, Telemetry
from ..auth import requires_auth


@api_bp.route('/test-db', methods=['GET'])
def test_db_connection():
    """
    Veritabanı bağlantısını doğrula.
    ---
    tags:
      - Sağlık
    responses:
      200:
        description: TimescaleDB bağlantısı aktif
    """
    from sqlalchemy import text

    try:
        db.session.execute(text('SELECT 1'))
        return jsonify({"status": "ok", "message": "TimescaleDB bağlantısı aktif"})
    except Exception as exc:
        return jsonify({"status": "error", "message": str(exc)}), 500


@api_bp.route('/dashboard', methods=['GET'])
@requires_auth
def get_dashboard():
    """
    Token'daki kullanıcının dashboard verilerini getir.
    ---
    tags:
      - Dashboard
    security:
      - bearerAuth: []
    responses:
      200:
        description: Dashboard verisi
    """
    user = get_or_create_user()
    if not user:
        return jsonify({"error": "Kullanıcı bulunamadı"}), 401

    response_data = {
        "user": {
            "id": user.id,
            "full_name": user.full_name,
            "email": user.email,
            "role": user.role,
        },
        "sites": []
    }

    for site in user.sites:
        site_data = {
            "id": site.id,
            "name": site.name,
            "city": site.city,
            "location": site.location,
            "latitude": site.latitude,
            "longitude": site.longitude,
            "devices": []
        }
        for device in site.devices:
            device_data = {
                "id": device.id,
                "name": device.name,
                "serial_number": device.serial_number,
                "status": "Online" if device.is_online else "Offline",
                "nodes": []
            }
            for node in device.nodes:
                last_val = Telemetry.query.filter_by(node_id=node.id).order_by(Telemetry.time.desc()).first()
                device_data["nodes"].append({
                    "id": node.id,
                    "name": node.name,
                    "type": node.node_type,
                    "last_value": last_val.value if last_val else None,
                    "last_key": last_val.key if last_val else None,
                    "last_time": last_val.time.isoformat() if last_val else None,
                })
            site_data["devices"].append(device_data)
        response_data["sites"].append(site_data)

    return jsonify(response_data)
