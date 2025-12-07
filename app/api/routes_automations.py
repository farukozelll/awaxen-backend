"""
Automation Routes - Otomasyon Kuralları.

Fiyat bazlı, zaman bazlı ve sensör bazlı otomasyonlar.
"""
from flask import Blueprint, request, jsonify
from flasgger import swag_from

from app.extensions import db
from app.models import Automation, AutomationLog, SmartAsset
from app.api.helpers import (
    get_current_user,
    get_pagination_params,
    paginate_response,
)
from app.services.automation_engine import automation_engine
from app.auth import requires_auth

automations_bp = Blueprint("automations", __name__)


@automations_bp.route("/automations", methods=["GET"])
@requires_auth
@swag_from({
    "tags": ["Automations"],
    "summary": "Otomasyonları listele",
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
            "name": "search",
            "in": "query",
            "type": "string",
            "description": "İsme göre arama"
        },
        {
            "name": "is_active",
            "in": "query",
            "type": "boolean",
            "description": "Aktif durumuna göre filtrele"
        },
    ],
    "responses": {
        200: {
            "description": "Paginated automation listesi",
            "schema": {
                "type": "object",
                "properties": {
                    "data": {
                        "type": "array",
                        "items": {"$ref": "#/definitions/Automation"}
                    },
                    "pagination": {"$ref": "#/definitions/Pagination"}
                }
            }
        },
        401: {"description": "Yetkisiz erişim"}
    }
})
def list_automations():
    """Organizasyonun otomasyonlarını listele."""
    user = get_current_user()
    if not user or not user.organization_id:
        return jsonify({"error": "Unauthorized"}), 401
    
    page, page_size = get_pagination_params()
    search = request.args.get("search", "", type=str).strip()
    is_active = request.args.get("is_active")
    
    # Temel filtre: Organizasyon bazlı izolasyon
    query = Automation.query.filter_by(organization_id=user.organization_id)
    
    # Row-Level Security: Admin/super_admin değilse sadece kendi oluşturduklarını görsün
    user_role_code = user.role.code if user.role else None
    if user_role_code not in ["admin", "super_admin"]:
        query = query.filter_by(created_by=user.id)
    
    if search:
        query = query.filter(Automation.name.ilike(f"%{search}%"))
    
    if is_active is not None:
        bool_value = is_active.lower() == "true"
        query = query.filter(Automation.is_active == bool_value)
    
    query = query.order_by(Automation.created_at.desc())
    total = query.count()
    items = query.offset((page - 1) * page_size).limit(page_size).all()
    
    return jsonify(paginate_response([a.to_dict() for a in items], total, page, page_size))


@automations_bp.route("/automations/<uuid:automation_id>", methods=["GET"])
@requires_auth
@swag_from({
    "tags": ["Automations"],
    "summary": "Otomasyon detayı",
    "parameters": [
        {
            "name": "automation_id",
            "in": "path",
            "required": True,
            "type": "string",
            "description": "Otomasyon UUID"
        }
    ],
    "responses": {
        200: {"description": "Otomasyon bilgileri"},
        401: {"description": "Yetkisiz erişim"},
        403: {"description": "Yetkisiz organizasyon"},
        404: {"description": "Otomasyon bulunamadı"}
    }
})
def get_automation(automation_id):
    """Tek bir otomasyonun detaylarını getir."""
    user = get_current_user()
    if not user:
        return jsonify({"error": "Unauthorized"}), 401
    
    automation = Automation.query.get_or_404(automation_id)
    
    # Organizasyon kontrolü
    if automation.organization_id != user.organization_id:
        return jsonify({"error": "Forbidden"}), 403
    
    # Row-Level Security: Admin değilse sadece kendi oluşturduğunu görebilir
    user_role_code = user.role.code if user.role else None
    if user_role_code not in ["admin", "super_admin"] and automation.created_by != user.id:
        return jsonify({"error": "Forbidden"}), 403
    
    result = automation.to_dict()
    
    # Asset bilgisini ekle
    if automation.asset:
        result["asset"] = automation.asset.to_dict()
    
    return jsonify(result)


