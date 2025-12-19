"""
AI Detection API Routes - Güneş Paneli Hata Tespiti.

Async yapı:
1. POST /api/ai/detect - Resim yükle, task_id al
2. GET /api/ai/tasks/{task_id} - Sonucu sorgula (polling)
3. GET /api/ai/tasks - Tüm task'ları listele
"""
from __future__ import annotations

import logging
from typing import Optional
from uuid import UUID

from flask import Blueprint, request, jsonify, g
from werkzeug.utils import secure_filename
from flasgger import swag_from

from app.auth import requires_auth, get_db_user
from app.extensions import db
from app.models import AIAnalysisTask, AITaskStatus, SmartAsset
from app.services.storage_service import get_storage_service
from app.tasks.ai_tasks import process_ai_detection

logger = logging.getLogger(__name__)

ai_bp = Blueprint("ai", __name__)

# İzin verilen dosya uzantıları
ALLOWED_EXTENSIONS = {"png", "jpg", "jpeg", "webp", "tiff", "bmp"}
MAX_FILE_SIZE = 50 * 1024 * 1024  # 50MB

# Swagger Definitions
AI_SWAGGER_DEFINITIONS = {
    "AITask": {
        "type": "object",
        "properties": {
            "id": {"type": "string", "format": "uuid"},
            "status": {"type": "string", "enum": ["pending", "processing", "completed", "failed"]},
            "progress": {"type": "integer", "example": 75},
            "detection_count": {"type": "integer", "example": 3},
            "processing_time_ms": {"type": "integer", "example": 1250},
            "model_version": {"type": "string", "example": "yolo11_solar_v1"},
            "created_at": {"type": "string", "format": "date-time"},
            "completed_at": {"type": "string", "format": "date-time"},
        },
    },
    "AIDetection": {
        "type": "object",
        "properties": {
            "id": {"type": "string", "format": "uuid"},
            "defect_class": {"type": "string", "example": "hotspot"},
            "confidence": {"type": "number", "example": 0.92},
            "bbox": {
                "type": "object",
                "properties": {
                    "x": {"type": "number"},
                    "y": {"type": "number"},
                    "width": {"type": "number"},
                    "height": {"type": "number"},
                },
            },
            "severity": {"type": "string", "enum": ["low", "medium", "high", "critical"]},
        },
    },
    "AIStats": {
        "type": "object",
        "properties": {
            "total_tasks": {"type": "integer"},
            "completed_tasks": {"type": "integer"},
            "total_detections": {"type": "integer"},
            "avg_processing_time_ms": {"type": "number"},
            "defect_distribution": {"type": "object"},
        },
    },
}


def _allowed_file(filename: str) -> bool:
    """Dosya uzantısı izinli mi?"""
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS


@ai_bp.route("/detect", methods=["POST"])
@requires_auth
@swag_from({
    "tags": ["AI Vision"],
    "summary": "Güneş paneli hata tespiti başlat",
    "description": """
Yüklenen görüntüde YOLO + SAM2 modelleri ile güneş paneli hatalarını tespit eder.

**Desteklenen Hata Türleri:**
- `hotspot`: Sıcak nokta (termal anomali)
- `crack`: Çatlak
- `soiling`: Kirlilik/toz
- `shading`: Gölgelenme
- `delamination`: Delaminasyon
- `snail_trail`: Salyangoz izi

**İşlem Akışı:**
1. Resim MinIO'ya yüklenir
2. Celery task'ı başlatılır
3. Task ID döner, polling ile sonuç sorgulanır
    """,
    "consumes": ["multipart/form-data"],
    "parameters": [
        {
            "name": "image",
            "in": "formData",
            "type": "file",
            "required": True,
            "description": "Analiz edilecek görüntü (PNG, JPG, WEBP, max 50MB)",
        },
        {
            "name": "asset_id",
            "in": "formData",
            "type": "string",
            "required": False,
            "description": "İlişkili güneş paneli asset UUID",
        },
        {
            "name": "enable_sahi",
            "in": "formData",
            "type": "boolean",
            "required": False,
            "description": "SAHI modu (yüksek çözünürlüklü görüntüler için)",
        },
        {
            "name": "confidence_threshold",
            "in": "formData",
            "type": "number",
            "required": False,
            "description": "Güven eşiği (0.0-1.0, varsayılan: 0.40)",
        },
        {
            "name": "test_type",
            "in": "formData",
            "type": "string",
            "required": False,
            "enum": ["electroluminescence", "thermal", "visual", "infrared"],
            "description": "Test türü (EL, termal, görsel, kızılötesi)",
        },
        {
            "name": "notes",
            "in": "formData",
            "type": "string",
            "required": False,
            "description": "Kullanıcı notları",
        },
    ],
    "responses": {
        202: {
            "description": "Task oluşturuldu, işlem başladı",
            "schema": {
                "type": "object",
                "properties": {
                    "task_id": {"type": "string", "format": "uuid"},
                    "status": {"type": "string", "example": "pending"},
                    "message": {"type": "string"},
                    "poll_url": {"type": "string"},
                },
            },
        },
        400: {"description": "Geçersiz istek (dosya eksik veya format hatası)"},
        413: {"description": "Dosya boyutu çok büyük (max 50MB)"},
    },
    "definitions": AI_SWAGGER_DEFINITIONS,
})
def create_detection_task():
    user = get_db_user()
    
    # Dosya kontrolü
    if "image" not in request.files:
        return jsonify({"error": "Resim dosyası gerekli", "code": "NO_FILE"}), 400
    
    file = request.files["image"]
    
    if file.filename == "":
        return jsonify({"error": "Dosya seçilmedi", "code": "EMPTY_FILENAME"}), 400
    
    if not _allowed_file(file.filename):
        return jsonify({
            "error": f"Geçersiz dosya formatı. İzin verilenler: {', '.join(ALLOWED_EXTENSIONS)}",
            "code": "INVALID_FORMAT"
        }), 400
    
    # Dosya boyutu kontrolü
    file.seek(0, 2)  # EOF'a git
    file_size = file.tell()
    file.seek(0)  # Başa dön
    
    if file_size > MAX_FILE_SIZE:
        return jsonify({
            "error": f"Dosya çok büyük. Maksimum: {MAX_FILE_SIZE // (1024*1024)}MB",
            "code": "FILE_TOO_LARGE"
        }), 413
    
    # Opsiyonel parametreler
    asset_id = request.form.get("asset_id")
    enable_sahi = request.form.get("enable_sahi", "false").lower() == "true"
    test_type = request.form.get("test_type")  # electroluminescence, thermal, visual, infrared
    notes = request.form.get("notes")
    
    try:
        confidence = float(request.form.get("confidence_threshold", "0.40"))
        confidence = max(0.0, min(1.0, confidence))  # 0-1 arasında tut
    except ValueError:
        confidence = 0.40
    
    # Asset kontrolü (varsa)
    if asset_id:
        try:
            asset = SmartAsset.query.filter_by(
                id=UUID(asset_id),
                organization_id=user.organization_id
            ).first()
            if not asset:
                asset_id = None
        except Exception:
            asset_id = None
    
    try:
        # MinIO'ya yükle
        storage = get_storage_service()
        filename = secure_filename(file.filename)
        
        # Content type belirle
        ext = filename.rsplit(".", 1)[1].lower()
        content_types = {
            "jpg": "image/jpeg",
            "jpeg": "image/jpeg",
            "png": "image/png",
            "webp": "image/webp",
            "tiff": "image/tiff",
            "bmp": "image/bmp",
        }
        content_type = content_types.get(ext, "application/octet-stream")
        
        object_key = storage.upload_file(
            file_data=file,
            filename=filename,
            content_type=content_type,
            folder="ai-uploads",
        )
        
        # Task oluştur
        task = AIAnalysisTask(
            organization_id=user.organization_id,
            user_id=user.id,
            asset_id=UUID(asset_id) if asset_id else None,
            original_image_key=object_key,
            original_filename=filename,
            sahi_enabled=enable_sahi,
            confidence_threshold=confidence,
            image_format=ext,
            image_size_bytes=file_size,
            test_type=test_type,
            notes=notes,
        )
        db.session.add(task)
        db.session.commit()
        
        # Celery task'ı başlat
        process_ai_detection.delay(str(task.id))
        
        logger.info(f"[AI] Task oluşturuldu: {task.id} by user {user.id}")
        
        return jsonify({
            "message": "İşlem başladı",
            "task_id": str(task.id),
            "status": task.status.value,
            "poll_url": f"/api/ai/tasks/{task.id}",
        }), 202
        
    except Exception as e:
        logger.exception("[AI] Task oluşturma hatası")
        db.session.rollback()
        return jsonify({"error": "İşlem başlatılamadı", "details": str(e)}), 500


