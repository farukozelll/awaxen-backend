"""
Integration Routes - Bulut Entegrasyonları (Shelly, Tesla, Tapo).

OAuth bağlantıları ve cihaz senkronizasyonu.
"""
from flask import Blueprint, request, jsonify
from flasgger import swag_from

from app.extensions import db
from app.models import Integration, SmartDevice
from app.api.helpers import (
    get_current_user,
    get_pagination_params,
    paginate_response,
)
from app.services.shelly_service import ShellyService
from app.auth import requires_auth

integrations_bp = Blueprint("integrations", __name__)


@integrations_bp.route("/integrations", methods=["GET"])
@requires_auth
@swag_from({
    "tags": ["Integrations"],
    "summary": "Organizasyonun entegrasyonlarını listele",
    "parameters": [
        {
            "name": "page",
            "in": "query",
            "type": "integer",
            "default": 1,
            "description": "Sayfa numarası"
        },
        {
            "name": "pageSize",
            "in": "query",
            "type": "integer",
            "default": 20,
            "description": "Sayfa başına kayıt (max 100)"
        },
        {
            "name": "provider",
            "in": "query",
            "type": "string",
            "description": "Sağlayıcıya göre filtrele (shelly, tapo, tesla)"
        },
        {
            "name": "status",
            "in": "query",
            "type": "string",
            "description": "Duruma göre filtrele (active, paused)"
        },
    ],
    "responses": {
        200: {
            "description": "Paginated entegrasyon listesi",
            "schema": {
                "type": "object",
                "properties": {
                    "data": {
                        "type": "array",
                        "items": {"$ref": "#/definitions/Integration"}
                    },
                    "pagination": {"$ref": "#/definitions/Pagination"}
                }
            }
        },
        401: {"description": "Yetkisiz erişim"}
    }
})
def list_integrations():
    """Aktif entegrasyonları listele."""
    user = get_current_user()
    if not user or not user.organization_id:
        return jsonify({"error": "Unauthorized"}), 401
    
    page, page_size = get_pagination_params()
    provider = request.args.get("provider")
    status = request.args.get("status")
    
    query = Integration.query.filter_by(
        organization_id=user.organization_id,
        is_active=True
    )
    
    if provider:
        query = query.filter(Integration.provider.ilike(f"%{provider}%"))
    if status:
        query = query.filter(Integration.status == status)
    
    query = query.order_by(Integration.created_at.desc())
    total = query.count()
    items = query.offset((page - 1) * page_size).limit(page_size).all()
    
    return jsonify(paginate_response([i.to_dict() for i in items], total, page, page_size))


@integrations_bp.route("/integrations/<uuid:integration_id>", methods=["GET"])
@requires_auth
@swag_from({
    "tags": ["Integrations"],
    "summary": "Entegrasyon detayı",
    "parameters": [
        {"name": "integration_id", "in": "path", "type": "string", "required": True}
    ],
    "responses": {
        200: {"description": "Entegrasyon bilgileri"},
        401: {"description": "Yetkisiz erişim"},
        403: {"description": "Yetki yok"},
        404: {"description": "Entegrasyon bulunamadı"}
    }
})
def get_integration(integration_id):
    """Tek bir entegrasyonun detaylarını getir."""
    user = get_current_user()
    if not user:
        return jsonify({"error": "Unauthorized"}), 401
    
    integration = Integration.query.get_or_404(integration_id)
    
    if integration.organization_id != user.organization_id:
        return jsonify({"error": "Forbidden"}), 403
    
    if integration.provider == "shelly" and not (integration.provider_data or {}).get("server_uri"):
        return jsonify({"error": "Shelly entegrasyonu için server_uri kaydı bulunamadı"}), 400
    
    return jsonify(integration.to_dict(include_tokens=True))