@automations_bp.route("/automations", methods=["POST"])
@requires_auth
@swag_from({
    "tags": ["Automations"],
    "summary": "Yeni otomasyon oluştur",
    "consumes": ["application/json"],
    "parameters": [
        {
            "name": "body",
            "in": "body",
            "schema": {
                "type": "object",
                "properties": {
                    "name": {"type": "string", "example": "Ucuz Saatte Şarj"},
                    "asset_id": {"type": "string"},
                    "rules": {
                        "type": "object",
                        "example": {
                            "trigger": {"type": "price", "operator": "<", "value": 2.0},
                            "action": {"type": "turn_on"},
                            "conditions": [{"type": "time_range", "start": "22:00", "end": "06:00"}]
                        }
                    }
                },
                "required": ["name", "rules"]
            }
        }
    ],
    "responses": {
        201: {
            "description": "Otomasyon oluşturuldu",
            "schema": {"$ref": "#/definitions/Automation"}
        },
        400: {"description": "Geçersiz istek"},
        401: {"description": "Yetkisiz erişim"}
    }
})
def create_automation():
    """
    Yeni otomasyon kuralı oluştur.
    
    Örnek rules formatı:
    {
        "trigger": {
            "type": "price",      // price, time_range, sensor
            "operator": "<",      // <, >, <=, >=, ==
            "value": 2.0          // Eşik değeri
        },
        "action": {
            "type": "turn_on",    // turn_on, turn_off, set_power
            "value": 100          // set_power için güç yüzdesi
        },
        "conditions": [           // Opsiyonel ek koşullar
            {
                "type": "time_range",
                "start": "22:00",
                "end": "06:00",
                "days": [0, 1, 2, 3, 4, 5, 6]  // 0=Pazartesi
            }
        ]
    }
    """
    user = get_current_user()
    if not user or not user.organization_id:
        return jsonify({"error": "Unauthorized"}), 401
    
    data = request.get_json()
    
    if not data.get("name"):
        return jsonify({"error": "Name is required"}), 400
    if not data.get("rules"):
        return jsonify({"error": "Rules are required"}), 400
    
    # Asset kontrolü
    asset_id = data.get("asset_id")
    if asset_id:
        asset = SmartAsset.query.get(asset_id)
        if not asset or asset.organization_id != user.organization_id:
            return jsonify({"error": "Asset not found"}), 404
    
    automation = Automation(
        organization_id=user.organization_id,
        asset_id=asset_id,
        created_by=user.id,  # Row-level security için oluşturan kullanıcı
        name=data["name"],
        description=data.get("description"),
        rules=data["rules"],
        is_active=data.get("is_active", True)
    )
    
    db.session.add(automation)
    db.session.commit()
    
    return jsonify(automation.to_dict()), 201


@automations_bp.route("/automations/<uuid:automation_id>", methods=["PUT"])
@requires_auth
@swag_from({
    "tags": ["Automations"],
    "summary": "Otomasyonu güncelle",
    "consumes": ["application/json"],
    "parameters": [
        {
            "name": "automation_id",
            "in": "path",
            "required": True,
            "type": "string",
            "description": "Otomasyon UUID"
        },
        {
            "name": "body",
            "in": "body",
            "schema": {
                "type": "object",
                "properties": {
                    "name": {"type": "string"},
                    "description": {"type": "string"},
                    "rules": {"type": "object"},
                    "is_active": {"type": "boolean"},
                    "asset_id": {"type": "string"}
                }
            }
        }
    ],
    "responses": {
        200: {"description": "Otomasyon güncellendi"},
        401: {"description": "Yetkisiz erişim"},
        403: {"description": "Yetkisiz organizasyon"},
        404: {"description": "Otomasyon bulunamadı"}
    }
})
def update_automation(automation_id):
    """Otomasyon kurallarını güncelle."""
    user = get_current_user()
    if not user:
        return jsonify({"error": "Unauthorized"}), 401
    
    automation = Automation.query.get_or_404(automation_id)
    
    # Organizasyon kontrolü
    if automation.organization_id != user.organization_id:
        return jsonify({"error": "Forbidden"}), 403
    
    # Row-Level Security: Admin değilse sadece kendi oluşturduğunu güncelleyebilir
    user_role_code = user.role.code if user.role else None
    if user_role_code not in ["admin", "super_admin"] and automation.created_by != user.id:
        return jsonify({"error": "Forbidden"}), 403
    
    data = request.get_json()
    
    if "name" in data:
        automation.name = data["name"]
    if "description" in data:
        automation.description = data["description"]
    if "rules" in data:
        automation.rules = data["rules"]
    if "is_active" in data:
        automation.is_active = data["is_active"]
    if "asset_id" in data:
        automation.asset_id = data["asset_id"]
    
    db.session.commit()
    
    return jsonify(automation.to_dict())


