"""
Awaxen Models - Data Export.

B2B müşteriler için veri ihracatı (CSV/Excel).
"""
from datetime import datetime, timezone
from typing import Optional
import uuid

from sqlalchemy.dialects.postgresql import JSONB, UUID

from app.extensions import db
from app.models.base import TimestampMixin


def utcnow() -> datetime:
    """Timezone-aware UTC datetime döndür."""
    return datetime.now(timezone.utc)


class DataExport(db.Model):
    """
    Veri ihracatı talebi.
    
    Ağır işlemler için Celery task olarak çalışır,
    tamamlandığında email ile bildirim gönderilir.
    """
    __tablename__ = "data_exports"

    id = db.Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    organization_id = db.Column(UUID(as_uuid=True), db.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True)
    requested_by = db.Column(UUID(as_uuid=True), db.ForeignKey("users.id", ondelete="SET NULL"), nullable=False)
    
    # Export tipi
    export_type = db.Column(db.String(50), nullable=False, index=True)
    # telemetry, devices, automations, invoices, audit_logs
    
    # Format
    format = db.Column(db.String(10), default="csv")  # csv, excel, json
    
    # Filtreler
    filters = db.Column(JSONB, default=dict)
    # {
    #   "device_id": "uuid",
    #   "start_date": "2024-01-01",
    #   "end_date": "2024-12-31",
    #   "columns": ["time", "power_w", "voltage"]
    # }
    
    # Durum
    status = db.Column(db.String(20), default="pending", index=True)
    # pending, processing, completed, failed, expired
    
    progress = db.Column(db.Integer, default=0)  # 0-100
    total_rows = db.Column(db.Integer)
    processed_rows = db.Column(db.Integer, default=0)
    
    # Sonuç
    file_name = db.Column(db.String(255))
    file_size = db.Column(db.Integer)  # bytes
    file_url = db.Column(db.String(500))  # S3/MinIO URL
    download_count = db.Column(db.Integer, default=0)
    
    # Hata
    error_message = db.Column(db.Text)
    
    # Zamanlar
    started_at = db.Column(db.DateTime(timezone=True))
    completed_at = db.Column(db.DateTime(timezone=True))
    expires_at = db.Column(db.DateTime(timezone=True))  # Download linki ne zaman expire olacak
    
    # Celery task ID
    celery_task_id = db.Column(db.String(255))
    
    # Bildirim
    notify_email = db.Column(db.String(255))  # Tamamlandığında email gönder
    notification_sent = db.Column(db.Boolean, default=False)
    
    created_at = db.Column(db.DateTime(timezone=True), default=utcnow)
    updated_at = db.Column(db.DateTime(timezone=True), default=utcnow, onupdate=utcnow)

    # İlişkiler
    organization = db.relationship("Organization", backref=db.backref("data_exports", lazy="dynamic"))
    requester = db.relationship("User", backref="data_exports")

    __table_args__ = (
        db.Index('idx_export_org_status', 'organization_id', 'status'),
        db.Index('idx_export_created', 'created_at'),
    )

    def to_dict(self) -> dict:
        return {
            "id": str(self.id),
            "organization_id": str(self.organization_id),
            "export_type": self.export_type,
            "format": self.format,
            "filters": self.filters or {},
            "status": self.status,
            "progress": self.progress,
            "total_rows": self.total_rows,
            "processed_rows": self.processed_rows,
            "file_name": self.file_name,
            "file_size": self.file_size,
            "file_url": self.file_url if self.status == "completed" else None,
            "download_count": self.download_count,
            "error_message": self.error_message,
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "expires_at": self.expires_at.isoformat() if self.expires_at else None,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }
