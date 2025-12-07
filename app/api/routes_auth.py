"""Kullanıcı kimlik doğrulama ve profil endpoint'leri - v6.0."""
from flask import jsonify, request, current_app

from . import api_bp
from .helpers import get_current_user
from app.extensions import db
from app.models import User, Organization, Wallet, Role
from app.auth import requires_auth


@api_bp.route('/auth/me', methods=['GET'])
@requires_auth
def get_my_profile():
    """
    Token'daki kullanıcının profil bilgisini döner.
    ---
    tags:
      - Auth
    security:
      - bearerAuth: []
    responses:
      200:
        description: Kullanıcı profili, rol ve yetki bilgisi
        schema:
          type: object
          properties:
            id:
              type: string
              example: "550e8400-e29b-41d4-a716-446655440000"
            auth0_id:
              type: string
              example: "google-oauth2|123456789"
            email:
              type: string
              example: "user@awaxen.com"
            full_name:
              type: string
              example: "Ahmet Yılmaz"
            role:
              type: object
              properties:
                code:
                  type: string
                  example: "admin"
                name:
                  type: string
                  example: "Admin"
            permissions:
              type: array
              items:
                type: string
              example: ["can_view_devices", "can_edit_devices"]
            organization:
              type: object
      401:
        description: Yetkisiz erişim
    """
    user = get_current_user()
    if not user:
        return jsonify({"error": "User not found"}), 401

    response = user.to_dict(include_permissions=True)
    
    # Organizasyon bilgisini de ekle
    if user.organization:
        response["organization"] = {
            "id": str(user.organization.id),
            "name": user.organization.name,
            "type": user.organization.type,
            "subscription_plan": user.organization.subscription_plan,
        }
    
    return jsonify(response)


@api_bp.route('/auth/sync', methods=['POST'])
def sync_user():
    """
    Auth0 kullanıcısını Postgres ile senkronize et (Upsert).
    
    İlk girişte kullanıcı, organizasyon ve cüzdan oluşturulur.
    Auth0'dan gelen rol, veritabanındaki roles tablosundan eşleştirilir.
    ---
    tags:
      - Auth
    consumes:
      - application/json
    parameters:
      - in: header
        name: X-Auth0-Id
        type: string
        description: Auth0 kullanıcı ID'si (alternatif olarak body'de gönderilebilir)
      - in: header
        name: X-Auth0-Email
        type: string
        description: Kullanıcı email adresi
      - in: header
        name: X-Auth0-Name
        type: string
        description: Kullanıcı tam adı
      - in: body
        name: body
        required: true
        schema:
          type: object
          required:
            - auth0_id
            - email
          properties:
            auth0_id:
              type: string
              description: Auth0 kullanıcı ID'si
              example: "google-oauth2|123456789"
            email:
              type: string
              description: Kullanıcı email adresi
              example: "user@awaxen.com"
            name:
              type: string
              description: Kullanıcı tam adı
              example: "Ahmet Yılmaz"
            role:
              type: string
              description: Auth0'dan gelen rol kodu
              enum: [super_admin, admin, operator, viewer, farmer]
              example: "admin"
    responses:
      200:
        description: Mevcut kullanıcı güncellendi
        schema:
          type: object
          properties:
            status:
              type: string
              example: "synced"
            message:
              type: string
            user:
              type: object
            organization:
              type: object
      201:
        description: Yeni kullanıcı oluşturuldu
      400:
        description: Eksik parametre (auth0_id veya email)
      500:
        description: Sunucu hatası
    """
    try:
        payload = request.get_json(silent=True) or {}

        auth0_id = request.headers.get('X-Auth0-Id') or payload.get('auth0_id')
        email = request.headers.get('X-Auth0-Email') or payload.get('email')
        full_name = request.headers.get('X-Auth0-Name') or payload.get('name')
        frontend_role = payload.get('role')

        if not auth0_id or not email:
            return jsonify({"error": "auth0_id ve email zorunludur"}), 400

        user = User.query.filter_by(auth0_id=auth0_id).first()

        if user:
            current_app.logger.info(f"[AuthSync] Kullanıcı güncelleniyor: {email}")
            user.email = email
            user.full_name = full_name or user.full_name

            # Auth0'dan gelen rolü veritabanından bul ve ata
            if frontend_role:
                role_db = Role.get_by_code(frontend_role)
                if role_db:
                    user.role_id = role_db.id
                    current_app.logger.info(f"[AuthSync] Rol güncellendi: {frontend_role}")

            db.session.commit()

            return jsonify({
                "status": "synced",
                "message": "Kullanıcı güncellendi",
                "user": user.to_dict(include_permissions=True),
                "organization": user.organization.to_dict() if user.organization else None,
            }), 200

        current_app.logger.info(f"[AuthSync] Yeni kullanıcı oluşturuluyor: {email}")

        # Rol belirleme mantığı:
        # 1. İlk kullanıcı otomatik super_admin olur
        # 2. Auth0'dan gelen rol varsa veritabanından bul
        # 3. Yoksa varsayılan viewer
        user_count = User.query.count()
        
        if user_count == 0:
            role_code = 'super_admin'
        elif frontend_role:
            role_code = frontend_role
        else:
            role_code = 'viewer'
        
        # Rolü veritabanından bul
        role_db = Role.get_by_code(role_code)
        if not role_db:
            # Varsayılan roller yoksa oluştur
            Role.seed_default_roles()
            role_db = Role.get_by_code(role_code)
        
        if not role_db:
            role_db = Role.get_by_code('viewer')  # Son çare

        org = Organization(
            name=f"{full_name or email}'s Home",
            type="home",
            subscription_plan="free",
            is_active=True,
        )
        db.session.add(org)
        db.session.flush()

        user = User(
            auth0_id=auth0_id,
            email=email,
            full_name=full_name or 'New User',
            role_id=role_db.id if role_db else None,
            organization_id=org.id,
        )
        db.session.add(user)
        db.session.flush()

        try:
            wallet = Wallet(user_id=user.id, balance=0.0)
            db.session.add(wallet)
        except Exception as wallet_err:
            current_app.logger.warning(f"[AuthSync] Wallet oluşturulamadı: {wallet_err}")

        db.session.commit()

        return jsonify({
            "status": "created",
            "message": "Kullanıcı ve organizasyon oluşturuldu",
            "user": user.to_dict(include_permissions=True),
            "organization": org.to_dict(),
        }), 201

    except Exception as exc:
        db.session.rollback()
        current_app.logger.error(f"[AuthSync] Hata: {exc}")
        return jsonify({"error": "Sunucu hatası", "details": str(exc)}), 500
