"""
Rol ve Yetki Yönetimi API - RBAC.

Admin panelinden rol oluşturma, düzenleme ve yetki atama.
"""
from flask import jsonify, request

from . import api_bp
from app.extensions import db
from app.models import Role, Permission
from app.auth import requires_auth, requires_role, requires_permission, get_db_user


# ==========================================
# ROL YÖNETİMİ
# ==========================================


@api_bp.route('/roles', methods=['GET'])
@requires_auth
@requires_permission('can_view_roles')
def list_roles():
    """
    Tüm rolleri listele.
    ---
    tags:
      - Roles
    security:
      - bearerAuth: []
    parameters:
      - name: include_permissions
        in: query
        type: boolean
        default: false
        description: Yetkileri de dahil et
      - name: include_system
        in: query
        type: boolean
        default: true
        description: Sistem rollerini dahil et
    responses:
      200:
        description: Rol listesi
        schema:
          type: object
          properties:
            roles:
              type: array
              items:
                type: object
                properties:
                  id:
                    type: string
                  code:
                    type: string
                    example: "admin"
                  name:
                    type: string
                    example: "Admin"
                  description:
                    type: string
                  is_system:
                    type: boolean
                  permissions:
                    type: array
                    items:
                      type: object
            total:
              type: integer
      401:
        description: Yetkisiz erişim
      403:
        description: Yetki yetersiz
    """
    include_permissions = request.args.get('include_permissions', 'false').lower() == 'true'
    include_system = request.args.get('include_system', 'true').lower() == 'true'
    
    query = Role.query.filter_by(is_active=True)
    
    if not include_system:
        query = query.filter_by(is_system=False)
    
    roles = query.order_by(Role.is_system.desc(), Role.name).all()
    
    return jsonify({
        "roles": [r.to_dict(include_permissions) for r in roles],
        "total": len(roles)
    })


@api_bp.route('/roles/<role_id>', methods=['GET'])
@requires_auth
@requires_permission('can_view_roles')
def get_role(role_id):
    """
    Tek bir rolün detaylarını getir.
    ---
    tags:
      - Roles
    security:
      - bearerAuth: []
    parameters:
      - name: role_id
        in: path
        type: string
        required: true
        description: Rol UUID'si
    responses:
      200:
        description: Rol detayları ve yetkileri
        schema:
          type: object
          properties:
            id:
              type: string
            code:
              type: string
            name:
              type: string
            description:
              type: string
            is_system:
              type: boolean
            permissions:
              type: array
              items:
                type: object
            user_count:
              type: integer
              description: Bu role sahip kullanıcı sayısı
      404:
        description: Rol bulunamadı
    """
    role = Role.query.get(role_id)
    if not role:
        return jsonify({"error": "Rol bulunamadı"}), 404
    
    data = role.to_dict(include_permissions=True)
    data["user_count"] = len(role.users)
    
    return jsonify(data)


@api_bp.route('/roles', methods=['POST'])
@requires_auth
@requires_permission('can_manage_roles')
def create_role():
    """
    Yeni rol oluştur.
    ---
    tags:
      - Roles
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
            - code
            - name
          properties:
            code:
              type: string
              description: Rol kodu (unique, snake_case)
              example: "technician"
            name:
              type: string
              description: Görünen isim
              example: "Teknisyen"
            description:
              type: string
              description: Rol açıklaması
              example: "Saha teknisyeni - cihaz bakımı"
            permission_ids:
              type: array
              items:
                type: string
              description: Atanacak yetki UUID'leri
    responses:
      201:
        description: Rol oluşturuldu
        schema:
          type: object
          properties:
            message:
              type: string
            role:
              type: object
      400:
        description: Eksik veya geçersiz veri
      409:
        description: Bu kod zaten kullanılıyor
    """
    data = request.get_json() or {}
    
    code = data.get('code', '').strip().lower().replace(' ', '_')
    name = data.get('name', '').strip()
    description = data.get('description', '').strip()
    permission_ids = data.get('permission_ids', [])
    
    if not code or not name:
        return jsonify({"error": "code ve name zorunludur"}), 400
    
    # Kod kontrolü
    existing = Role.query.filter_by(code=code).first()
    if existing:
        return jsonify({"error": f"'{code}' kodu zaten kullanılıyor"}), 409
    
    role = Role(
        code=code,
        name=name,
        description=description,
        is_system=False,  # Kullanıcı oluşturduğu roller sistem rolü değil
    )
    db.session.add(role)
    db.session.flush()
    
    # Yetkileri ekle
    if permission_ids:
        permissions = Permission.query.filter(Permission.id.in_(permission_ids)).all()
        role.permissions = permissions
    
    db.session.commit()
    
    return jsonify({
        "message": "Rol oluşturuldu",
        "role": role.to_dict(include_permissions=True)
    }), 201


