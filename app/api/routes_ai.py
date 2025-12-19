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

from app.auth import require_auth, get_current_user
from app.extensions import db
from app.models import AIAnalysisTask, AITaskStatus, SmartAsset
from app.services.storage_service import get_storage_service
from app.tasks.ai_tasks import process_ai_detection

logger = logging.getLogger(__name__)

ai_bp = Blueprint("ai", __name__)

# İzin verilen dosya uzantıları
ALLOWED_EXTENSIONS = {"png", "jpg", "jpeg", "webp", "tiff", "bmp"}
MAX_FILE_SIZE = 50 * 1024 * 1024  # 50MB


def _allowed_file(filename: str) -> bool:
    """Dosya uzantısı izinli mi?"""
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS


@ai_bp.route("/detect", methods=["POST"])
@require_auth
def create_detection_task():
    """
    Yeni AI detection task'ı oluştur.
    
    ---
    tags:
      - AI Detection
    consumes:
      - multipart/form-data
    parameters:
      - name: image
        in: formData
        type: file
        required: true
        description: Analiz edilecek görüntü (PNG, JPG, WEBP)
      - name: asset_id
        in: formData
        type: string
        required: false
        description: İlişkili asset UUID (opsiyonel)
      - name: enable_sahi
        in: formData
        type: boolean
        required: false
        description: SAHI (yüksek çözünürlük) modu aktif mi
      - name: confidence_threshold
        in: formData
        type: number
        required: false
        description: Güven eşiği (0.0-1.0, varsayılan 0.40)
    responses:
      202:
        description: Task oluşturuldu, işlem başladı
      400:
        description: Geçersiz istek
      413:
        description: Dosya çok büyük
    """
    user = get_current_user()
    
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
@require_auth
def get_task_status(task_id: str):
    """
    Task durumunu sorgula.
    
    ---
    tags:
      - AI Detection
    parameters:
      - name: task_id
        in: path
        type: string
        required: true
        description: Task UUID
    responses:
      200:
        description: Task durumu
      404:
        description: Task bulunamadı
    """
    user = get_current_user()
    
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
    
    # Tamamlandıysa presigned URL ekle
    if task.status == AITaskStatus.COMPLETED:
        try:
            storage = get_storage_service()
            result["image_url"] = storage.get_presigned_url(
                task.original_image_key,
                expires_in=3600,  # 1 saat
            )
        except Exception:
            pass
    
    return jsonify(result), 200


@ai_bp.route("/tasks", methods=["GET"])
@require_auth
def list_tasks():
    """
    Tüm AI task'larını listele.
    
    ---
    tags:
      - AI Detection
    parameters:
      - name: status
        in: query
        type: string
        required: false
        description: Durum filtresi (pending, processing, completed, failed)
      - name: asset_id
        in: query
        type: string
        required: false
        description: Asset UUID filtresi
      - name: limit
        in: query
        type: integer
        required: false
        description: Sayfa başına kayıt (varsayılan 20, max 100)
      - name: offset
        in: query
        type: integer
        required: false
        description: Başlangıç offset'i
    responses:
      200:
        description: Task listesi
    """
    user = get_current_user()
    
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
@require_auth
def delete_task(task_id: str):
    """
    Task'ı sil.
    
    ---
    tags:
      - AI Detection
    parameters:
      - name: task_id
        in: path
        type: string
        required: true
    responses:
      200:
        description: Task silindi
      404:
        description: Task bulunamadı
    """
    user = get_current_user()
    
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
@require_auth
def get_ai_stats():
    """
    AI analiz istatistikleri.
    
    ---
    tags:
      - AI Detection
    responses:
      200:
        description: İstatistikler
    """
    user = get_current_user()
    
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
