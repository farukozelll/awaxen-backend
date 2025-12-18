"""
Data Export Celery Tasks.

Ağır veri ihracatı işlemleri için arka plan görevleri.
"""
import os
import io
import csv
import json
import logging
from datetime import datetime, timezone, timedelta

from celery import shared_task

from app.extensions import db
from app.models import (
    DataExport, DeviceTelemetry, SmartDevice, SmartAsset,
    Automation, Invoice, AuditLog
)

logger = logging.getLogger(__name__)


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


@shared_task(bind=True, max_retries=3, default_retry_delay=60)
def process_export(self, export_id: str):
    """
    Export talebini işle.
    
    Args:
        export_id: DataExport kaydının UUID'si
    """
    from flask import current_app
    
    export = DataExport.query.get(export_id)
    if not export:
        logger.error(f"Export not found: {export_id}")
        return {"error": "Export not found"}
    
    try:
        export.status = "processing"
        export.started_at = utcnow()
        db.session.commit()
        
        # Export tipine göre işle
        if export.export_type == "telemetry":
            result = _export_telemetry(export)
        elif export.export_type == "devices":
            result = _export_devices(export)
        elif export.export_type == "automations":
            result = _export_automations(export)
        elif export.export_type == "invoices":
            result = _export_invoices(export)
        elif export.export_type == "audit_logs":
            result = _export_audit_logs(export)
        else:
            raise ValueError(f"Unknown export type: {export.export_type}")
        
        # Başarılı
        export.status = "completed"
        export.completed_at = utcnow()
        export.file_name = result["file_name"]
        export.file_size = result["file_size"]
        export.file_url = result["file_url"]
        export.total_rows = result["total_rows"]
        export.processed_rows = result["total_rows"]
        export.progress = 100
        db.session.commit()
        
        # Email bildirimi gönder
        if export.notify_email:
            _send_export_notification(export)
        
        logger.info(f"Export completed: {export_id}, rows: {result['total_rows']}")
        return {"status": "completed", "rows": result["total_rows"]}
        
    except Exception as e:
        logger.error(f"Export failed: {export_id}, error: {e}")
        export.status = "failed"
        export.error_message = str(e)
        db.session.commit()
        
        # Retry
        raise self.retry(exc=e)


def _export_telemetry(export: DataExport) -> dict:
    """Telemetri verilerini export et."""
    filters = export.filters or {}
    device_id = filters.get("device_id")
    start_date = _parse_date(filters.get("start_date"))
    end_date = _parse_date(filters.get("end_date"))
    columns = filters.get("columns")
    
    # Varsayılan tarih aralığı: son 30 gün
    if not start_date:
        start_date = utcnow() - timedelta(days=30)
    if not end_date:
        end_date = utcnow()
    
    # Query oluştur
    query = DeviceTelemetry.query.join(SmartDevice).filter(
        SmartDevice.organization_id == export.organization_id,
        DeviceTelemetry.time >= start_date,
        DeviceTelemetry.time <= end_date
    )
    
    if device_id:
        query = query.filter(DeviceTelemetry.device_id == device_id)
    
    query = query.order_by(DeviceTelemetry.time.asc())
    
    # Toplam kayıt sayısı
    total_rows = query.count()
    export.total_rows = total_rows
    db.session.commit()
    
    # Batch işleme
    batch_size = 5000
    all_columns = columns or ["time", "device_id", "power_w", "voltage", "current", "energy_total_kwh", "temperature", "humidity"]
    
    if export.format == "csv":
        return _write_csv(export, query, all_columns, batch_size, total_rows)
    elif export.format == "excel":
        return _write_excel(export, query, all_columns, batch_size, total_rows)
    else:
        return _write_json(export, query, batch_size, total_rows)


def _export_devices(export: DataExport) -> dict:
    """Cihaz listesini export et."""
    devices = SmartDevice.query.filter_by(
        organization_id=export.organization_id,
        is_active=True
    ).all()
    
    columns = ["id", "name", "type", "external_id", "is_online", "last_seen", "firmware_version", "created_at"]
    
    data = []
    for d in devices:
        data.append({
            "id": str(d.id),
            "name": d.name,
            "type": d.type,
            "external_id": d.external_id,
            "is_online": d.is_online,
            "last_seen": d.last_seen.isoformat() if d.last_seen else None,
            "firmware_version": d.firmware_version,
            "created_at": d.created_at.isoformat() if d.created_at else None
        })
    
    return _write_data(export, data, columns, "devices")


def _export_automations(export: DataExport) -> dict:
    """Otomasyon listesini export et."""
    automations = Automation.query.filter_by(
        organization_id=export.organization_id
    ).all()
    
    columns = ["id", "name", "is_active", "trigger_type", "action_type", "last_triggered", "created_at"]
    
    data = []
    for a in automations:
        data.append({
            "id": str(a.id),
            "name": a.name,
            "is_active": a.is_active,
            "trigger_type": a.trigger_type,
            "action_type": a.action_type,
            "last_triggered": a.last_triggered.isoformat() if a.last_triggered else None,
            "created_at": a.created_at.isoformat() if a.created_at else None
        })
    
    return _write_data(export, data, columns, "automations")


def _export_invoices(export: DataExport) -> dict:
    """Fatura listesini export et."""
    invoices = Invoice.query.filter_by(
        organization_id=export.organization_id
    ).order_by(Invoice.created_at.desc()).all()
    
    columns = ["invoice_number", "amount", "tax_amount", "total_amount", "currency", "status", "paid_at", "created_at"]
    
    data = []
    for i in invoices:
        data.append({
            "invoice_number": i.invoice_number,
            "amount": float(i.amount),
            "tax_amount": float(i.tax_amount) if i.tax_amount else 0,
            "total_amount": float(i.total_amount),
            "currency": i.currency,
            "status": i.status,
            "paid_at": i.paid_at.isoformat() if i.paid_at else None,
            "created_at": i.created_at.isoformat() if i.created_at else None
        })
    
    return _write_data(export, data, columns, "invoices")


def _export_audit_logs(export: DataExport) -> dict:
    """Audit log'ları export et."""
    filters = export.filters or {}
    start_date = _parse_date(filters.get("start_date"))
    end_date = _parse_date(filters.get("end_date"))
    
    if not start_date:
        start_date = utcnow() - timedelta(days=90)
    if not end_date:
        end_date = utcnow()
    
    logs = AuditLog.query.filter(
        AuditLog.organization_id == export.organization_id,
        AuditLog.created_at >= start_date,
        AuditLog.created_at <= end_date
    ).order_by(AuditLog.created_at.desc()).all()
    
    columns = ["action", "entity_type", "entity_id", "user_email", "ip_address", "created_at"]
    
    data = []
    for log in logs:
        data.append({
            "action": log.action,
            "entity_type": log.entity_type,
            "entity_id": str(log.entity_id) if log.entity_id else None,
            "user_email": log.user.email if log.user else None,
            "ip_address": log.ip_address,
            "created_at": log.created_at.isoformat() if log.created_at else None
        })
    
    return _write_data(export, data, columns, "audit_logs")


def _write_csv(export: DataExport, query, columns: list, batch_size: int, total_rows: int) -> dict:
    """CSV dosyası oluştur."""
    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=columns)
    writer.writeheader()
    
    processed = 0
    for offset in range(0, total_rows, batch_size):
        records = query.offset(offset).limit(batch_size).all()
        
        for r in records:
            row = {}
            for col in columns:
                val = getattr(r, col, None)
                if hasattr(val, 'isoformat'):
                    val = val.isoformat()
                elif hasattr(val, '__str__') and val is not None:
                    val = str(val)
                row[col] = val
            writer.writerow(row)
        
        processed += len(records)
        export.processed_rows = processed
        export.progress = int((processed / total_rows) * 100) if total_rows > 0 else 100
        db.session.commit()
    
    content = output.getvalue()
    return _save_file(export, content.encode('utf-8'), "csv")


def _write_excel(export: DataExport, query, columns: list, batch_size: int, total_rows: int) -> dict:
    """Excel dosyası oluştur."""
    try:
        import openpyxl
        from openpyxl import Workbook
    except ImportError:
        logger.warning("openpyxl not installed, falling back to CSV")
        return _write_csv(export, query, columns, batch_size, total_rows)
    
    wb = Workbook()
    ws = wb.active
    ws.title = export.export_type.capitalize()
    
    # Header
    ws.append(columns)
    
    processed = 0
    for offset in range(0, total_rows, batch_size):
        records = query.offset(offset).limit(batch_size).all()
        
        for r in records:
            row = []
            for col in columns:
                val = getattr(r, col, None)
                if hasattr(val, 'isoformat'):
                    val = val.isoformat()
                elif hasattr(val, '__str__') and val is not None:
                    val = str(val)
                row.append(val)
            ws.append(row)
        
        processed += len(records)
        export.processed_rows = processed
        export.progress = int((processed / total_rows) * 100) if total_rows > 0 else 100
        db.session.commit()
    
    output = io.BytesIO()
    wb.save(output)
    content = output.getvalue()
    
    return _save_file(export, content, "xlsx")


