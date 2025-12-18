"""
Firmware & OTA Update API Endpoints - v6.0.

Gateway ve ESP32 cihazlar için uzaktan firmware güncelleme.
"""
import os
import hashlib
from datetime import datetime, timezone
from flask import Blueprint, jsonify, request, current_app
from flasgger import swag_from
from werkzeug.utils import secure_filename

from app.extensions import db
from app.auth import requires_auth
from app.api.helpers import get_current_user, get_pagination_params, paginate_response
from app.models import (
    SmartDevice, Gateway, User,
    Firmware, FirmwareUpdate
)

firmware_bp = Blueprint("firmware", __name__)

ALLOWED_EXTENSIONS = {'bin', 'hex', 'elf'}
MAX_FILE_SIZE = 16 * 1024 * 1024  # 16MB


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS


def calculate_file_hash(file_data):
    """SHA256 hash hesapla."""
    return hashlib.sha256(file_data).hexdigest()


# ==========================================
# Firmware Management
# ==========================================

@firmware_bp.route("/firmware", methods=["GET", "OPTIONS"])
@requires_auth
@swag_from({
    "tags": ["Firmware"],
    "summary": "Firmware listesini getir",
    "parameters": [
        {"name": "device_type", "in": "query", "type": "string", "description": "Cihaz tipi filtresi"},
        {"name": "is_stable", "in": "query", "type": "boolean", "description": "Sadece stable versiyonlar"},
        {"name": "page", "in": "query", "type": "integer", "default": 1},
        {"name": "pageSize", "in": "query", "type": "integer", "default": 20}
    ],
    "responses": {
        200: {"description": "Firmware listesi"}
    }
})
def list_firmwares():
    """Mevcut firmware versiyonlarını listele."""
    user = get_current_user()
    if not user:
        return jsonify({"error": "Unauthorized"}), 401
    
    # Sadece admin görebilir
    user_role = user.role.code if user.role else None
    if user_role not in ["admin", "super_admin"]:
        return jsonify({"error": "Forbidden"}), 403
    
    page, page_size = get_pagination_params()
    device_type = request.args.get("device_type")
    is_stable = request.args.get("is_stable")
    
    query = Firmware.query.filter_by(is_active=True)
    
    if device_type:
        query = query.filter_by(device_type=device_type)
    if is_stable is not None:
        query = query.filter_by(is_stable=is_stable.lower() == "true")
    
    query = query.order_by(Firmware.version_code.desc())
    
    total = query.count()
    firmwares = query.offset((page - 1) * page_size).limit(page_size).all()
    
    return jsonify(paginate_response([f.to_dict() for f in firmwares], total, page, page_size))


@firmware_bp.route("/firmware/<uuid:firmware_id>", methods=["GET", "OPTIONS"])
@requires_auth
@swag_from({
    "tags": ["Firmware"],
    "summary": "Firmware detayını getir",
    "parameters": [
        {"name": "firmware_id", "in": "path", "type": "string", "required": True}
    ],
    "responses": {
        200: {"description": "Firmware detayı"},
        404: {"description": "Firmware bulunamadı"}
    }
})
def get_firmware(firmware_id):
    """Belirli bir firmware'in detayını getir."""
    user = get_current_user()
    if not user:
        return jsonify({"error": "Unauthorized"}), 401
    
    firmware = Firmware.query.get(firmware_id)
    if not firmware:
        return jsonify({"error": "Firmware not found"}), 404
    
    return jsonify(firmware.to_dict())


