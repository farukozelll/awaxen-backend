"""
Notifications API - Bildirim Yönetimi.

In-app, Telegram, Email, Push bildirimleri.
"""
from datetime import datetime
from flask import jsonify, request

from . import api_bp
from .helpers import get_current_user, get_pagination_params, paginate_response
from app.extensions import db
from app.models import Notification, NotificationStatus, UserSettings
from app.auth import requires_auth


@api_bp.route('/notifications', methods=['GET'])
@requires_auth
def get_notifications():
    """
    Kullanıcının bildirimlerini listele.
    ---
    tags:
      - Notifications
    security:
      - bearerAuth: []
    parameters:
      - name: page
        in: query
        type: integer
        default: 1
        description: Sayfa numarası
      - name: pageSize
        in: query
        type: integer
        default: 20
        description: Sayfa başına kayıt (max 100)
      - name: is_read
        in: query
        type: boolean
        description: Okunmuş/okunmamış filtresi
      - name: type
        in: query
        type: string
        enum: [info, warning, error, success, price_alert, device_alert, automation]
        description: Bildirim tipine göre filtrele
      - name: channel
        in: query
        type: string
        enum: [in_app, telegram, email, push]
        description: Kanala göre filtrele
    responses:
      200:
        description: Bildirim listesi
        schema:
          type: object
          properties:
            data:
              type: array
              items:
                $ref: '#/definitions/Notification'
            pagination:
              $ref: '#/definitions/Pagination'
            unread_count:
              type: integer
              description: Okunmamış bildirim sayısı
      401:
        description: Yetkisiz erişim
    definitions:
      Notification:
        type: object
        properties:
          id:
            type: string
            format: uuid
          title:
            type: string
          message:
            type: string
          type:
            type: string
            example: info
          channel:
            type: string
            example: in_app
          is_read:
            type: boolean
          created_at:
            type: string
            format: date-time
    """
    user = get_current_user()
    if not user:
        return jsonify({"error": "Unauthorized"}), 401
    
    page, page_size = get_pagination_params()
    is_read = request.args.get('is_read')
    notif_type = request.args.get('type')
    channel = request.args.get('channel')
    
    query = Notification.query.filter_by(user_id=user.id)
    
    if is_read is not None:
        query = query.filter_by(is_read=is_read.lower() == 'true')
    if notif_type:
        query = query.filter_by(type=notif_type)
    if channel:
        query = query.filter_by(channel=channel)
    
    query = query.order_by(Notification.created_at.desc())
    
    total = query.count()
    notifications = query.offset((page - 1) * page_size).limit(page_size).all()
    
    # Okunmamış sayısı
    unread_count = Notification.query.filter_by(
        user_id=user.id,
        is_read=False
    ).count()
    
    result = paginate_response(
        [n.to_dict() for n in notifications],
        total, page, page_size
    )
    result["unread_count"] = unread_count
    
    return jsonify(result)


@api_bp.route('/notifications/<uuid:notification_id>', methods=['GET'])
@requires_auth
def get_notification(notification_id):
    """
    Tek bir bildirimi getir.
    ---
    tags:
      - Notifications
    security:
      - bearerAuth: []
    parameters:
      - name: notification_id
        in: path
        type: string
        format: uuid
        required: true
        description: Bildirim UUID
    responses:
      200:
        description: Bildirim detayı
        schema:
          $ref: '#/definitions/Notification'
      401:
        description: Yetkisiz erişim
      404:
        description: Bildirim bulunamadı
    """
    user = get_current_user()
    if not user:
        return jsonify({"error": "Unauthorized"}), 401
    
    notification = Notification.query.filter_by(
        id=notification_id,
        user_id=user.id
    ).first()
    
    if not notification:
        return jsonify({"error": "Notification not found"}), 404
    
    return jsonify(notification.to_dict())


@api_bp.route('/notifications/<uuid:notification_id>/read', methods=['POST'])
@requires_auth
def mark_as_read(notification_id):
    """
    Bildirimi okundu olarak işaretle.
    ---
    tags:
      - Notifications
    security:
      - bearerAuth: []
    parameters:
      - name: notification_id
        in: path
        type: string
        format: uuid
        required: true
        description: Bildirim UUID
    responses:
      200:
        description: Bildirim okundu olarak işaretlendi
        schema:
          type: object
          properties:
            message:
              type: string
            notification:
              $ref: '#/definitions/Notification'
      401:
        description: Yetkisiz erişim
      404:
        description: Bildirim bulunamadı
    """
    user = get_current_user()
    if not user:
        return jsonify({"error": "Unauthorized"}), 401
    
    notification = Notification.query.filter_by(
        id=notification_id,
        user_id=user.id
    ).first()
    
    if not notification:
        return jsonify({"error": "Notification not found"}), 404
    
    notification.is_read = True
    notification.read_at = datetime.utcnow()
    notification.status = NotificationStatus.READ.value
    db.session.commit()
    
    return jsonify({
        "message": "Notification marked as read",
        "notification": notification.to_dict()
    })


