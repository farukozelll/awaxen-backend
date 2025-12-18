"""
Data Export API Endpoints - v6.0.

B2B müşteriler için veri ihracatı (CSV/Excel).
Ağır işlemler Celery task olarak çalışır.
"""
import os
from datetime import datetime, timezone, timedelta
from flask import Blueprint, jsonify, request, current_app
from flasgger import swag_from

from app.extensions import db
from app.auth import requires_auth
from app.api.helpers import get_current_user, get_pagination_params, paginate_response
from app.models import DataExport, SmartDevice

export_bp = Blueprint("export", __name__)


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


# ==========================================
# Export Requests
# ==========================================

@export_bp.route("/export", methods=["POST", "OPTIONS"])
@requires_auth
@swag_from({
    "tags": ["Data Export"],
    "summary": "Veri ihracatı talebi oluştur",
    "description": "Ağır işlem olduğu için arka planda çalışır. Tamamlandığında email ile bildirim gönderilir.",
    "parameters": [
        {
            "name": "body",
            "in": "body",
            "required": True,
            "schema": {
                "type": "object",
                "properties": {
                    "export_type": {
                        "type": "string",
                        "enum": ["telemetry", "devices", "automations", "invoices", "audit_logs"],
                        "example": "telemetry"
                    },
                    "format": {
                        "type": "string",
                        "enum": ["csv", "excel", "json"],
                        "default": "csv"
                    },
                    "filters": {
                        "type": "object",
                        "properties": {
                            "device_id": {"type": "string", "format": "uuid"},
                            "start_date": {"type": "string", "format": "date", "example": "2024-01-01"},
                            "end_date": {"type": "string", "format": "date", "example": "2024-12-31"},
                            "columns": {"type": "array", "items": {"type": "string"}}
                        }
                    },
                    "notify_email": {"type": "string", "format": "email"}
                },
                "required": ["export_type"]
            }
        }
    ],
    "responses": {
        202: {
            "description": "Export talebi alındı",
            "schema": {
                "type": "object",
                "properties": {
                    "message": {"type": "string"},
                    "export_id": {"type": "string"},
                    "status": {"type": "string"}
                }
            }
        },
        400: {"description": "Geçersiz istek"}
    }
})
def create_export():
    """Veri ihracatı talebi oluştur."""
    user = get_current_user()
    if not user or not user.organization_id:
        return jsonify({"error": "Unauthorized"}), 401
    
    data = request.get_json()
    export_type = data.get("export_type")
    format_type = data.get("format", "csv")
    filters = data.get("filters", {})
    notify_email = data.get("notify_email", user.email)
    
    # Validasyon
    valid_types = ["telemetry", "devices", "automations", "invoices", "audit_logs"]
    if export_type not in valid_types:
        return jsonify({"error": f"Invalid export_type. Valid: {', '.join(valid_types)}"}), 400
    
    valid_formats = ["csv", "excel", "json"]
    if format_type not in valid_formats:
        return jsonify({"error": f"Invalid format. Valid: {', '.join(valid_formats)}"}), 400
    
    # Telemetry için device_id kontrolü
    if export_type == "telemetry" and filters.get("device_id"):
        device = SmartDevice.query.filter_by(
            id=filters["device_id"],
            organization_id=user.organization_id
        ).first()
        if not device:
            return jsonify({"error": "Device not found"}), 404
    
    # Export kaydı oluştur
    export = DataExport(
        organization_id=user.organization_id,
        requested_by=user.id,
        export_type=export_type,
        format=format_type,
        filters=filters,
        status="pending",
        notify_email=notify_email,
        expires_at=utcnow() + timedelta(days=7)  # 7 gün sonra expire
    )
    db.session.add(export)
    db.session.commit()
    
    # Celery task'ı başlat
    try:
        from app.tasks.export_tasks import process_export
        task = process_export.delay(str(export.id))
        
        export.celery_task_id = task.id
        export.status = "processing"
        export.started_at = utcnow()
        db.session.commit()
        
    except Exception as e:
        current_app.logger.error(f"Failed to start export task: {e}")
        # Task başlatılamazsa bile export kaydı oluşturuldu
    
    return jsonify({
        "message": "Export request received. You will be notified when it's ready.",
        "export_id": str(export.id),
        "status": export.status,
        "notify_email": notify_email
    }), 202