@automations_bp.route("/automations/<uuid:automation_id>", methods=["DELETE"])
@requires_auth
@swag_from({
    "tags": ["Automations"],
    "summary": "Otomasyonu sil",
    "parameters": [
        {
            "name": "automation_id",
            "in": "path",
            "required": True,
            "type": "string",
            "description": "Otomasyon UUID"
        }
    ],
    "responses": {
        200: {"description": "Otomasyon silindi"},
        401: {"description": "Yetkisiz erişim"},
        403: {"description": "Yetkisiz organizasyon"},
        404: {"description": "Otomasyon bulunamadı"}
    }
})
def delete_automation(automation_id):
    """Otomasyonu sil."""
    user = get_current_user()
    if not user:
        return jsonify({"error": "Unauthorized"}), 401
    
    automation = Automation.query.get_or_404(automation_id)
    
    # Organizasyon kontrolü
    if automation.organization_id != user.organization_id:
        return jsonify({"error": "Forbidden"}), 403
    
    # Row-Level Security: Admin değilse sadece kendi oluşturduğunu silebilir
    user_role_code = user.role.code if user.role else None
    if user_role_code not in ["admin", "super_admin"] and automation.created_by != user.id:
        return jsonify({"error": "Forbidden"}), 403
    
    db.session.delete(automation)
    db.session.commit()
    
    return jsonify({"message": "Automation deleted"}), 200


@automations_bp.route("/automations/<uuid:automation_id>/toggle", methods=["POST"])
@requires_auth
@swag_from({
    "tags": ["Automations"],
    "summary": "Otomasyonu aç/kapat",
    "parameters": [
        {
            "name": "automation_id",
            "in": "path",
            "required": True,
            "type": "string",
            "description": "Otomasyon UUID"
        }
    ],
    "responses": {
        200: {"description": "Otomasyon durumu değiştirildi"},
        401: {"description": "Yetkisiz erişim"},
        403: {"description": "Yetkisiz organizasyon"},
        404: {"description": "Otomasyon bulunamadı"}
    }
})
def toggle_automation(automation_id):
    """Otomasyonu aktif/pasif yap."""
    user = get_current_user()
    if not user:
        return jsonify({"error": "Unauthorized"}), 401
    
    automation = Automation.query.get_or_404(automation_id)
    
    if automation.organization_id != user.organization_id:
        return jsonify({"error": "Forbidden"}), 403
    
    automation.is_active = not automation.is_active
    db.session.commit()
    
    return jsonify({
        "id": str(automation.id),
        "is_active": automation.is_active,
        "message": f"Automation {'activated' if automation.is_active else 'deactivated'}"
    })


@automations_bp.route("/automations/<uuid:automation_id>/test", methods=["POST"])
@requires_auth
@swag_from({
    "tags": ["Automations"],
    "summary": "Otomasyonu test et",
    "description": "Kuralları değerlendirir ama aksiyonu çalıştırmaz.",
    "parameters": [
        {
            "name": "automation_id",
            "in": "path",
            "required": True,
            "type": "string",
            "description": "Otomasyon UUID"
        }
    ],
    "responses": {
        200: {"description": "Test sonucu"},
        401: {"description": "Yetkisiz erişim"},
        403: {"description": "Yetkisiz organizasyon"},
        404: {"description": "Otomasyon bulunamadı"}
    }
})
def test_automation(automation_id):
    """
    Otomasyonu test et.
    
    Kuralları değerlendirir ve tetiklenip tetiklenmeyeceğini söyler.
    Gerçek aksiyonu ÇALIŞTIRMAZ.
    """
    user = get_current_user()
    if not user:
        return jsonify({"error": "Unauthorized"}), 401
    
    automation = Automation.query.get_or_404(automation_id)
    
    if automation.organization_id != user.organization_id:
        return jsonify({"error": "Forbidden"}), 403
    
    should_trigger, reason = automation_engine.evaluate(automation)
    
    return jsonify({
        "automation_id": str(automation.id),
        "name": automation.name,
        "would_trigger": should_trigger,
        "reason": reason,
        "rules": automation.rules
    })