@firmware_bp.route("/firmware/upload", methods=["POST", "OPTIONS"])
@requires_auth
@swag_from({
    "tags": ["Firmware"],
    "summary": "Yeni firmware yükle",
    "consumes": ["multipart/form-data"],
    "parameters": [
        {"name": "file", "in": "formData", "type": "file", "required": True, "description": ".bin firmware dosyası"},
        {"name": "version", "in": "formData", "type": "string", "required": True, "example": "1.2.3"},
        {"name": "version_code", "in": "formData", "type": "integer", "required": True, "example": 123},
        {"name": "device_type", "in": "formData", "type": "string", "required": True, "example": "gateway"},
        {"name": "hardware_version", "in": "formData", "type": "string", "example": "v2"},
        {"name": "release_notes", "in": "formData", "type": "string"},
        {"name": "is_stable", "in": "formData", "type": "boolean", "default": False},
        {"name": "is_mandatory", "in": "formData", "type": "boolean", "default": False}
    ],
    "responses": {
        201: {"description": "Firmware yüklendi"},
        400: {"description": "Geçersiz dosya"},
        403: {"description": "Yetki yok"}
    }
})
def upload_firmware():
    """Yeni firmware dosyası yükle."""
    user = get_current_user()
    if not user:
        return jsonify({"error": "Unauthorized"}), 401
    
    # Sadece super_admin yükleyebilir
    user_role = user.role.code if user.role else None
    if user_role != "super_admin":
        return jsonify({"error": "Only super admins can upload firmware"}), 403
    
    # Dosya kontrolü
    if 'file' not in request.files:
        return jsonify({"error": "No file provided"}), 400
    
    file = request.files['file']
    if file.filename == '':
        return jsonify({"error": "No file selected"}), 400
    
    if not allowed_file(file.filename):
        return jsonify({"error": f"Invalid file type. Allowed: {', '.join(ALLOWED_EXTENSIONS)}"}), 400
    
    # Form verileri
    version = request.form.get("version")
    version_code = request.form.get("version_code", type=int)
    device_type = request.form.get("device_type")
    
    if not version or not version_code or not device_type:
        return jsonify({"error": "version, version_code and device_type are required"}), 400
    
    # Aynı versiyon var mı kontrol et
    existing = Firmware.query.filter_by(device_type=device_type, version=version).first()
    if existing:
        return jsonify({"error": f"Firmware {version} for {device_type} already exists"}), 400
    
    # Dosyayı oku
    file_data = file.read()
    file_size = len(file_data)
    
    if file_size > MAX_FILE_SIZE:
        return jsonify({"error": f"File too large. Max size: {MAX_FILE_SIZE // (1024*1024)}MB"}), 400
    
    file_hash = calculate_file_hash(file_data)
    filename = secure_filename(f"{device_type}_{version}_{file.filename}")
    
    # Dosyayı kaydet (S3/MinIO veya local)
    upload_folder = os.getenv("FIRMWARE_UPLOAD_FOLDER", "/app/uploads/firmware")
    os.makedirs(upload_folder, exist_ok=True)
    
    file_path = os.path.join(upload_folder, filename)
    with open(file_path, 'wb') as f:
        f.write(file_data)
    
    # URL oluştur
    base_url = os.getenv("FIRMWARE_BASE_URL", request.host_url.rstrip('/'))
    file_url = f"{base_url}/firmware/download/{filename}"
    
    # Veritabanına kaydet
    firmware = Firmware(
        version=version,
        version_code=version_code,
        device_type=device_type,
        hardware_version=request.form.get("hardware_version"),
        file_name=filename,
        file_size=file_size,
        file_hash=file_hash,
        file_url=file_url,
        release_notes=request.form.get("release_notes"),
        is_stable=request.form.get("is_stable", "false").lower() == "true",
        is_mandatory=request.form.get("is_mandatory", "false").lower() == "true",
        rollout_percentage=request.form.get("rollout_percentage", 100, type=int),
        uploaded_by=user.id
    )
    
    db.session.add(firmware)
    db.session.commit()
    
    current_app.logger.info(f"Firmware uploaded: {device_type} v{version} by {user.email}")
    
    return jsonify(firmware.to_dict()), 201