@export_bp.route("/export", methods=["GET", "OPTIONS"])
@requires_auth
@swag_from({
    "tags": ["Data Export"],
    "summary": "Export taleplerini listele",
    "parameters": [
        {"name": "status", "in": "query", "type": "string", "enum": ["pending", "processing", "completed", "failed"]},
        {"name": "page", "in": "query", "type": "integer", "default": 1},
        {"name": "pageSize", "in": "query", "type": "integer", "default": 20}
    ],
    "responses": {
        200: {"description": "Export listesi"}
    }
})
def list_exports():
    """Export taleplerini listele."""
    user = get_current_user()
    if not user or not user.organization_id:
        return jsonify({"error": "Unauthorized"}), 401
    
    page, page_size = get_pagination_params()
    status = request.args.get("status")
    
    query = DataExport.query.filter_by(organization_id=user.organization_id)
    
    if status:
        query = query.filter_by(status=status)
    
    query = query.order_by(DataExport.created_at.desc())
    
    total = query.count()
    exports = query.offset((page - 1) * page_size).limit(page_size).all()
    
    return jsonify(paginate_response([e.to_dict() for e in exports], total, page, page_size))


@export_bp.route("/export/<uuid:export_id>", methods=["GET", "OPTIONS"])
@requires_auth
@swag_from({
    "tags": ["Data Export"],
    "summary": "Export detayını getir",
    "parameters": [
        {"name": "export_id", "in": "path", "type": "string", "required": True}
    ],
    "responses": {
        200: {"description": "Export detayı"},
        404: {"description": "Export bulunamadı"}
    }
})
def get_export(export_id):
    """Export detayını getir."""
    user = get_current_user()
    if not user or not user.organization_id:
        return jsonify({"error": "Unauthorized"}), 401
    
    export = DataExport.query.filter_by(
        id=export_id,
        organization_id=user.organization_id
    ).first()
    
    if not export:
        return jsonify({"error": "Export not found"}), 404
    
    return jsonify(export.to_dict())


@export_bp.route("/export/<uuid:export_id>/download", methods=["GET", "OPTIONS"])
@requires_auth
@swag_from({
    "tags": ["Data Export"],
    "summary": "Export dosyasını indir",
    "parameters": [
        {"name": "export_id", "in": "path", "type": "string", "required": True}
    ],
    "responses": {
        200: {"description": "Download URL"},
        400: {"description": "Export henüz hazır değil"},
        404: {"description": "Export bulunamadı"},
        410: {"description": "Download linki expire olmuş"}
    }
})
def download_export(export_id):
    """Export dosyasını indir."""
    user = get_current_user()
    if not user or not user.organization_id:
        return jsonify({"error": "Unauthorized"}), 401
    
    export = DataExport.query.filter_by(
        id=export_id,
        organization_id=user.organization_id
    ).first()
    
    if not export:
        return jsonify({"error": "Export not found"}), 404
    
    if export.status != "completed":
        return jsonify({
            "error": "Export not ready",
            "status": export.status,
            "progress": export.progress
        }), 400
    
    if export.expires_at and export.expires_at < utcnow():
        return jsonify({"error": "Download link expired"}), 410
    
    # Download sayacını artır
    export.download_count += 1
    db.session.commit()
    
    return jsonify({
        "download_url": export.file_url,
        "file_name": export.file_name,
        "file_size": export.file_size,
        "expires_at": export.expires_at.isoformat() if export.expires_at else None
    })


# ==========================================
# Quick Export (Küçük veri setleri için)
# ==========================================