@integrations_bp.route("/integrations", methods=["POST"])
@requires_auth
@swag_from({
    "tags": ["Integrations"],
    "summary": "Yeni entegrasyon ekle",
    "consumes": ["application/json"],
    "parameters": [
        {
            "name": "body",
            "in": "body",
            "schema": {
                "type": "object",
                "properties": {
                    "provider": {"type": "string", "example": "shelly"},
                    "access_token": {"type": "string"},
                    "refresh_token": {"type": "string"},
                    "provider_data": {"type": "object"},
                    "expires_at": {"type": "string", "format": "date-time"}
                },
                "required": ["provider", "access_token"]
            }
        }
    ],
    "responses": {
        201: {"description": "Entegrasyon oluşturuldu"},
        400: {"description": "Geçersiz istek"},
        401: {"description": "Yetkisiz erişim"}
    }
})
def create_integration():
    """
    Yeni bulut entegrasyonu ekle.
    
    Shelly için: access_token = auth_key
    Tesla için: OAuth flow sonrası token
    """
    user = get_current_user()
    if not user or not user.organization_id:
        return jsonify({"error": "Unauthorized"}), 401
    
    data = request.get_json()
    
    provider = data.get("provider")
    if not provider:
        return jsonify({"error": "Provider is required"}), 400
    
    provider_data = data.get("provider_data", {})
    if provider == "shelly":
        server_uri = (provider_data or {}).get("server_uri")
        if not server_uri:
            return jsonify({"error": "Shelly entegrasyonları için server_uri alanı zorunludur"}), 400
    
    # Aynı provider için mevcut entegrasyon var mı?
    existing = Integration.query.filter_by(
        organization_id=user.organization_id,
        provider=provider,
        is_active=True
    ).first()
    
    if existing:
        return jsonify({"error": f"Integration for {provider} already exists"}), 400
    
    integration = Integration(
        organization_id=user.organization_id,
        provider=provider,
        provider_data=provider_data,
    )
    
    # Token'ları şifreli kaydet
    integration.access_token = data.get("access_token")
    integration.refresh_token = data.get("refresh_token")
    
    if data.get("expires_at"):
        from datetime import datetime
        integration.expires_at = datetime.fromisoformat(data["expires_at"])
    
    db.session.add(integration)
    db.session.commit()
    
    return jsonify(integration.to_dict()), 201


@integrations_bp.route("/integrations/<uuid:integration_id>", methods=["PUT"])
@requires_auth
@swag_from({
    "tags": ["Integrations"],
    "summary": "Entegrasyonu güncelle",
    "parameters": [
        {"name": "integration_id", "in": "path", "type": "string", "required": True},
        {
            "name": "body",
            "in": "body",
            "schema": {
                "type": "object",
                "properties": {
                    "access_token": {"type": "string"},
                    "refresh_token": {"type": "string"},
                    "provider_data": {"type": "object"},
                    "status": {"type": "string"}
                }
            }
        }
    ],
    "responses": {
        200: {"description": "Entegrasyon güncellendi"},
        401: {"description": "Yetkisiz erişim"},
        403: {"description": "Yetki yok"},
        404: {"description": "Entegrasyon bulunamadı"}
    }
})
def update_integration(integration_id):
    """Entegrasyon token'larını güncelle."""
    user = get_current_user()
    if not user:
        return jsonify({"error": "Unauthorized"}), 401
    
    integration = Integration.query.get_or_404(integration_id)
    
    if integration.organization_id != user.organization_id:
        return jsonify({"error": "Forbidden"}), 403
    
    data = request.get_json()
    
    if "access_token" in data:
        integration.access_token = data["access_token"]
    if "refresh_token" in data:
        integration.refresh_token = data["refresh_token"]
    if "provider_data" in data:
        integration.provider_data = data["provider_data"]
    if "status" in data:
        integration.status = data["status"]
    
    db.session.commit()
    
    return jsonify(integration.to_dict(include_tokens=True))


@integrations_bp.route("/integrations/<uuid:integration_id>", methods=["DELETE"])
@requires_auth
@swag_from({
    "tags": ["Integrations"],
    "summary": "Entegrasyonu sil",
    "parameters": [
        {"name": "integration_id", "in": "path", "type": "string", "required": True}
    ],
    "responses": {
        200: {"description": "Entegrasyon deaktive edildi"},
        401: {"description": "Yetkisiz erişim"},
        403: {"description": "Yetki yok"},
        404: {"description": "Entegrasyon bulunamadı"}
    }
})
def delete_integration(integration_id):
    """Entegrasyonu deaktive et."""
    user = get_current_user()
    if not user:
        return jsonify({"error": "Unauthorized"}), 401
    
    integration = Integration.query.get_or_404(integration_id)
    
    if integration.organization_id != user.organization_id:
        return jsonify({"error": "Forbidden"}), 403
    
    integration.is_active = False
    db.session.commit()
    
    return jsonify({"message": "Integration deactivated"}), 200


