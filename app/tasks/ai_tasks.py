"""
Awaxen AI Tasks - Celery görevleri.

YOLO + SAM2 ile güneş paneli hata tespiti.
Async yapı: Kullanıcı beklemez, task_id ile sonucu sorgular.
"""
from __future__ import annotations

import io
import logging
import os
import time
from typing import Any, Dict, List, Optional
from uuid import UUID

from celery import shared_task

from app.extensions import db
from app.models import AIAnalysisTask, AIDetection, AITaskStatus, DefectType
from app.services.storage_service import get_storage_service

logger = logging.getLogger(__name__)

# AI Configuration
CONFIDENCE_THRESHOLD = float(os.getenv("AI_CONFIDENCE_THRESHOLD", "0.40"))
MODEL_PATH = os.getenv("AI_MODEL_PATH", "/app/models")
ENABLE_SAHI = os.getenv("ENABLE_SAHI", "true").lower() == "true"


def _load_yolo_model():
    """
    YOLO modelini lazy-load et.
    
    Öncelik sırası:
    1. ONNX modeli (production - hızlı, taşınabilir)
    2. PT modeli (fallback)
    3. Demo model (geliştirme)
    """
    try:
        from ultralytics import YOLO
        
        # ONNX modeli öncelikli (production best practice)
        onnx_model = os.path.join(MODEL_PATH, "yolo11_solar_v1.onnx")
        pt_model = os.path.join(MODEL_PATH, "yolo11_solar_v1.pt")
        
        model_file = None
        
        # 1. ONNX modeli kontrol et (öncelikli)
        if os.path.exists(onnx_model):
            model_file = onnx_model
            logger.info(f"[AI] ONNX model bulundu: {onnx_model}")
        # 2. PT modeli kontrol et
        elif os.path.exists(pt_model):
            model_file = pt_model
            logger.info(f"[AI] PT model bulundu: {pt_model}")
        # 3. Demo mod
        else:
            logger.warning(f"[AI] Model dosyası bulunamadı: {MODEL_PATH}")
            logger.info("[AI] Demo mod: yolov8n.pt kullanılıyor")
            model_file = "yolov8n.pt"
        
        model = YOLO(model_file)
        logger.info(f"[AI] Model yüklendi: {model_file}")
        return model, model_file
        
    except ImportError:
        logger.error("[AI] ultralytics kütüphanesi yüklü değil")
        return None, None
    except Exception as e:
        logger.error(f"[AI] Model yükleme hatası: {e}")
        return None, None


def _run_sahi_inference(model, image_path: str, confidence: float) -> List[Dict]:
    """
    SAHI ile yüksek çözünürlüklü görüntülerde inference.
    
    Görüntüyü parçalara böler, her parçada YOLO çalıştırır,
    sonuçları birleştirir. Küçük hataları yakalamak için ideal.
    """
    try:
        from sahi import AutoDetectionModel
        from sahi.predict import get_sliced_prediction
        
        # SAHI detection model wrapper
        detection_model = AutoDetectionModel.from_pretrained(
            model_type="yolov8",
            model_path=model.model_name if hasattr(model, 'model_name') else str(model),
            confidence_threshold=confidence,
            device="cpu",  # RPi uyumlu
        )
        
        # Sliced prediction
        result = get_sliced_prediction(
            image_path,
            detection_model,
            slice_height=640,
            slice_width=640,
            overlap_height_ratio=0.2,
            overlap_width_ratio=0.2,
        )
        
        detections = []
        for pred in result.object_prediction_list:
            detections.append({
                "class": pred.category.name,
                "confidence": pred.score.value,
                "bbox": [
                    pred.bbox.minx,
                    pred.bbox.miny,
                    pred.bbox.maxx - pred.bbox.minx,
                    pred.bbox.maxy - pred.bbox.miny,
                ],
                "segmentation": None,  # SAHI segmentation desteklemiyor
            })
        
        logger.info(f"[AI] SAHI inference tamamlandı: {len(detections)} tespit")
        return detections
        
    except ImportError:
        logger.warning("[AI] SAHI kütüphanesi yüklü değil, standart inference kullanılacak")
        return None
    except Exception as e:
        logger.warning(f"[AI] SAHI hatası: {e}, standart inference kullanılacak")
        return None


def _run_standard_inference(model, image_path: str, confidence: float) -> List[Dict]:
    """Standart YOLO inference."""
    results = model.predict(
        source=image_path,
        conf=confidence,
        verbose=False,
    )
    
    detections = []
    for result in results:
        boxes = result.boxes
        if boxes is None:
            continue
            
        for i, box in enumerate(boxes):
            cls_id = int(box.cls[0])
            cls_name = result.names.get(cls_id, "unknown")
            conf = float(box.conf[0])
            
            # xyxy -> xywh format
            xyxy = box.xyxy[0].tolist()
            bbox = [
                xyxy[0],  # x
                xyxy[1],  # y
                xyxy[2] - xyxy[0],  # width
                xyxy[3] - xyxy[1],  # height
            ]
            
            # Segmentation mask (varsa)
            segmentation = None
            if result.masks is not None and i < len(result.masks):
                mask = result.masks[i]
                if hasattr(mask, 'xy') and len(mask.xy) > 0:
                    segmentation = mask.xy[0].tolist()
            
            detections.append({
                "class": cls_name,
                "confidence": conf,
                "bbox": bbox,
                "segmentation": segmentation,
            })
    
    logger.info(f"[AI] Standart inference tamamlandı: {len(detections)} tespit")
    return detections