@ai_bp.route("/tasks/<task_id>", methods=["GET"])
@requires_auth
@swag_from({
    "tags": ["AI Vision"],
    "summary": "Task durumunu sorgula (polling)",
    "description": """
Task'ın işlenme durumunu sorgular. Frontend bu endpoint'i polling ile çağırmalıdır.

**Status Değerleri:**
- `pending`: Kuyrukta bekliyor
- `processing`: İşleniyor (progress: 0-100)
- `completed`: Tamamlandı, sonuçlar hazır
- `failed`: Hata oluştu
    """,
    "parameters": [
        {
            "name": "task_id",
            "in": "path",
            "type": "string",
            "required": True,
            "description": "Task UUID",
        },
    ],
    "responses": {
        200: {
            "description": "Task durumu ve sonuçları",
            "schema": {"$ref": "#/definitions/AITask"},
        },
        404: {"description": "Task bulunamadı"},
    },
    "definitions": AI_SWAGGER_DEFINITIONS,
})
def get_task_status(task_id: str):
    user = get_db_user()
    
    try:
        task = AIAnalysisTask.query.filter_by(
            id=UUID(task_id),
            organization_id=user.organization_id,
        ).first()
    except Exception:
        return jsonify({"error": "Geçersiz task ID"}), 400
    
    if not task:
        return jsonify({"error": "Task bulunamadı"}), 404
    
    result = task.to_dict(include_detections=True)
    
    # Tamamlandıysa presigned URL'ler ekle
    if task.status == AITaskStatus.COMPLETED:
        try:
            storage = get_storage_service()
            # Orijinal görsel URL
            result["image_url"] = storage.get_presigned_url(
                task.original_image_key,
                expires_in=3600,  # 1 saat
            )
            # Annotated (işaretli) görsel URL
            if task.annotated_image_key:
                result["annotated_image_url"] = storage.get_presigned_url(
                    task.annotated_image_key,
                    expires_in=3600,
                )
        except Exception:
            pass
    
    return jsonify(result), 200


@ai_bp.route("/tasks", methods=["GET"])
@requires_auth
@swag_from({
    "tags": ["AI Vision"],
    "summary": "AI task'larını listele",
    "description": "Organizasyona ait tüm AI analiz task'larını listeler.",
    "parameters": [
        {
            "name": "status",
            "in": "query",
            "type": "string",
            "enum": ["pending", "processing", "completed", "failed"],
            "required": False,
            "description": "Durum filtresi",
        },
        {
            "name": "asset_id",
            "in": "query",
            "type": "string",
            "required": False,
            "description": "Asset UUID filtresi",
        },
        {
            "name": "limit",
            "in": "query",
            "type": "integer",
            "default": 20,
            "description": "Sayfa başına kayıt (max 100)",
        },
        {
            "name": "offset",
            "in": "query",
            "type": "integer",
            "default": 0,
            "description": "Başlangıç offset'i",
        },
    ],
    "responses": {
        200: {
            "description": "Task listesi",
            "schema": {
                "type": "object",
                "properties": {
                    "tasks": {"type": "array", "items": {"$ref": "#/definitions/AITask"}},
                    "total": {"type": "integer"},
                    "limit": {"type": "integer"},
                    "offset": {"type": "integer"},
                },
            },
        },
    },
    "definitions": AI_SWAGGER_DEFINITIONS,
})
def list_tasks():
    user = get_db_user()
    
    # Query parametreleri
    status_filter = request.args.get("status")
    asset_id = request.args.get("asset_id")
    limit = min(int(request.args.get("limit", 20)), 100)
    offset = int(request.args.get("offset", 0))
    
    # Base query
    query = AIAnalysisTask.query.filter_by(organization_id=user.organization_id)
    
    # Filtreler
    if status_filter:
        try:
            status_enum = AITaskStatus(status_filter)
            query = query.filter_by(status=status_enum)
        except ValueError:
            pass
    
    if asset_id:
        try:
            query = query.filter_by(asset_id=UUID(asset_id))
        except Exception:
            pass
    
    # Sıralama ve pagination
    total = query.count()
    tasks = query.order_by(AIAnalysisTask.created_at.desc()).offset(offset).limit(limit).all()
    
    return jsonify({
        "tasks": [t.to_dict(include_detections=False) for t in tasks],
        "total": total,
        "limit": limit,
        "offset": offset,
    }), 200


