"""
Awaxen Models - AI Analysis.

Güneş paneli elektrolüminesans testi ve hata tespiti için modeller.
YOLO + SAM2 sonuçlarını saklar.
"""
from datetime import datetime
from typing import Any, Dict, List, Optional
from uuid import uuid4

from sqlalchemy import Column, String, Float, Integer, DateTime, ForeignKey, Text, Enum as SQLEnum
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import relationship
import enum

from app.extensions import db
from app.models.base import TimestampMixin, utcnow


class AITaskStatus(enum.Enum):
    """AI task durumları."""
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"


class DefectType(enum.Enum):
    """Güneş paneli hata tipleri."""
    CRACK = "crack"                    # Çatlak
    HOTSPOT = "hotspot"                # Sıcak nokta
    SNAIL_TRAIL = "snail_trail"        # Salyangoz izi
    CELL_DAMAGE = "cell_damage"        # Hücre hasarı
    DELAMINATION = "delamination"      # Delaminasyon
    DISCOLORATION = "discoloration"    # Renk değişimi
    BROKEN_CELL = "broken_cell"        # Kırık hücre
    PID = "pid"                        # Potential Induced Degradation
    SOILING = "soiling"                # Kirlilik
    SHADING = "shading"                # Gölgelenme
    UNKNOWN = "unknown"                # Bilinmeyen


class AIAnalysisTask(db.Model, TimestampMixin):
    """
    AI analiz görevi.
    
    Kullanıcı resim yüklediğinde bir task oluşturulur.
    Celery worker bu task'ı işler ve sonucu kaydeder.
    """
    __tablename__ = "ai_analysis_tasks"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    
    # İlişkiler
    organization_id = Column(UUID(as_uuid=True), ForeignKey("organizations.id"), nullable=False, index=True)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True, index=True)
    asset_id = Column(UUID(as_uuid=True), ForeignKey("smart_assets.id"), nullable=True, index=True)
    
    # Task durumu
    status = Column(SQLEnum(AITaskStatus), default=AITaskStatus.PENDING, nullable=False, index=True)
    progress = Column(Integer, default=0)  # 0-100
    error_message = Column(Text, nullable=True)
    
    # Görüntü bilgileri
    original_image_key = Column(String(512), nullable=False)  # MinIO object key
    original_filename = Column(String(255), nullable=True)
    image_width = Column(Integer, nullable=True)
    image_height = Column(Integer, nullable=True)
    
    # Model bilgileri
    model_version = Column(String(50), nullable=True)  # örn: "yolo11_solar_v1"
    sahi_enabled = Column(db.Boolean, default=False)
    confidence_threshold = Column(Float, default=0.40)
    
    # Zamanlama
    started_at = Column(DateTime(timezone=True), nullable=True)
    completed_at = Column(DateTime(timezone=True), nullable=True)
    processing_time_ms = Column(Integer, nullable=True)
    
    # İlişkiler
    organization = relationship("Organization", backref="ai_tasks")
    user = relationship("User", backref="ai_tasks")
    asset = relationship("SmartAsset", backref="ai_tasks")
    detections = relationship("AIDetection", back_populates="task", cascade="all, delete-orphan")

    def start_processing(self):
        """Task işlemeye başladığında çağrılır."""
        self.status = AITaskStatus.PROCESSING
        self.started_at = utcnow()
        self.progress = 10

    def complete(self, model_version: str, processing_time_ms: int):
        """Task başarıyla tamamlandığında çağrılır."""
        self.status = AITaskStatus.COMPLETED
        self.completed_at = utcnow()
        self.model_version = model_version
        self.processing_time_ms = processing_time_ms
        self.progress = 100

    def fail(self, error_message: str):
        """Task başarısız olduğunda çağrılır."""
        self.status = AITaskStatus.FAILED
        self.completed_at = utcnow()
        self.error_message = error_message
        self.progress = 0

    def to_dict(self, include_detections: bool = True) -> Dict[str, Any]:
        """Task'ı JSON-serializable dict'e çevir."""
        result = {
            "id": str(self.id),
            "status": self.status.value,
            "progress": self.progress,
            "error_message": self.error_message,
            "original_filename": self.original_filename,
            "image_width": self.image_width,
            "image_height": self.image_height,
            "model_version": self.model_version,
            "sahi_enabled": self.sahi_enabled,
            "confidence_threshold": self.confidence_threshold,
            "processing_time_ms": self.processing_time_ms,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
        }
        
        if include_detections and self.status == AITaskStatus.COMPLETED:
            result["detections"] = [d.to_dict() for d in self.detections]
            result["detection_count"] = len(self.detections)
            result["defect_summary"] = self._get_defect_summary()
        
        return result

    def _get_defect_summary(self) -> Dict[str, int]:
        """Hata tiplerinin özetini döndür."""
        summary = {}
        for detection in self.detections:
            defect_type = detection.defect_type.value
            summary[defect_type] = summary.get(defect_type, 0) + 1
        return summary