@api_bp.route('/roles/<role_id>', methods=['PUT', 'PATCH'])
@requires_auth
@requires_permission('can_manage_roles')
def update_role(role_id):
    """
    Rol güncelle.
    ---
    tags:
      - Roles
    security:
      - bearerAuth: []
    consumes:
      - application/json
    parameters:
      - name: role_id
        in: path
        type: string
        required: true
        description: Rol UUID'si
      - name: body
        in: body
        required: true
        schema:
          type: object
          properties:
            name:
              type: string
              description: Görünen isim
            description:
              type: string
              description: Rol açıklaması
            permission_ids:
              type: array
              items:
                type: string
              description: Yeni yetki listesi (mevcut yetkiler değiştirilir)
            is_active:
              type: boolean
              description: Aktif/Pasif durumu
    responses:
      200:
        description: Rol güncellendi
      400:
        description: Sistem rolünün kodu değiştirilemez
      404:
        description: Rol bulunamadı
    """
    role = Role.query.get(role_id)
    if not role:
        return jsonify({"error": "Rol bulunamadı"}), 404
    
    data = request.get_json() or {}
    
    # Sistem rollerinin kodu değiştirilemez
    if role.is_system and 'code' in data:
        return jsonify({"error": "Sistem rolünün kodu değiştirilemez"}), 400
    
    # Güncellenebilir alanlar
    if 'name' in data:
        role.name = data['name'].strip()
    if 'description' in data:
        role.description = data['description'].strip()
    if 'is_active' in data and not role.is_system:
        role.is_active = data['is_active']
    
    # Yetkileri güncelle
    if 'permission_ids' in data:
        permission_ids = data['permission_ids']
        permissions = Permission.query.filter(Permission.id.in_(permission_ids)).all()
        role.permissions = permissions
    
    db.session.commit()
    
    return jsonify({
        "message": "Rol güncellendi",
        "role": role.to_dict(include_permissions=True)
    })


@api_bp.route('/roles/<role_id>', methods=['DELETE'])
@requires_auth
@requires_permission('can_manage_roles')
def delete_role(role_id):
    """
    Rol sil (soft delete - pasif yap).
    ---
    tags:
      - Roles
    security:
      - bearerAuth: []
    parameters:
      - name: role_id
        in: path
        type: string
        required: true
        description: Rol UUID'si
    responses:
      200:
        description: Rol silindi
      400:
        description: Sistem rolleri silinemez
      404:
        description: Rol bulunamadı
      409:
        description: Bu role atanmış kullanıcılar var
    """
    role = Role.query.get(role_id)
    if not role:
        return jsonify({"error": "Rol bulunamadı"}), 404
    
    if role.is_system:
        return jsonify({"error": "Sistem rolleri silinemez"}), 400
    
    # Kullanıcı kontrolü
    if role.users:
        return jsonify({
            "error": "Bu role atanmış kullanıcılar var",
            "user_count": len(role.users)
        }), 409
    
    # Soft delete
    role.is_active = False
    db.session.commit()
    
    return jsonify({"message": "Rol silindi"})


# ==========================================
# YETKİ YÖNETİMİ
# ==========================================


@api_bp.route('/permissions', methods=['GET'])
@requires_auth
@requires_permission('can_view_roles')
def list_permissions():
    """
    Tüm yetkileri listele.
    ---
    tags:
      - Roles
    security:
      - bearerAuth: []
    parameters:
      - name: category
        in: query
        type: string
        description: Kategori filtresi (devices, automations, wallet, vb.)
    responses:
      200:
        description: Yetki listesi
        schema:
          type: object
          properties:
            permissions:
              type: array
              items:
                type: object
                properties:
                  id:
                    type: string
                  code:
                    type: string
                    example: "can_edit_devices"
                  name:
                    type: string
                    example: "Cihaz Düzenle"
                  description:
                    type: string
                  category:
                    type: string
                    example: "devices"
            categories:
              type: array
              items:
                type: string
              description: Mevcut kategoriler
    """
    category = request.args.get('category')
    
    query = Permission.query
    if category:
        query = query.filter_by(category=category)
    
    permissions = query.order_by(Permission.category, Permission.name).all()
    
    # Kategorileri topla
    categories = db.session.query(Permission.category).distinct().all()
    categories = [c[0] for c in categories if c[0]]
    
    return jsonify({
        "permissions": [p.to_dict() for p in permissions],
        "categories": sorted(categories),
        "total": len(permissions)
    })


@api_bp.route('/roles/seed', methods=['POST'])
@requires_auth
@requires_role('super_admin')
def seed_roles():
    """
    Varsayılan rolleri ve yetkileri oluştur/güncelle.
    ---
    tags:
      - Roles
    security:
      - bearerAuth: []
    responses:
      200:
        description: Roller oluşturuldu
        schema:
          type: object
          properties:
            message:
              type: string
            roles:
              type: array
              items:
                type: object
    """
    Role.seed_default_roles()
    
    roles = Role.query.filter_by(is_active=True).all()
    
    return jsonify({
        "message": "Varsayılan roller oluşturuldu/güncellendi",
        "roles": [r.to_dict(include_permissions=True) for r in roles]
    })