@ai_bp.route("/tasks/<task_id>", methods=["DELETE"])
@requires_auth
@swag_from({
    "tags": ["AI Vision"],
    "summary": "AI task'ı sil",
    "description": "Task'ı ve ilişkili MinIO dosyalarını siler.",
    "parameters": [
        {
            "name": "task_id",
            "in": "path",
            "type": "string",
            "required": True,
            "description": "Silinecek task UUID",
        },
    ],
    "responses": {
        200: {"description": "Task başarıyla silindi"},
        404: {"description": "Task bulunamadı"},
    },
})
def delete_task(task_id: str):
    user = get_db_user()
    
    try:
        task = AIAnalysisTask.query.filter_by(
            id=UUID(task_id),
            organization_id=user.organization_id,
        ).first()
    except Exception:
        return jsonify({"error": "Geçersiz task ID"}), 400
    
    if not task:
        return jsonify({"error": "Task bulunamadı"}), 404
    
    try:
        # MinIO'dan resmi sil
        storage = get_storage_service()
        if task.original_image_key:
            storage.delete_file(task.original_image_key)
        
        # Veritabanından sil
        db.session.delete(task)
        db.session.commit()
        
        return jsonify({"message": "Task silindi"}), 200
        
    except Exception as e:
        logger.exception("[AI] Task silme hatası")
        db.session.rollback()
        return jsonify({"error": "Silme hatası", "details": str(e)}), 500


@ai_bp.route("/stats", methods=["GET"])
@requires_auth
@swag_from({
    "tags": ["AI Vision"],
    "summary": "AI analiz istatistikleri",
    "description": """
Organizasyona ait AI analiz istatistiklerini döner.

**İçerik:**
- Task sayıları (status bazında)
- Hata tipi dağılımı
- Ortalama işlem süresi
    """,
    "responses": {
        200: {
            "description": "İstatistikler",
            "schema": {"$ref": "#/definitions/AIStats"},
        },
    },
    "definitions": AI_SWAGGER_DEFINITIONS,
})
def get_ai_stats():
    user = get_db_user()
    
    from sqlalchemy import func
    from app.models import AIDetection, DefectType
    
    # Task sayıları
    task_counts = db.session.query(
        AIAnalysisTask.status,
        func.count(AIAnalysisTask.id)
    ).filter_by(
        organization_id=user.organization_id
    ).group_by(AIAnalysisTask.status).all()
    
    status_counts = {status.value: count for status, count in task_counts}
    
    # Hata tipi dağılımı
    defect_counts = db.session.query(
        AIDetection.defect_type,
        func.count(AIDetection.id)
    ).join(AIAnalysisTask).filter(
        AIAnalysisTask.organization_id == user.organization_id
    ).group_by(AIDetection.defect_type).all()
    
    defect_distribution = {dt.value: count for dt, count in defect_counts}
    
    # Ortalama işlem süresi
    avg_time = db.session.query(
        func.avg(AIAnalysisTask.processing_time_ms)
    ).filter(
        AIAnalysisTask.organization_id == user.organization_id,
        AIAnalysisTask.status == AITaskStatus.COMPLETED,
    ).scalar()
    
    return jsonify({
        "task_counts": status_counts,
        "total_tasks": sum(status_counts.values()),
        "defect_distribution": defect_distribution,
        "total_detections": sum(defect_distribution.values()),
        "avg_processing_time_ms": round(avg_time) if avg_time else None,
    }), 200