class AIDetection(db.Model, TimestampMixin):
    """
    Tek bir tespit sonucu.
    
    YOLO'dan gelen bounding box ve SAM2'den gelen segmentation mask.
    Profesyonel yaklaşım: Ham veriyi kaydet, frontend çizsin.
    """
    __tablename__ = "ai_detections"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    task_id = Column(UUID(as_uuid=True), ForeignKey("ai_analysis_tasks.id"), nullable=False, index=True)
    
    # Hata bilgileri
    defect_type = Column(SQLEnum(DefectType), nullable=False, index=True)
    confidence = Column(Float, nullable=False)  # 0.0 - 1.0
    
    # Bounding Box (YOLO) - [x, y, width, height] formatında
    bbox_x = Column(Float, nullable=False)
    bbox_y = Column(Float, nullable=False)
    bbox_width = Column(Float, nullable=False)
    bbox_height = Column(Float, nullable=False)
    
    # Segmentation Mask (SAM2) - Poligon noktaları [[x1,y1], [x2,y2], ...]
    segmentation_points = Column(JSONB, nullable=True)
    
    # Ek metadata
    area_pixels = Column(Integer, nullable=True)  # Hata alanı (piksel)
    severity_score = Column(Float, nullable=True)  # 0.0 - 1.0 (hesaplanmış ciddiyet)
    
    # İlişkiler
    task = relationship("AIAnalysisTask", back_populates="detections")

    def to_dict(self) -> Dict[str, Any]:
        """Detection'ı JSON-serializable dict'e çevir."""
        return {
            "id": str(self.id),
            "defect_type": self.defect_type.value,
            "confidence": round(self.confidence, 4),
            "bbox": {
                "x": self.bbox_x,
                "y": self.bbox_y,
                "width": self.bbox_width,
                "height": self.bbox_height,
            },
            "segmentation": self.segmentation_points,
            "area_pixels": self.area_pixels,
            "severity_score": round(self.severity_score, 4) if self.severity_score else None,
        }

    @classmethod
    def from_yolo_result(
        cls,
        task_id: str,
        defect_class: str,
        confidence: float,
        bbox: List[float],
        segmentation: Optional[List[List[float]]] = None,
    ) -> "AIDetection":
        """
        YOLO sonucundan AIDetection oluştur.
        
        Args:
            task_id: İlişkili task ID
            defect_class: Hata sınıfı adı
            confidence: Güven skoru
            bbox: [x, y, width, height]
            segmentation: [[x1,y1], [x2,y2], ...] poligon noktaları
        """
        # Defect type mapping
        defect_type_map = {
            "crack": DefectType.CRACK,
            "hotspot": DefectType.HOTSPOT,
            "snail_trail": DefectType.SNAIL_TRAIL,
            "cell_damage": DefectType.CELL_DAMAGE,
            "delamination": DefectType.DELAMINATION,
            "discoloration": DefectType.DISCOLORATION,
            "broken_cell": DefectType.BROKEN_CELL,
            "pid": DefectType.PID,
            "soiling": DefectType.SOILING,
            "shading": DefectType.SHADING,
        }
        
        defect_type = defect_type_map.get(defect_class.lower(), DefectType.UNKNOWN)
        
        # Alan hesapla
        area = int(bbox[2] * bbox[3]) if len(bbox) >= 4 else None
        
        return cls(
            task_id=task_id,
            defect_type=defect_type,
            confidence=confidence,
            bbox_x=bbox[0],
            bbox_y=bbox[1],
            bbox_width=bbox[2],
            bbox_height=bbox[3],
            segmentation_points=segmentation,
            area_pixels=area,
        )