@export_bp.route("/telemetry/export", methods=["GET", "OPTIONS"])
@requires_auth
@swag_from({
    "tags": ["Data Export"],
    "summary": "Telemetri verilerini hızlı export et",
    "description": "Küçük veri setleri için direkt response döner. Büyük veriler için POST /export kullanın.",
    "parameters": [
        {"name": "device_id", "in": "query", "type": "string", "required": True},
        {"name": "start_date", "in": "query", "type": "string", "format": "date"},
        {"name": "end_date", "in": "query", "type": "string", "format": "date"},
        {"name": "format", "in": "query", "type": "string", "enum": ["csv", "json"], "default": "csv"},
        {"name": "limit", "in": "query", "type": "integer", "default": 10000, "description": "Max 10000 kayıt"}
    ],
    "responses": {
        200: {"description": "Export verisi"},
        400: {"description": "Geçersiz istek"},
        413: {"description": "Veri seti çok büyük, async export kullanın"}
    }
})
def quick_telemetry_export():
    """Küçük telemetri veri setlerini hızlı export et."""
    user = get_current_user()
    if not user or not user.organization_id:
        return jsonify({"error": "Unauthorized"}), 401
    
    device_id = request.args.get("device_id")
    if not device_id:
        return jsonify({"error": "device_id is required"}), 400
    
    # Cihaz kontrolü
    device = SmartDevice.query.filter_by(
        id=device_id,
        organization_id=user.organization_id
    ).first()
    
    if not device:
        return jsonify({"error": "Device not found"}), 404
    
    from app.models import DeviceTelemetry
    from app.api.helpers import parse_iso_datetime
    
    start_date = parse_iso_datetime(request.args.get("start_date"))
    end_date = parse_iso_datetime(request.args.get("end_date"))
    format_type = request.args.get("format", "csv")
    limit = min(request.args.get("limit", 10000, type=int), 10000)
    
    # Varsayılan: son 7 gün
    if not start_date:
        start_date = utcnow() - timedelta(days=7)
    if not end_date:
        end_date = utcnow()
    
    # Kayıt sayısını kontrol et
    count = DeviceTelemetry.query.filter(
        DeviceTelemetry.device_id == device_id,
        DeviceTelemetry.time >= start_date,
        DeviceTelemetry.time <= end_date
    ).count()
    
    if count > 10000:
        return jsonify({
            "error": "Dataset too large for quick export",
            "row_count": count,
            "suggestion": "Use POST /api/export for large datasets"
        }), 413
    
    # Verileri çek
    records = DeviceTelemetry.query.filter(
        DeviceTelemetry.device_id == device_id,
        DeviceTelemetry.time >= start_date,
        DeviceTelemetry.time <= end_date
    ).order_by(DeviceTelemetry.time.asc()).limit(limit).all()
    
    if format_type == "json":
        return jsonify({
            "device_id": device_id,
            "device_name": device.name,
            "start_date": start_date.isoformat(),
            "end_date": end_date.isoformat(),
            "row_count": len(records),
            "data": [r.to_dict() for r in records]
        })
    
    # CSV format
    import io
    import csv
    from flask import Response
    
    output = io.StringIO()
    writer = csv.writer(output)
    
    # Header
    headers = ["time", "power_w", "voltage", "current", "energy_total_kwh", "temperature", "humidity"]
    writer.writerow(headers)
    
    # Data
    for r in records:
        writer.writerow([
            r.time.isoformat() if r.time else "",
            r.power_w or "",
            r.voltage or "",
            r.current or "",
            r.energy_total_kwh or "",
            r.temperature or "",
            r.humidity or ""
        ])
    
    output.seek(0)
    
    filename = f"telemetry_{device.name}_{start_date.strftime('%Y%m%d')}_{end_date.strftime('%Y%m%d')}.csv"
    
    return Response(
        output.getvalue(),
        mimetype="text/csv",
        headers={"Content-Disposition": f"attachment; filename={filename}"}
    )