@automations_bp.route("/automations/<uuid:automation_id>/run", methods=["POST"])
@requires_auth
@swag_from({
    "tags": ["Automations"],
    "summary": "Otomasyonu manuel çalıştır",
    "parameters": [
        {
            "name": "automation_id",
            "in": "path",
            "required": True,
            "type": "string",
            "description": "Otomasyon UUID"
        }
    ],
    "responses": {
        200: {"description": "Çalıştırma sonucu"},
        401: {"description": "Yetkisiz erişim"},
        403: {"description": "Yetkisiz organizasyon"},
        404: {"description": "Otomasyon bulunamadı"}
    }
})
def run_automation(automation_id):
    """
    Otomasyonu manuel olarak çalıştır.
    
    Koşulları kontrol eder ve uygunsa aksiyonu gerçekleştirir.
    """
    user = get_current_user()
    if not user:
        return jsonify({"error": "Unauthorized"}), 401
    
    automation = Automation.query.get_or_404(automation_id)
    
    if automation.organization_id != user.organization_id:
        return jsonify({"error": "Forbidden"}), 403
    
    result = automation_engine.run_automation(automation)
    
    return jsonify({
        "automation_id": str(automation.id),
        "name": automation.name,
        **result
    })


@automations_bp.route("/automations/<uuid:automation_id>/logs", methods=["GET"])
@requires_auth
@swag_from({
    "tags": ["Automations"],
    "summary": "Otomasyon loglarını getir",
    "parameters": [
        {
            "name": "automation_id",
            "in": "path",
            "required": True,
            "type": "string",
            "description": "Otomasyon UUID"
        },
        {
            "name": "limit",
            "in": "query",
            "type": "integer",
            "default": 50,
            "description": "Döndürülecek maksimum log sayısı"
        }
    ],
    "responses": {
        200: {"description": "Log listesi"},
        401: {"description": "Yetkisiz erişim"},
        403: {"description": "Yetkisiz organizasyon"},
        404: {"description": "Otomasyon bulunamadı"}
    }
})
def get_automation_logs(automation_id):
    """Otomasyonun çalışma geçmişini getir."""
    user = get_current_user()
    if not user:
        return jsonify({"error": "Unauthorized"}), 401
    
    automation = Automation.query.get_or_404(automation_id)
    
    if automation.organization_id != user.organization_id:
        return jsonify({"error": "Forbidden"}), 403
    
    limit = request.args.get("limit", 50, type=int)
    
    logs = AutomationLog.query.filter_by(
        automation_id=automation.id
    ).order_by(AutomationLog.triggered_at.desc()).limit(limit).all()
    
    return jsonify([log.to_dict() for log in logs])


@automations_bp.route("/automations/templates", methods=["GET"])
@requires_auth
@swag_from({
    "tags": ["Automations"],
    "summary": "Hazır otomasyon şablonları",
    "responses": {
        200: {"description": "Şablon listesi"}
    }
})
def get_automation_templates():
    """Kullanıcının hızlıca uygulayabileceği hazır şablonlar."""
    templates = [
        {
            "id": "cheap_charging",
            "name": "Ucuz Saatte Şarj",
            "description": "Elektrik fiyatı 2 TL/kWh altına düşünce cihazı aç",
            "rules": {
                "trigger": {"type": "price", "operator": "<", "value": 2.0},
                "action": {"type": "turn_on"}
            }
        },
        {
            "id": "night_heating",
            "name": "Gece Isıtma",
            "description": "Gece 22:00-06:00 arası ısıtıcıyı çalıştır",
            "rules": {
                "trigger": {"type": "time_range", "start": "22:00", "end": "06:00"},
                "action": {"type": "turn_on"}
            }
        },
        {
            "id": "peak_saver",
            "name": "Puant Tasarrufu",
            "description": "Puant saatlerinde (17:00-22:00) cihazı kapat",
            "rules": {
                "trigger": {"type": "time_range", "start": "17:00", "end": "22:00"},
                "action": {"type": "turn_off"}
            }
        },
        {
            "id": "price_alert",
            "name": "Yüksek Fiyat Uyarısı",
            "description": "Fiyat 4 TL/kWh üstüne çıkınca cihazı kapat",
            "rules": {
                "trigger": {"type": "price", "operator": ">", "value": 4.0},
                "action": {"type": "turn_off"}
            }
        }
    ]
    
    return jsonify(templates)