@shared_task(bind=True, queue="ai_tasks", max_retries=3, default_retry_delay=60)
def process_ai_detection(self, task_id: str) -> Dict[str, Any]:
    """
    AI detection task'ı işle.
    
    1. MinIO'dan resmi indir
    2. YOLO ile hata tespiti yap
    3. (Opsiyonel) SAM2 ile segmentation
    4. Sonuçları veritabanına kaydet
    
    Args:
        task_id: AIAnalysisTask UUID
    
    Returns:
        İşlem sonucu
    """
    from flask import current_app
    from app import create_app
    
    # Flask app context
    app = create_app()
    
    with app.app_context():
        start_time = time.time()
        
        # Task'ı bul
        task = AIAnalysisTask.query.get(task_id)
        if not task:
            logger.error(f"[AI] Task bulunamadı: {task_id}")
            return {"error": "Task not found"}
        
        try:
            # İşleme başla
            task.start_processing()
            db.session.commit()
            
            # MinIO'dan resmi indir
            storage = get_storage_service()
            image_data = storage.download_file(task.original_image_key)
            
            # Geçici dosyaya yaz (YOLO dosya path'i istiyor)
            import tempfile
            with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as tmp:
                tmp.write(image_data)
                tmp_path = tmp.name
            
            task.progress = 30
            db.session.commit()
            
            # Resim boyutlarını al
            try:
                from PIL import Image
                with Image.open(tmp_path) as img:
                    task.image_width, task.image_height = img.size
            except Exception:
                pass
            
            # YOLO modelini yükle
            model, model_file = _load_yolo_model()
            if model is None:
                raise Exception("YOLO model yüklenemedi")
            
            task.progress = 50
            db.session.commit()
            
            # Inference
            confidence = task.confidence_threshold or CONFIDENCE_THRESHOLD
            
            detections = None
            if task.sahi_enabled and ENABLE_SAHI:
                detections = _run_sahi_inference(model, tmp_path, confidence)
            
            if detections is None:
                detections = _run_standard_inference(model, tmp_path, confidence)
            
            task.progress = 80
            db.session.commit()
            
            # Geçici dosyayı sil
            try:
                os.unlink(tmp_path)
            except Exception:
                pass
            
            # Sonuçları kaydet - model versiyonunu dosya adından al
            model_version = os.path.basename(model_file).replace('.pt', '').replace('.onnx', '') if model_file else 'unknown'
            
            for det in detections:
                # Confidence threshold filtresi
                if det["confidence"] < confidence:
                    continue
                
                detection = AIDetection.from_yolo_result(
                    task_id=task.id,
                    defect_class=det["class"],
                    confidence=det["confidence"],
                    bbox=det["bbox"],
                    segmentation=det.get("segmentation"),
                )
                db.session.add(detection)
            
            # Task'ı tamamla
            processing_time = int((time.time() - start_time) * 1000)
            task.complete(model_version=model_version, processing_time_ms=processing_time)
            db.session.commit()
            
            logger.info(f"[AI] Task tamamlandı: {task_id}, {len(task.detections)} tespit, {processing_time}ms")
            
            return {
                "task_id": str(task_id),
                "status": "completed",
                "detection_count": len(task.detections),
                "processing_time_ms": processing_time,
            }
            
        except Exception as e:
            logger.exception(f"[AI] Task hatası: {task_id}")
            task.fail(str(e))
            db.session.commit()
            
            # Retry
            if self.request.retries < self.max_retries:
                raise self.retry(exc=e)
            
            return {
                "task_id": str(task_id),
                "status": "failed",
                "error": str(e),
            }


@shared_task(queue="ai_tasks")
def cleanup_old_ai_results(days: int = 30) -> Dict[str, int]:
    """
    Eski AI sonuçlarını temizle.
    
    Args:
        days: Kaç günden eski sonuçlar silinsin
    
    Returns:
        Silinen kayıt sayısı
    """
    from datetime import datetime, timedelta
    from app import create_app
    
    app = create_app()
    
    with app.app_context():
        cutoff = datetime.utcnow() - timedelta(days=days)
        
        # Eski task'ları bul
        old_tasks = AIAnalysisTask.query.filter(
            AIAnalysisTask.created_at < cutoff,
            AIAnalysisTask.status.in_([AITaskStatus.COMPLETED, AITaskStatus.FAILED]),
        ).all()
        
        deleted_count = 0
        storage = get_storage_service()
        
        for task in old_tasks:
            try:
                # MinIO'dan resmi sil
                if task.original_image_key:
                    storage.delete_file(task.original_image_key)
                
                # Veritabanından sil (cascade ile detection'lar da silinir)
                db.session.delete(task)
                deleted_count += 1
            except Exception as e:
                logger.warning(f"[AI] Cleanup hatası: {task.id} - {e}")
        
        db.session.commit()
        logger.info(f"[AI] Cleanup tamamlandı: {deleted_count} task silindi")
        
        return {"deleted_tasks": deleted_count}