@integrations_bp.route("/integrations/<uuid:integration_id>/sync", methods=["POST"])
@requires_auth
@swag_from({
    "tags": ["Integrations"],
    "summary": "Cihazları senkronize et",
    "description": "Bulut API'den cihazları çeker ve veritabanına kaydeder.",
    "parameters": [
        {"name": "integration_id", "in": "path", "type": "string", "required": True}
    ],
    "responses": {
        200: {"description": "Senkronizasyon sonucu"},
        401: {"description": "Yetkisiz erişim"},
        403: {"description": "Yetki yok"},
        404: {"description": "Entegrasyon bulunamadı"},
        501: {"description": "Henüz desteklenmeyen provider"},
        500: {"description": "Sync sırasında hata"}
    }
})
def sync_integration_devices(integration_id):
    """
    Entegrasyondan cihazları senkronize et.
    
    "Cihazları Tara" butonu bu endpoint'i çağırır.
    """
    user = get_current_user()
    if not user:
        return jsonify({"error": "Unauthorized"}), 401
    
    integration = Integration.query.get_or_404(integration_id)
    
    if integration.organization_id != user.organization_id:
        return jsonify({"error": "Forbidden"}), 403
    
    try:
        if integration.provider == "shelly":
            service = ShellyService(integration)
            synced_devices = service.sync_devices()
            
            return jsonify({
                "status": "success",
                "provider": "shelly",
                "devices_synced": len(synced_devices),
                "devices": synced_devices
            })
        
        # Diğer provider'lar için
        return jsonify({
            "status": "error",
            "message": f"Sync not implemented for {integration.provider}"
        }), 501
        
    except Exception as e:
        return jsonify({
            "status": "error",
            "message": str(e)
        }), 500


@integrations_bp.route("/integrations/<uuid:integration_id>/devices", methods=["GET"])
@requires_auth
@swag_from({
    "tags": ["Integrations"],
    "summary": "Entegrasyona bağlı cihazları listele",
    "parameters": [
        {"name": "integration_id", "in": "path", "type": "string", "required": True}
    ],
    "responses": {
        200: {"description": "Cihaz listesi"},
        401: {"description": "Yetkisiz erişim"},
        403: {"description": "Yetki yok"},
        404: {"description": "Entegrasyon bulunamadı"}
    }
})
def list_integration_devices(integration_id):
    """Entegrasyona bağlı cihazları listele."""
    user = get_current_user()
    if not user:
        return jsonify({"error": "Unauthorized"}), 401
    
    integration = Integration.query.get_or_404(integration_id)
    
    if integration.organization_id != user.organization_id:
        return jsonify({"error": "Forbidden"}), 403
    
    devices = SmartDevice.query.filter_by(
        integration_id=integration.id,
        is_active=True
    ).all()
    
    return jsonify([d.to_dict() for d in devices])


@integrations_bp.route("/integrations/providers", methods=["GET"])
@swag_from({
    "tags": ["Integrations"],
    "summary": "Desteklenen entegrasyon sağlayıcıları",
    "responses": {
        200: {"description": "Sağlayıcı listesi"}
    }
})
def list_providers():
    """Desteklenen bulut entegrasyon sağlayıcılarını listele."""
    providers = [
        {
            "id": "shelly",
            "name": "Shelly Cloud",
            "description": "Shelly akıllı prizler ve röleler",
            "auth_type": "api_key",
            "setup_url": "https://control.shelly.cloud",
            "supported": True
        },
        {
            "id": "tesla",
            "name": "Tesla",
            "description": "Tesla araçlar ve Powerwall",
            "auth_type": "oauth2",
            "setup_url": "https://auth.tesla.com",
            "supported": False  # Henüz implemente edilmedi
        },
        {
            "id": "tapo",
            "name": "TP-Link Tapo",
            "description": "Tapo akıllı prizler",
            "auth_type": "credentials",
            "supported": False
        },
        {
            "id": "tuya",
            "name": "Tuya / Smart Life",
            "description": "Tuya tabanlı cihazlar",
            "auth_type": "oauth2",
            "supported": False
        }
    ]
    
    return jsonify(providers)