@firmware_bp.route("/firmware/<uuid:firmware_id>", methods=["DELETE", "OPTIONS"])
@requires_auth
@swag_from({
    "tags": ["Firmware"],
    "summary": "Firmware'i sil (soft delete)",
    "parameters": [
        {"name": "firmware_id", "in": "path", "type": "string", "required": True}
    ],
    "responses": {
        200: {"description": "Firmware silindi"},
        403: {"description": "Yetki yok"},
        404: {"description": "Firmware bulunamadı"}
    }
})
def delete_firmware(firmware_id):
    """Firmware'i deaktive et."""
    user = get_current_user()
    if not user:
        return jsonify({"error": "Unauthorized"}), 401
    
    user_role = user.role.code if user.role else None
    if user_role != "super_admin":
        return jsonify({"error": "Only super admins can delete firmware"}), 403
    
    firmware = Firmware.query.get(firmware_id)
    if not firmware:
        return jsonify({"error": "Firmware not found"}), 404
    
    firmware.is_active = False
    db.session.commit()
    
    return jsonify({"message": "Firmware deactivated"})


# ==========================================
# OTA Updates
# ==========================================

@firmware_bp.route("/devices/<uuid:device_id>/update-firmware", methods=["POST", "OPTIONS"])
@requires_auth
@swag_from({
    "tags": ["Firmware"],
    "summary": "Cihaza firmware güncelleme emri gönder",
    "description": "MQTT üzerinden cihaza güncelleme komutu gönderir.",
    "parameters": [
        {"name": "device_id", "in": "path", "type": "string", "required": True},
        {
            "name": "body",
            "in": "body",
            "schema": {
                "type": "object",
                "properties": {
                    "firmware_id": {"type": "string", "format": "uuid"},
                    "force": {"type": "boolean", "default": False, "description": "Zorunlu güncelleme"}
                }
            }
        }
    ],
    "responses": {
        200: {"description": "Güncelleme emri gönderildi"},
        400: {"description": "Geçersiz istek"},
        404: {"description": "Cihaz veya firmware bulunamadı"}
    }
})
def update_device_firmware(device_id):
    """Cihaza firmware güncelleme emri gönder."""
    user = get_current_user()
    if not user or not user.organization_id:
        return jsonify({"error": "Unauthorized"}), 401
    
    # Admin kontrolü
    user_role = user.role.code if user.role else None
    if user_role not in ["admin", "super_admin"]:
        return jsonify({"error": "Only admins can trigger firmware updates"}), 403
    
    # Cihaz kontrolü
    device = SmartDevice.query.filter_by(
        id=device_id,
        organization_id=user.organization_id
    ).first()
    
    if not device:
        return jsonify({"error": "Device not found"}), 404
    
    data = request.get_json() or {}
    firmware_id = data.get("firmware_id")
    force = data.get("force", False)
    
    # Firmware seç
    if firmware_id:
        firmware = Firmware.query.get(firmware_id)
    else:
        # En son stable firmware'i bul
        firmware = Firmware.query.filter_by(
            device_type=device.type or "esp32",
            is_active=True,
            is_stable=True
        ).order_by(Firmware.version_code.desc()).first()
    
    if not firmware:
        return jsonify({"error": "No firmware available for this device type"}), 404
    
    # Güncelleme kaydı oluştur
    update = FirmwareUpdate(
        device_id=device.id,
        firmware_id=firmware.id,
        from_version=device.firmware_version,
        to_version=firmware.version,
        status="pending",
        triggered_by=user.id,
        trigger_type="manual"
    )
    db.session.add(update)
    db.session.commit()
    
    # MQTT üzerinden güncelleme emri gönder
    try:
        from app.mqtt_client import mqtt_client
        
        topic = f"awaxen/devices/{device.external_id or device.id}/ota"
        payload = {
            "command": "update",
            "firmware_url": firmware.file_url,
            "version": firmware.version,
            "version_code": firmware.version_code,
            "hash": firmware.file_hash,
            "size": firmware.file_size,
            "force": force,
            "update_id": str(update.id)
        }
        
        mqtt_client.publish(topic, payload)
        
        update.status = "downloading"
        update.started_at = utcnow()
        db.session.commit()
        
        current_app.logger.info(f"OTA update triggered: device={device.id}, firmware={firmware.version}")
        
    except Exception as e:
        current_app.logger.error(f"MQTT publish error: {e}")
        update.status = "failed"
        update.error_message = str(e)
        db.session.commit()
        return jsonify({"error": f"Failed to send update command: {e}"}), 500
    
    return jsonify({
        "message": "Firmware update initiated",
        "update": update.to_dict()
    })


@firmware_bp.route("/gateways/<uuid:gateway_id>/update-firmware", methods=["POST", "OPTIONS"])
@requires_auth
@swag_from({
    "tags": ["Firmware"],
    "summary": "Gateway'e firmware güncelleme emri gönder",
    "parameters": [
        {"name": "gateway_id", "in": "path", "type": "string", "required": True},
        {
            "name": "body",
            "in": "body",
            "schema": {
                "type": "object",
                "properties": {
                    "firmware_id": {"type": "string", "format": "uuid"},
                    "force": {"type": "boolean", "default": False}
                }
            }
        }
    ],
    "responses": {
        200: {"description": "Güncelleme emri gönderildi"},
        404: {"description": "Gateway bulunamadı"}
    }
})
def update_gateway_firmware(gateway_id):
    """Gateway'e firmware güncelleme emri gönder."""
    user = get_current_user()
    if not user or not user.organization_id:
        return jsonify({"error": "Unauthorized"}), 401
    
    user_role = user.role.code if user.role else None
    if user_role not in ["admin", "super_admin"]:
        return jsonify({"error": "Only admins can trigger firmware updates"}), 403
    
    gateway = Gateway.query.filter_by(
        id=gateway_id,
        organization_id=user.organization_id
    ).first()
    
    if not gateway:
        return jsonify({"error": "Gateway not found"}), 404
    
    data = request.get_json() or {}
    firmware_id = data.get("firmware_id")
    force = data.get("force", False)
    
    if firmware_id:
        firmware = Firmware.query.get(firmware_id)
    else:
        firmware = Firmware.query.filter_by(
            device_type="gateway",
            is_active=True,
            is_stable=True
        ).order_by(Firmware.version_code.desc()).first()
    
    if not firmware:
        return jsonify({"error": "No firmware available for gateway"}), 404
    
    update = FirmwareUpdate(
        gateway_id=gateway.id,
        firmware_id=firmware.id,
        from_version=gateway.firmware_version,
        to_version=firmware.version,
        status="pending",
        triggered_by=user.id,
        trigger_type="manual"
    )
    db.session.add(update)
    db.session.commit()
    
    try:
        from app.mqtt_client import mqtt_client
        
        topic = f"awaxen/gateways/{gateway.serial_number or gateway.id}/ota"
        payload = {
            "command": "update",
            "firmware_url": firmware.file_url,
            "version": firmware.version,
            "version_code": firmware.version_code,
            "hash": firmware.file_hash,
            "size": firmware.file_size,
            "force": force,
            "update_id": str(update.id)
        }
        
        mqtt_client.publish(topic, payload)
        
        update.status = "downloading"
        update.started_at = utcnow()
        db.session.commit()
        
    except Exception as e:
        current_app.logger.error(f"MQTT publish error: {e}")
        update.status = "failed"
        update.error_message = str(e)
        db.session.commit()
        return jsonify({"error": f"Failed to send update command: {e}"}), 500
    
    return jsonify({
        "message": "Gateway firmware update initiated",
        "update": update.to_dict()
    })


# ==========================================
# Update Status
# ==========================================