@api_bp.route('/notifications/read-all', methods=['POST'])
@requires_auth
def mark_all_as_read():
    """
    Tüm bildirimleri okundu olarak işaretle.
    ---
    tags:
      - Notifications
    security:
      - bearerAuth: []
    responses:
      200:
        description: Tüm bildirimler okundu olarak işaretlendi
        schema:
          type: object
          properties:
            message:
              type: string
            updated_count:
              type: integer
      401:
        description: Yetkisiz erişim
    """
    user = get_current_user()
    if not user:
        return jsonify({"error": "Unauthorized"}), 401
    
    now = datetime.utcnow()
    
    updated = Notification.query.filter_by(
        user_id=user.id,
        is_read=False
    ).update({
        "is_read": True,
        "read_at": now,
        "status": NotificationStatus.READ.value
    })
    
    db.session.commit()
    
    return jsonify({
        "message": "All notifications marked as read",
        "updated_count": updated
    })


@api_bp.route('/notifications/<uuid:notification_id>', methods=['DELETE'])
@requires_auth
def delete_notification(notification_id):
    """
    Bildirimi sil.
    ---
    tags:
      - Notifications
    security:
      - bearerAuth: []
    parameters:
      - name: notification_id
        in: path
        type: string
        format: uuid
        required: true
        description: Bildirim UUID
    responses:
      200:
        description: Bildirim silindi
        schema:
          type: object
          properties:
            message:
              type: string
      401:
        description: Yetkisiz erişim
      404:
        description: Bildirim bulunamadı
    """
    user = get_current_user()
    if not user:
        return jsonify({"error": "Unauthorized"}), 401
    
    notification = Notification.query.filter_by(
        id=notification_id,
        user_id=user.id
    ).first()
    
    if not notification:
        return jsonify({"error": "Notification not found"}), 404
    
    db.session.delete(notification)
    db.session.commit()
    
    return jsonify({"message": "Notification deleted"})


@api_bp.route('/notifications', methods=['POST'])
@requires_auth
def create_notification():
    """
    Yeni bildirim oluştur (Admin/System).
    ---
    tags:
      - Notifications
    security:
      - bearerAuth: []
    consumes:
      - application/json
    parameters:
      - name: body
        in: body
        required: true
        schema:
          type: object
          required:
            - message
          properties:
            user_id:
              type: string
              format: uuid
              description: Hedef kullanıcı (admin için). Belirtilmezse kendisi.
            title:
              type: string
              example: Fiyat Uyarısı
            message:
              type: string
              example: Elektrik fiyatı 2 TL/kWh altına düştü!
            type:
              type: string
              enum: [info, warning, error, success, price_alert, device_alert, automation]
              default: info
            channel:
              type: string
              enum: [in_app, telegram, email, push]
              default: in_app
            reference_id:
              type: string
              description: İlişkili kayıt ID
            reference_type:
              type: string
              enum: [device, automation, market, system]
            data:
              type: object
              description: Ek veri
    responses:
      201:
        description: Bildirim oluşturuldu
        schema:
          type: object
          properties:
            message:
              type: string
            notification:
              $ref: '#/definitions/Notification'
      400:
        description: Geçersiz veri
      401:
        description: Yetkisiz erişim
    """
    user = get_current_user()
    if not user:
        return jsonify({"error": "Unauthorized"}), 401
    
    data = request.get_json() or {}
    
    message = data.get("message")
    if not message:
        return jsonify({"error": "Message is required"}), 400
    
    # Hedef kullanıcı
    target_user_id = data.get("user_id") or user.id
    
    # Admin kontrolü
    user_role_code = user.role.code if user.role else None
    if str(target_user_id) != str(user.id) and user_role_code not in ["admin", "super_admin"]:
        return jsonify({"error": "Forbidden"}), 403
    
    notification = Notification(
        user_id=target_user_id,
        organization_id=user.organization_id,
        title=data.get("title"),
        message=message,
        type=data.get("type", "info"),
        channel=data.get("channel", "in_app"),
        reference_id=data.get("reference_id"),
        reference_type=data.get("reference_type"),
        data=data.get("data", {}),
        status=NotificationStatus.SENT.value if data.get("channel") == "in_app" else NotificationStatus.PENDING.value,
    )
    
    db.session.add(notification)
    db.session.commit()
    
    # Telegram/Email için async gönderim tetikle
    channel = data.get("channel", "in_app")
    if channel != "in_app":
        _send_notification_async(notification)
    
    return jsonify({
        "message": "Notification created",
        "notification": notification.to_dict()
    }), 201