def _write_json(export: DataExport, query, batch_size: int, total_rows: int) -> dict:
    """JSON dosyası oluştur."""
    data = []
    
    processed = 0
    for offset in range(0, total_rows, batch_size):
        records = query.offset(offset).limit(batch_size).all()
        
        for r in records:
            data.append(r.to_dict())
        
        processed += len(records)
        export.processed_rows = processed
        export.progress = int((processed / total_rows) * 100) if total_rows > 0 else 100
        db.session.commit()
    
    content = json.dumps(data, indent=2, default=str).encode('utf-8')
    return _save_file(export, content, "json")


def _write_data(export: DataExport, data: list, columns: list, name: str) -> dict:
    """Genel veri yazma."""
    if export.format == "csv":
        output = io.StringIO()
        writer = csv.DictWriter(output, fieldnames=columns)
        writer.writeheader()
        for row in data:
            writer.writerow({k: row.get(k) for k in columns})
        content = output.getvalue().encode('utf-8')
        ext = "csv"
    elif export.format == "excel":
        try:
            from openpyxl import Workbook
            wb = Workbook()
            ws = wb.active
            ws.title = name.capitalize()
            ws.append(columns)
            for row in data:
                ws.append([row.get(k) for k in columns])
            output = io.BytesIO()
            wb.save(output)
            content = output.getvalue()
            ext = "xlsx"
        except ImportError:
            output = io.StringIO()
            writer = csv.DictWriter(output, fieldnames=columns)
            writer.writeheader()
            for row in data:
                writer.writerow({k: row.get(k) for k in columns})
            content = output.getvalue().encode('utf-8')
            ext = "csv"
    else:
        content = json.dumps(data, indent=2, default=str).encode('utf-8')
        ext = "json"
    
    return _save_file(export, content, ext, total_rows=len(data))


def _save_file(export: DataExport, content: bytes, ext: str, total_rows: int = None) -> dict:
    """Dosyayı kaydet ve URL döndür."""
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    file_name = f"{export.export_type}_{export.organization_id}_{timestamp}.{ext}"
    
    # Upload klasörü
    upload_folder = os.getenv("EXPORT_UPLOAD_FOLDER", "/app/uploads/exports")
    os.makedirs(upload_folder, exist_ok=True)
    
    file_path = os.path.join(upload_folder, file_name)
    
    with open(file_path, 'wb') as f:
        f.write(content)
    
    # URL oluştur
    base_url = os.getenv("EXPORT_BASE_URL", "http://localhost:5000")
    file_url = f"{base_url}/api/export/files/{file_name}"
    
    return {
        "file_name": file_name,
        "file_size": len(content),
        "file_url": file_url,
        "total_rows": total_rows or export.total_rows or 0
    }


def _parse_date(date_str: str) -> datetime:
    """Tarih string'ini parse et."""
    if not date_str:
        return None
    
    try:
        if 'T' in date_str:
            return datetime.fromisoformat(date_str.replace('Z', '+00:00'))
        return datetime.strptime(date_str, "%Y-%m-%d").replace(tzinfo=timezone.utc)
    except:
        return None


def _send_export_notification(export: DataExport):
    """Export tamamlandığında email bildirimi gönder."""
    try:
        from app.services.notification_service import send_email
        
        subject = f"Veri İhracatı Hazır - {export.export_type.capitalize()}"
        body = f"""
Merhaba,

Talep ettiğiniz veri ihracatı tamamlandı.

Detaylar:
- Tip: {export.export_type}
- Format: {export.format.upper()}
- Kayıt Sayısı: {export.total_rows}
- Dosya Boyutu: {export.file_size / 1024:.1f} KB

İndirme linki 7 gün geçerlidir.

İndirmek için: {export.file_url}

Awaxen Ekibi
        """
        
        send_email(export.notify_email, subject, body)
        
        export.notification_sent = True
        db.session.commit()
        
    except Exception as e:
        logger.error(f"Failed to send export notification: {e}")


@shared_task
def cleanup_expired_exports():
    """Süresi dolmuş export dosyalarını temizle."""
    expired = DataExport.query.filter(
        DataExport.expires_at < utcnow(),
        DataExport.status == "completed"
    ).all()
    
    upload_folder = os.getenv("EXPORT_UPLOAD_FOLDER", "/app/uploads/exports")
    
    for export in expired:
        # Dosyayı sil
        if export.file_name:
            file_path = os.path.join(upload_folder, export.file_name)
            if os.path.exists(file_path):
                os.remove(file_path)
        
        export.status = "expired"
        export.file_url = None
    
    db.session.commit()
    
    logger.info(f"Cleaned up {len(expired)} expired exports")
    return {"cleaned": len(expired)}