@firmware_bp.route("/firmware-updates", methods=["GET", "OPTIONS"])
@requires_auth
@swag_from({
    "tags": ["Firmware"],
    "summary": "Firmware güncelleme geçmişini listele",
    "parameters": [
        {"name": "device_id", "in": "query", "type": "string"},
        {"name": "gateway_id", "in": "query", "type": "string"},
        {"name": "status", "in": "query", "type": "string"},
        {"name": "page", "in": "query", "type": "integer", "default": 1},
        {"name": "pageSize", "in": "query", "type": "integer", "default": 20}
    ],
    "responses": {
        200: {"description": "Güncelleme listesi"}
    }
})
def list_firmware_updates():
    """Firmware güncelleme geçmişini listele."""
    user = get_current_user()
    if not user or not user.organization_id:
        return jsonify({"error": "Unauthorized"}), 401
    
    page, page_size = get_pagination_params()
    device_id = request.args.get("device_id")
    gateway_id = request.args.get("gateway_id")
    status = request.args.get("status")
    
    # Organizasyona ait cihazların güncellemelerini getir
    query = FirmwareUpdate.query.join(
        SmartDevice, FirmwareUpdate.device_id == SmartDevice.id, isouter=True
    ).join(
        Gateway, FirmwareUpdate.gateway_id == Gateway.id, isouter=True
    ).filter(
        db.or_(
            SmartDevice.organization_id == user.organization_id,
            Gateway.organization_id == user.organization_id
        )
    )
    
    if device_id:
        query = query.filter(FirmwareUpdate.device_id == device_id)
    if gateway_id:
        query = query.filter(FirmwareUpdate.gateway_id == gateway_id)
    if status:
        query = query.filter(FirmwareUpdate.status == status)
    
    query = query.order_by(FirmwareUpdate.created_at.desc())
    
    total = query.count()
    updates = query.offset((page - 1) * page_size).limit(page_size).all()
    
    return jsonify(paginate_response([u.to_dict() for u in updates], total, page, page_size))


@firmware_bp.route("/firmware-updates/<uuid:update_id>/status", methods=["POST"])
def update_firmware_status(update_id):
    """
    Cihazdan gelen güncelleme durumu bildirimi.
    
    Bu endpoint cihazlar tarafından çağrılır (auth yok).
    """
    data = request.get_json()
    
    update = FirmwareUpdate.query.get(update_id)
    if not update:
        return jsonify({"error": "Update not found"}), 404
    
    new_status = data.get("status")
    progress = data.get("progress")
    error = data.get("error")
    
    if new_status:
        update.status = new_status
    if progress is not None:
        update.progress = progress
    if error:
        update.error_message = error
    
    if new_status == "completed":
        update.completed_at = utcnow()
        update.progress = 100
        
        # Cihaz firmware versiyonunu güncelle
        if update.device_id:
            device = SmartDevice.query.get(update.device_id)
            if device:
                device.firmware_version = update.to_version
        elif update.gateway_id:
            gateway = Gateway.query.get(update.gateway_id)
            if gateway:
                gateway.firmware_version = update.to_version
    
    db.session.commit()
    
    return jsonify({"message": "Status updated"})


# ==========================================
# Check for Updates
# ==========================================

@firmware_bp.route("/firmware/check", methods=["GET", "OPTIONS"])
def check_firmware_update():
    """
    Cihaz için mevcut güncelleme var mı kontrol et.
    
    Cihazlar tarafından çağrılır.
    """
    device_type = request.args.get("device_type", "esp32")
    current_version = request.args.get("current_version")
    current_version_code = request.args.get("current_version_code", type=int)
    hardware_version = request.args.get("hardware_version")
    
    query = Firmware.query.filter_by(
        device_type=device_type,
        is_active=True
    )
    
    if hardware_version:
        query = query.filter(
            db.or_(
                Firmware.hardware_version == hardware_version,
                Firmware.hardware_version.is_(None)
            )
        )
    
    # En son versiyon
    latest = query.order_by(Firmware.version_code.desc()).first()
    
    if not latest:
        return jsonify({"update_available": False})
    
    # Güncelleme gerekli mi?
    update_available = False
    if current_version_code:
        update_available = latest.version_code > current_version_code
    elif current_version:
        update_available = latest.version != current_version
    else:
        update_available = True
    
    if not update_available:
        return jsonify({"update_available": False, "current_version": latest.version})
    
    return jsonify({
        "update_available": True,
        "firmware": {
            "version": latest.version,
            "version_code": latest.version_code,
            "url": latest.file_url,
            "hash": latest.file_hash,
            "size": latest.file_size,
            "is_mandatory": latest.is_mandatory,
            "release_notes": latest.release_notes
        }
    })