@api_bp.route('/notifications/unread-count', methods=['GET'])
@requires_auth
def get_unread_count():
    """
    Okunmamış bildirim sayısını getir.
    ---
    tags:
      - Notifications
    security:
      - bearerAuth: []
    responses:
      200:
        description: Okunmamış bildirim sayısı
        schema:
          type: object
          properties:
            unread_count:
              type: integer
              example: 5
      401:
        description: Yetkisiz erişim
    """
    user = get_current_user()
    if not user:
        return jsonify({"error": "Unauthorized"}), 401
    
    count = Notification.query.filter_by(
        user_id=user.id,
        is_read=False
    ).count()
    
    return jsonify({"unread_count": count})


@api_bp.route('/notifications/settings', methods=['GET'])
@requires_auth
def get_notification_settings():
    """
    Bildirim ayarlarını getir.
    ---
    tags:
      - Notifications
    security:
      - bearerAuth: []
    responses:
      200:
        description: Bildirim ayarları
        schema:
          type: object
          properties:
            telegram_enabled:
              type: boolean
            email_enabled:
              type: boolean
            push_enabled:
              type: boolean
            price_alerts:
              type: boolean
            device_alerts:
              type: boolean
            automation_alerts:
              type: boolean
            security_alerts:
              type: boolean
            weekly_report:
              type: boolean
            language:
              type: string
            theme:
              type: string
            price_alert_threshold_low:
              type: number
            price_alert_threshold_high:
              type: number
      401:
        description: Yetkisiz erişim
    """
    user = get_current_user()
    if not user:
        return jsonify({"error": "Unauthorized"}), 401
    
    # Veritabanından ayarları getir veya varsayılan oluştur
    settings = UserSettings.get_or_create(user.id)
    
    # Telegram durumunu user tablosundan kontrol et
    response = settings.to_dict()
    response["telegram_enabled"] = settings.telegram_enabled and bool(user.telegram_chat_id)
    response["telegram_connected"] = bool(user.telegram_chat_id)
    
    return jsonify(response)


@api_bp.route('/notifications/settings', methods=['PUT', 'PATCH'])
@requires_auth
def update_notification_settings():
    """
    Bildirim ayarlarını güncelle.
    ---
    tags:
      - Notifications
    security:
      - bearerAuth: []
    consumes:
      - application/json
    parameters:
      - name: body
        in: body
        required: true
        schema:
          type: object
          properties:
            telegram_enabled:
              type: boolean
            email_enabled:
              type: boolean
            push_enabled:
              type: boolean
            price_alerts:
              type: boolean
            device_alerts:
              type: boolean
            automation_alerts:
              type: boolean
            security_alerts:
              type: boolean
            weekly_report:
              type: boolean
            language:
              type: string
            theme:
              type: string
            price_alert_threshold_low:
              type: number
            price_alert_threshold_high:
              type: number
    responses:
      200:
        description: Ayarlar güncellendi
      400:
        description: Geçersiz veri
      401:
        description: Yetkisiz erişim
    """
    user = get_current_user()
    if not user:
        return jsonify({"error": "Unauthorized"}), 401
    
    data = request.get_json() or {}
    
    # Ayarları getir veya oluştur
    settings = UserSettings.get_or_create(user.id)
    
    # İzin verilen alanları güncelle
    allowed_fields = [
        'telegram_enabled', 'email_enabled', 'push_enabled',
        'price_alerts', 'device_alerts', 'automation_alerts',
        'security_alerts', 'weekly_report',
        'language', 'theme',
        'price_alert_threshold_low', 'price_alert_threshold_high'
    ]
    
    for field in allowed_fields:
        if field in data:
            setattr(settings, field, data[field])
    
    db.session.commit()
    
    return jsonify({
        "message": "Ayarlar güncellendi",
        "settings": settings.to_dict()
    })


# ==========================================
# HELPER FUNCTIONS
# ==========================================

def _send_notification_async(notification: Notification):
    """
    Bildirimi async olarak gönder (Celery task).
    """
    try:
        from app.tasks.notification_tasks import send_notification_task
        send_notification_task.delay(str(notification.id))
    except ImportError:
        # Celery yoksa sync gönder
        pass
