import os
import re
import time
from datetime import datetime
from typing import Optional
import requests

from flask import Blueprint, request, jsonify, g
from . import db
from .models import (
    User, Site, Device, Node, Telemetry, Command, SensorData, Asset, 
    Tariff, VppRule, DiscoveryQueue, DiscoveryStatus
)
from .auth import requires_auth, get_current_user_id
from .services import (
    # Device işlemleri
    create_device_logic, update_device_logic, delete_device_logic,
    # Site işlemleri
    create_site_logic, update_site_logic,
    # Node işlemleri
    create_node_logic, update_node_logic, delete_node_logic,
    # Asset işlemleri
    create_asset_logic, update_asset_logic, delete_asset_logic,
    get_assets_by_node, get_assets_by_site, get_site_hierarchy,
    # ENUM yardımcıları
    get_site_types, get_device_statuses, get_node_protocols,
    get_asset_types, get_asset_categories,
    # VPP ENUM yardımcıları
    get_node_types, get_inverter_brands, get_tariff_types,
    get_vpp_trigger_types, get_vpp_action_types,
    # Tarife işlemleri
    create_tariff_logic, update_tariff_logic, delete_tariff_logic,
    get_current_tariff_price,
    # Piyasa fiyatları
    save_market_prices, get_market_prices_for_date, get_current_market_price,
    # VPP işlemleri
    create_vpp_rule_logic, update_vpp_rule_logic, delete_vpp_rule_logic,
    get_vpp_rules_for_node, get_vpp_rule_logs,
    # Inverter işlemleri
    get_inverters_for_user, get_inverter_summary,
)

main = Blueprint('main', __name__)

# ===========================================
# HAVA DURUMU CACHE (Para Tasarrufu)
# ===========================================
# Yapı: { site_id: { "data": {...}, "timestamp": 1701234567 } }
weather_cache = {}
CACHE_TIMEOUT = 900  # 15 Dakika (Saniye cinsinden)

# ===========================================
# YARDIMCI FONKSİYONLAR
# ===========================================

def get_or_create_user():
    """Token'dan gelen kullanıcıyı DB'de bul veya oluştur."""
    auth0_id = get_current_user_id()
    if not auth0_id:
        return None

    user = User.query.filter_by(auth0_id=auth0_id).first()
    if not user:
        # İlk giriş - kullanıcıyı kaydet
        token_info = g.current_user
        user = User(
            auth0_id=auth0_id,
            email=token_info.get("email", f"{auth0_id}@unknown.com"),
            full_name=token_info.get("name", "Yeni Kullanıcı"),
            role="viewer",
        )
        db.session.add(user)
        db.session.commit()
    return user


def parse_iso_datetime(value: Optional[str]):
    if not value:
        return None
    try:
        cleaned = value.replace("Z", "+00:00") if value.endswith("Z") else value
        return datetime.fromisoformat(cleaned)
    except ValueError:
        return None


def get_pagination_params():
    """Query parametrelerinden pagination bilgilerini al."""
    page = request.args.get("page", 1, type=int)
    page_size = request.args.get("pageSize", 20, type=int)
    # Güvenlik: max 100 kayıt
    page_size = min(page_size, 100)
    return page, page_size


def get_filter_params():
    """Query parametrelerinden filtreleme bilgilerini al."""
    return {
        "search": request.args.get("search", "", type=str).strip(),
        "sort_by": request.args.get("sortBy", "id", type=str),
        "sort_order": request.args.get("sortOrder", "asc", type=str).lower(),
    }


def paginate_response(items: list, total: int, page: int, page_size: int):
    """Standart pagination response formatı."""
    return {
        "data": items,
        "pagination": {
            "page": page,
            "pageSize": page_size,
            "total": total,
            "totalPages": (total + page_size - 1) // page_size if page_size > 0 else 0,
        },
    }


def apply_sorting(query, model, sort_by: str, sort_order: str, allowed_fields: list):
    """Query'ye sıralama uygula."""
    if sort_by not in allowed_fields:
        sort_by = "id"
    
    column = getattr(model, sort_by, None)
    if column is None:
        column = model.id
    
    if sort_order == "desc":
        return query.order_by(column.desc())
    return query.order_by(column.asc())


def parse_decimal(value: Optional[str]) -> Optional[float]:
    """String veya sayıyı güvenle floata çevir."""
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        cleaned = value.strip().replace("°", "")
        if not cleaned:
            return None
        cleaned = cleaned.replace(",", ".")
        try:
            return float(cleaned)
        except ValueError:
            return None
    return None


def resolve_site_coordinates(site: Site) -> tuple[Optional[float], Optional[float]]:
    """Site koordinatını latitude/longitude veya location'dan üret."""
    lat = parse_decimal(site.latitude)
    lon = parse_decimal(site.longitude)
    if lat is not None and lon is not None:
        return lat, lon

    if site.location:
        tokens = [tok for tok in re.split(r"[;|,\s]+", site.location) if tok]
        if len(tokens) >= 2:
            lat_candidate = parse_decimal(tokens[0])
            lon_candidate = parse_decimal(tokens[1])
            if lat_candidate is not None and lon_candidate is not None:
                if site.latitude is None or site.longitude is None:
                    site.latitude = lat_candidate
                    site.longitude = lon_candidate
                    db.session.commit()
                return lat_candidate, lon_candidate

    return None, None


# ===========================================
# PUBLIC ENDPOINTS (Token gerekmez)
# ===========================================

@main.route('/')
def home():
    """
    Uygulama ana sayfası.
    ---
    tags:
      - Genel
    responses:
      200:
        description: Uygulama ana sayfası
    """
    return "Awaxen Industrial Backend Hazır!"

# --- 1. CİHAZDAN GELEN VERİYİ KAYDETME (Ingest) ---
@main.route('/api/telemetry', methods=['POST'])
def receive_telemetry():
    """
    Core cihazlardan telemetri verisini kaydet.
    ---
    tags:
      - Telemetry
    consumes:
      - application/json
    parameters:
      - in: body
        name: telemetry
        required: true
        schema:
          type: object
          properties:
            serial_number:
              type: string
              example: AWX-CORE-0001
            node_name:
              type: string
              example: Solar Inverter
            data:
              type: object
              example: {"power": 4200.5, "voltage": 810}
    responses:
      201:
        description: Telemetri kaydedildi
      404:
        description: Cihaz veya node bulunamadı
    """
    try:
        payload = request.json
        
        # 1. Cihazı Bul
        device = Device.query.filter_by(serial_number=payload['serial_number']).first()
        if not device:
            return jsonify({"error": "Cihaz bulunamadı"}), 404
            
        # 2. Node'u Bul (Yoksa yaratma mantığı eklenebilir ama şimdilik var sayalım)
        node = Node.query.filter_by(device_id=device.id, name=payload['node_name']).first()
        if not node:
             # Basitlik için: Node yoksa varsayılan bir node bul veya hata dön
             return jsonify({"error": "Node tanimsiz"}), 404

        # 3. Verileri Kaydet
        for key, value in payload['data'].items():
            new_telemetry = Telemetry(
                node_id=node.id,
                key=key,
                value=float(value)
            )
            db.session.add(new_telemetry)
        
        # 4. Cihazı Online İşaretle
        device.is_online = True
        db.session.commit()
        
        return jsonify({"status": "success"}), 201

    except Exception as e:
        return jsonify({"error": str(e)}), 400

@main.route('/api/telemetry/history', methods=['GET'])
@requires_auth
def get_telemetry_history():
    """
    Bir node için tarih aralığındaki telemetri verilerini getir.
    ---
    tags:
      - Telemetry
    parameters:
      - in: query
        name: node_id
        required: true
        schema:
          type: integer
      - in: query
        name: start_date
        required: false
        schema:
          type: string
          format: date-time
      - in: query
        name: end_date
        required: false
        schema:
          type: string
          format: date-time
    responses:
      200:
        description: Telemetri geçmişi
    """
    user = get_or_create_user()
    if not user:
        return jsonify({"error": "Kullanıcı bulunamadı"}), 401

    node_id = request.args.get('node_id', type=int)
    if not node_id:
        return jsonify({"error": "node_id zorunlu"}), 400

    node = Node.query.join(Device).join(Site).filter(
        Node.id == node_id,
        Site.user_id == user.id,
    ).first()
    if not node:
        return jsonify({"error": "Node bulunamadı"}), 404

    start = parse_iso_datetime(request.args.get('start_date'))
    end = parse_iso_datetime(request.args.get('end_date'))

    query = Telemetry.query.filter(Telemetry.node_id == node_id)
    if start:
        query = query.filter(Telemetry.time >= start)
    if end:
        query = query.filter(Telemetry.time <= end)

    records = query.order_by(Telemetry.time.asc()).limit(5000).all()

    return jsonify([
        {
            "time": rec.time.isoformat(),
            "key": rec.key,
            "value": rec.value,
        }
        for rec in records
    ])

# --- 1.b ÖN TARAF SENKRONİZASYONU (Auth0'dan gelen kullanıcıyı DB'ye yaz) ---
@main.route('/api/sync-user', methods=['POST'])
def sync_user():
    """
    Auth0 kullanıcısını Postgres ile senkronize et.
    ---
    tags:
      - Kullanıcı
    consumes:
      - application/json
    parameters:
      - in: header
        name: X-Auth0-Id
        required: false
        type: string
      - in: body
        name: payload
        required: true
        schema:
          type: object
          properties:
            auth0_id:
              type: string
              example: google-oauth2|123
            email:
              type: string
              example: user@awaxen.com
            name:
              type: string
              example: Awaxen User
            role:
              type: string
              example: farmer-user
    responses:
      200:
        description: Kullanıcı bilgileri güncellendi
    """
    payload = request.get_json(force=True, silent=True) or {}

    # Header üzerinden gelen bilgiler (Next.js bu şekilde gönderiyor)
    auth0_id = request.headers.get('X-Auth0-Id') or payload.get('auth0_id')
    email = request.headers.get('X-Auth0-Email') or payload.get('email')
    full_name = request.headers.get('X-Auth0-Name') or payload.get('name')
    role = request.headers.get('X-Auth0-Role') or payload.get('role', 'viewer')

    if not auth0_id:
        return jsonify({"error": "auth0_id eksik"}), 400

    user = User.query.filter_by(auth0_id=auth0_id).first()
    created = False

    if not user:
        user = User(
            auth0_id=auth0_id,
            email=email,
            full_name=full_name or 'Yeni Kullanıcı',
            role=role or 'viewer',
        )
        db.session.add(user)
        created = True
    else:
        user.email = email or user.email
        user.full_name = full_name or user.full_name
        if role:
            user.role = role

    db.session.commit()

    return jsonify({
        "message": "Kullanıcı senkronize edildi",
        "created": created,
        "user": {
            "id": user.id,
            "auth0_id": user.auth0_id,
            "email": user.email,
            "full_name": user.full_name,
            "role": user.role,
        },
    }), 200

# --- 2. FRONTEND İÇİN VERİ ÇEKME (Dashboard) ---
@main.route('/api/dashboard', methods=['GET'])
@requires_auth
def get_dashboard():
    """
    Token'daki kullanıcının dashboard verilerini getir.
    ---
    tags:
      - Dashboard
    security:
      - bearerAuth: []
    responses:
      200:
        description: Dashboard verisi
    """
    user = get_or_create_user()
    if not user:
        return jsonify({"error": "Kullanıcı bulunamadı"}), 401

    response_data = {
        "user": {
            "id": user.id,
            "full_name": user.full_name,
            "email": user.email,
            "role": user.role,
        },
        "sites": []
    }

    for site in user.sites:
        site_data = {
            "id": site.id,
            "name": site.name,
            "city": site.city,
            "location": site.location,
            "latitude": site.latitude,
            "longitude": site.longitude,
            "devices": []
        }
        for device in site.devices:
            device_data = {
                "id": device.id,
                "name": device.name,
                "serial_number": device.serial_number,
                "status": "Online" if device.is_online else "Offline",
                "nodes": []
            }
            for node in device.nodes:
                last_val = Telemetry.query.filter_by(node_id=node.id).order_by(Telemetry.time.desc()).first()
                device_data["nodes"].append({
                    "id": node.id,
                    "name": node.name,
                    "type": node.node_type,
                    "last_value": last_val.value if last_val else None,
                    "last_key": last_val.key if last_val else None,
                    "last_time": last_val.time.isoformat() if last_val else None,
                })
            site_data["devices"].append(device_data)
        response_data["sites"].append(site_data)

    return jsonify(response_data)

@main.route('/test-db', methods=['GET'])
def test_db_connection():
    """
    Veritabanı bağlantısını doğrula.
    ---
    tags:
      - Sağlık
    responses:
      200:
        description: TimescaleDB bağlantısı aktif
    """
    from sqlalchemy import text

    try:
        db.session.execute(text('SELECT 1'))
        return jsonify({"status": "ok", "message": "TimescaleDB bağlantısı aktif"})
    except Exception as exc:  # pragma: no cover - basit sağlık uç noktası
        return jsonify({"status": "error", "message": str(exc)}), 500


# ===========================================
# PROTECTED ENDPOINTS (Token gerekli)
# ===========================================

# --- KULLANICI PROFİLİ ---
@main.route('/api/me', methods=['GET'])
@requires_auth
def get_my_profile():
    """
    Token'daki kullanıcının profil bilgisini döner.
    ---
    tags:
      - Kullanıcı
    security:
      - bearerAuth: []
    responses:
      200:
        description: Kullanıcı profili
    """
    user = get_or_create_user()
    if not user:
        return jsonify({"error": "Kullanıcı bulunamadı"}), 401

    return jsonify({
        "id": user.id,
        "auth0_id": user.auth0_id,
        "email": user.email,
        "full_name": user.full_name,
        "role": user.role,
    })

# --- SITE (SAHA) YÖNETİMİ ---
@main.route('/api/sites', methods=['GET'])
@requires_auth
def get_my_sites():
    """
    Oturumdaki kullanıcının sahalarını listele (pagination + filtreleme).
    ---
    tags:
      - Saha
    security:
      - bearerAuth: []
    parameters:
      - in: query
        name: page
        schema:
          type: integer
          default: 1
      - in: query
        name: pageSize
        schema:
          type: integer
          default: 20
      - in: query
        name: search
        schema:
          type: string
        description: İsim veya şehir içinde arama
      - in: query
        name: sortBy
        schema:
          type: string
          enum: [id, name, city, created_at]
          default: id
      - in: query
        name: sortOrder
        schema:
          type: string
          enum: [asc, desc]
          default: asc
    responses:
      200:
        description: Kullanıcının sahaları (paginated)
    """
    user = get_or_create_user()
    if not user:
        return jsonify({"error": "Kullanıcı bulunamadı"}), 401

    page, page_size = get_pagination_params()
    filters = get_filter_params()

    # Base query
    query = Site.query.filter_by(user_id=user.id)

    # Search filter
    if filters["search"]:
        search_term = f"%{filters['search']}%"
        query = query.filter(
            db.or_(
                Site.name.ilike(search_term),
                Site.city.ilike(search_term),
            )
        )

    # Sorting
    allowed_sort = ["id", "name", "city", "created_at"]
    query = apply_sorting(query, Site, filters["sort_by"], filters["sort_order"], allowed_sort)

    # Total count (before pagination)
    total = query.count()

    # Pagination
    sites_page = query.offset((page - 1) * page_size).limit(page_size).all()

    items = [{
        "id": s.id,
        "name": s.name,
        "city": s.city,
        "location": s.location,
        "latitude": s.latitude,
        "longitude": s.longitude,
        "created_at": s.created_at.isoformat() if s.created_at else None,
        "device_count": len(s.devices),
    } for s in sites_page]

    return jsonify(paginate_response(items, total, page, page_size))


@main.route('/api/sites', methods=['POST'])
@requires_auth
def create_site():
    """
    Yeni saha oluştur (tipli ve boyutlu).
    ---
    tags:
      - Saha
    consumes:
      - application/json
    parameters:
      - in: body
        name: site
        schema:
          type: object
          properties:
            name:
              type: string
              example: Bafra Serası
            site_type:
              type: string
              enum: [GREENHOUSE, FIELD, SOLAR_PLANT, FACTORY, WAREHOUSE, OTHER]
              example: GREENHOUSE
            dimensions:
              type: object
              example: {"rows": 10, "columns": 5, "width_m": 100}
            city:
              type: string
              example: Samsun
            district:
              type: string
              example: Bafra
            location:
              type: string
              example: 41.12, 36.11
            latitude:
              type: number
              example: 41.12
            longitude:
              type: number
              example: 36.11
    responses:
      201:
        description: Saha başarıyla oluşturuldu
      400:
        description: Validasyon hatası
    """
    user = get_or_create_user()
    if not user:
        return jsonify({"error": "Kullanıcı bulunamadı"}), 401

    try:
        site = create_site_logic(user.id, request.json)
        return jsonify({
            "message": "Saha oluşturuldu",
            "site_id": site.id,
            "site": site.to_dict()
        }), 201
    except ValueError as e:
        return jsonify({"error": str(e)}), 400

@main.route('/api/sites/<int:site_id>', methods=['GET'])
@requires_auth
def get_site_detail(site_id):
    """
    Tek bir sahayı detaylarıyla getir.
    ---
    tags:
      - Saha
    parameters:
      - in: path
        name: site_id
        required: true
        schema:
          type: integer
    responses:
      200:
        description: Saha detayları
    """
    user = get_or_create_user()
    if not user:
        return jsonify({"error": "Kullanıcı bulunamadı"}), 401

    site = Site.query.filter_by(id=site_id, user_id=user.id).first()
    if not site:
        return jsonify({"error": "Saha bulunamadı"}), 404

    site_payload = {
        "id": site.id,
        "name": site.name,
        "city": site.city,
        "location": site.location,
        "latitude": site.latitude,
        "longitude": site.longitude,
        "created_at": site.created_at.isoformat() if site.created_at else None,
        "device_count": len(site.devices),
        "devices": [
            {
                "id": d.id,
                "name": d.name,
                "serial_number": d.serial_number,
                "model": d.model,
                "firmware_version": d.firmware_version,
                "is_online": d.is_online,
                "last_seen": d.last_seen.isoformat() if d.last_seen else None,
                "node_count": len(d.nodes),
            }
            for d in site.devices
        ],
    }

    return jsonify(site_payload)


@main.route('/api/sites/<int:site_id>', methods=['PUT'])
@requires_auth
def update_site(site_id):
    """
    Bir sahayı güncelle.
    ---
    tags:
      - Saha
    parameters:
      - in: path
        name: site_id
        required: true
        schema:
          type: integer
    responses:
      200:
        description: Saha güncellendi
    """
    user = get_or_create_user()
    if not user:
        return jsonify({"error": "Kullanıcı bulunamadı"}), 401

    try:
        updated_site = update_site_logic(user.id, site_id, request.json or {})
        return jsonify({
            "message": "Saha güncellendi",
            "site": updated_site.to_dict()
        })
    except ValueError as e:
        return jsonify({"error": str(e)}), 404


@main.route('/api/nodes/<int:node_id>', methods=['PUT'])
@requires_auth
def update_node(node_id):
    """
    Bir node'un bilgilerini güncelle.

    ---
    tags:
      - Node
    parameters:
      - in: path
        name: node_id
        required: true
        schema:
          type: integer
      - in: body
        name: payload
        schema:
          type: object
          properties:
            name:
              type: string
            node_type:
              type: string
            protocol:
              type: string
            node_address:
              type: string
            battery_level:
              type: number
            signal_strength:
              type: number
            brand:
              type: string
            model_number:
              type: string
            capacity_info:
              type: object
            configuration:
              type: object
            last_seen:
              type: string
              example: 2025-01-01T12:00:00Z
    responses:
      200:
        description: Node güncellendi
    """
    user = get_or_create_user()
    if not user:
        return jsonify({"error": "Kullanıcı bulunamadı"}), 401

    try:
        node = update_node_logic(user.id, node_id, request.json or {})
        return jsonify({
            "message": "Node güncellendi",
            "node": node.to_dict()
        })
    except ValueError as e:
        return jsonify({"error": str(e)}), 404


@main.route('/api/nodes/<int:node_id>', methods=['DELETE'])
@requires_auth
def delete_node(node_id):
    """
    Bir node'u sil.
    ---
    tags:
      - Node
    parameters:
      - in: path
        name: node_id
        required: true
        schema:
          type: integer
    responses:
      200:
        description: Node silindi
    """
    user = get_or_create_user()
    node = Node.query.join(Device).join(Site).filter(
        Node.id == node_id,
        Site.user_id == user.id,
    ).first()

    if not node:
        return jsonify({"error": "Node bulunamadı"}), 404

    db.session.delete(node)
    db.session.commit()

    return jsonify({"message": "Node silindi"})
    """
    Bir node'a komut gönder.
    ---
    tags:
      - Komut
    consumes:
      - application/json
    parameters:
      - in: body
        name: command
        schema:
          type: object
          properties:
            node_id:
              type: integer
            command_type:
              type: string
              example: SET_POWER
            payload:
              type: object
              example: {"state": "ON"}
    responses:
      201:
        description: Komut eklendi
    """
    user = get_or_create_user()
    data = request.json

    # Node kullanıcıya ait mi kontrol et
    node = Node.query.join(Device).join(Site).filter(
        Node.id == data.get("node_id"),
        Site.user_id == user.id
    ).first()

    if not node:
        return jsonify({"error": "Node bulunamadı"}), 404

    command = Command(
        node_id=node.id,
        user_id=user.id,
        command_type=data.get("command_type", "SET_STATE"),
        payload=data.get("payload"),
        status="PENDING",
    )
    db.session.add(command)
    db.session.commit()

    return jsonify({"message": "Komut gönderildi", "command_id": command.id}), 201

@main.route('/api/commands/<int:device_id>', methods=['GET'])
@requires_auth
def get_command_history(device_id):
    """
    Bir cihazın komut geçmişini getir.
    ---
    tags:
      - Komut
    parameters:
      - in: path
        name: device_id
        required: true
        schema:
          type: integer
    responses:
      200:
        description: Komut geçmişi döner
    """
    user = get_or_create_user()
    if not user:
        return jsonify({"error": "Kullanıcı bulunamadı"}), 401

    device = Device.query.join(Site).filter(
        Device.id == device_id,
        Site.user_id == user.id,
    ).first()

    if not device:
        return jsonify({"error": "Cihaz bulunamadı"}), 404

    commands = (
        Command.query.join(Node)
        .filter(Node.device_id == device_id)
        .order_by(Command.created_at.desc())
        .limit(200)
        .all()
    )

    return jsonify([
        {
            "id": cmd.id,
            "node_id": cmd.node_id,
            "command_type": cmd.command_type,
            "payload": cmd.payload,
            "status": cmd.status,
            "created_at": cmd.created_at.isoformat() if cmd.created_at else None,
            "executed_at": cmd.executed_at.isoformat() if cmd.executed_at else None,
        }
        for cmd in commands
    ])


# ===========================================
# ENUM ENDPOINT'LERİ (Frontend için seçenekler)
# ===========================================

@main.route('/api/enums/site-types', methods=['GET'])
def get_site_type_options():
    """
    Mevcut saha tiplerini listele.
    ---
    tags:
      - Enum
    responses:
      200:
        description: Saha tipleri listesi
    """
    return jsonify(get_site_types())


@main.route('/api/enums/device-statuses', methods=['GET'])
def get_device_status_options():
    """
    Mevcut cihaz durumlarını listele.
    ---
    tags:
      - Enum
    responses:
      200:
        description: Cihaz durumları listesi
    """
    return jsonify(get_device_statuses())


@main.route('/api/enums/node-protocols', methods=['GET'])
def get_node_protocol_options():
    """
    Mevcut node protokollerini listele.
    ---
    tags:
      - Enum
    responses:
      200:
        description: Node protokolleri listesi
    """
    return jsonify(get_node_protocols())


@main.route('/api/enums/asset-types', methods=['GET'])
def get_asset_type_options():
    """
    Mevcut asset tiplerini listele.
    ---
    tags:
      - Enum
    responses:
      200:
        description: Asset tipleri listesi
    """
    return jsonify(get_asset_types())


@main.route('/api/enums/asset-categories', methods=['GET'])
def get_asset_category_options():
    """
    Mevcut asset kategorilerini listele.
    ---
    tags:
      - Enum
    responses:
      200:
        description: Asset kategorileri listesi
    """
    return jsonify(get_asset_categories())


@main.route('/api/enums', methods=['GET'])
def get_all_enums():
    """
    Tüm enum değerlerini tek seferde getir.
    ---
    tags:
      - Enum
    responses:
      200:
        description: Tüm enum değerleri
    """
    return jsonify({
        "site_types": get_site_types(),
        "device_statuses": get_device_statuses(),
        "node_protocols": get_node_protocols(),
        "asset_types": get_asset_types(),
        "asset_categories": get_asset_categories(),
    })


# ===========================================
# ASSET (INVENTORY) YÖNETİMİ
# ===========================================

@main.route('/api/assets', methods=['GET'])
@requires_auth
def get_all_assets():
    """
    Kullanıcının tüm asset'lerini getir (pagination + filtreleme).
    ---
    tags:
      - Asset
    security:
      - bearerAuth: []
    parameters:
      - in: query
        name: page
        schema:
          type: integer
          default: 1
      - in: query
        name: pageSize
        schema:
          type: integer
          default: 20
      - in: query
        name: search
        schema:
          type: string
        description: İsim veya variable_name içinde arama
      - in: query
        name: asset_type
        schema:
          type: string
        description: Asset tipine göre filtrele (SENSOR, ACTUATOR, vb.)
      - in: query
        name: category
        schema:
          type: string
        description: Kategoriye göre filtrele (TEMPERATURE, HUMIDITY, vb.)
    responses:
      200:
        description: Asset listesi (paginated)
    """
    user = get_or_create_user()
    if not user:
        return jsonify({"error": "Kullanıcı bulunamadı"}), 401

    page, page_size = get_pagination_params()
    filters = get_filter_params()

    # Kullanıcının site ID'lerini al
    user_site_ids = [s.id for s in user.sites]

    # Base query - Asset -> Node -> Device -> Site zinciri
    query = (
        Asset.query
        .join(Node)
        .join(Device)
        .filter(Device.site_id.in_(user_site_ids))
    )

    # Search filter
    if filters["search"]:
        search_term = f"%{filters['search']}%"
        query = query.filter(
            db.or_(
                Asset.name.ilike(search_term),
                Asset.variable_name.ilike(search_term),
            )
        )

    # Asset type filter
    asset_type = request.args.get("asset_type")
    if asset_type:
        query = query.filter(Asset.asset_type == asset_type)

    # Category filter
    category = request.args.get("category")
    if category:
        query = query.filter(Asset.category == category)

    # Sorting
    allowed_sort = ["id", "name", "asset_type", "category", "created_at"]
    query = apply_sorting(query, Asset, filters["sort_by"], filters["sort_order"], allowed_sort)

    # Total count
    total = query.count()

    # Pagination
    assets_page = query.offset((page - 1) * page_size).limit(page_size).all()

    items = []
    for asset in assets_page:
        asset_dict = asset.to_dict()
        asset_dict["node_name"] = asset.node.name
        asset_dict["device_name"] = asset.node.device.name
        asset_dict["device_serial"] = asset.node.device.serial_number
        asset_dict["site_name"] = asset.node.device.site.name
        items.append(asset_dict)

    return jsonify(paginate_response(items, total, page, page_size))


@main.route('/api/assets', methods=['POST'])
@requires_auth
def create_asset():
    """
    Bir Node'a yeni asset (sensör/vana) tanımla.
    ---
    tags:
      - Asset
    consumes:
      - application/json
    parameters:
      - in: body
        name: asset
        schema:
          type: object
          required:
            - node_id
            - name
            - variable_name
          properties:
            node_id:
              type: integer
              example: 1
            name:
              type: string
              example: Domates Nem Sensörü
            description:
              type: string
              example: Sıra 1'deki toprak nem sensörü
            asset_type:
              type: string
              enum: [SENSOR, ACTUATOR, METER, CONTROLLER]
              example: SENSOR
            category:
              type: string
              example: SOIL_MOISTURE
            variable_name:
              type: string
              example: soil_moisture_1
            port_number:
              type: integer
              example: 1
            unit:
              type: string
              example: "%"
            min_value:
              type: number
              example: 0
            max_value:
              type: number
              example: 100
            calibration_offset:
              type: number
              example: 0
            position:
              type: object
              example: {"row": 1, "column": 3}
            configuration:
              type: object
              example: {"alarm_low": 20, "alarm_high": 80}
    responses:
      201:
        description: Asset oluşturuldu
      400:
        description: Validasyon hatası
    """
    user = get_or_create_user()
    if not user:
        return jsonify({"error": "Kullanıcı bulunamadı"}), 401

    try:
        asset = create_asset_logic(user.id, request.json)
        return jsonify({
            "message": "Asset oluşturuldu",
            "asset_id": asset.id,
            "asset": asset.to_dict()
        }), 201
    except ValueError as e:
        return jsonify({"error": str(e)}), 400


@main.route('/api/assets/<int:asset_id>', methods=['GET'])
@requires_auth
def get_asset_detail(asset_id):
    """
    Tek bir asset'in detaylarını getir.
    ---
    tags:
      - Asset
    parameters:
      - in: path
        name: asset_id
        required: true
        schema:
          type: integer
    responses:
      200:
        description: Asset detayları
      404:
        description: Asset bulunamadı
    """
    user = get_or_create_user()
    if not user:
        return jsonify({"error": "Kullanıcı bulunamadı"}), 401

    asset = (
        Asset.query
        .join(Node)
        .join(Device)
        .join(Site)
        .filter(Asset.id == asset_id, Site.user_id == user.id)
        .first()
    )

    if not asset:
        return jsonify({"error": "Asset bulunamadı"}), 404

    asset_dict = asset.to_dict()
    asset_dict["node_name"] = asset.node.name
    asset_dict["device_name"] = asset.node.device.name
    asset_dict["device_serial"] = asset.node.device.serial_number
    asset_dict["site_name"] = asset.node.device.site.name
    asset_dict["site_id"] = asset.node.device.site.id

    return jsonify(asset_dict)


@main.route('/api/assets/<int:asset_id>', methods=['PUT'])
@requires_auth
def update_asset(asset_id):
    """
    Asset bilgilerini güncelle.
    ---
    tags:
      - Asset
    parameters:
      - in: path
        name: asset_id
        required: true
        schema:
          type: integer
      - in: body
        name: payload
        schema:
          type: object
          properties:
            name:
              type: string
            description:
              type: string
            asset_type:
              type: string
            category:
              type: string
            variable_name:
              type: string
            unit:
              type: string
            min_value:
              type: number
            max_value:
              type: number
            calibration_offset:
              type: number
            position:
              type: object
            configuration:
              type: object
            is_active:
              type: boolean
    responses:
      200:
        description: Asset güncellendi
      404:
        description: Asset bulunamadı
    """
    user = get_or_create_user()
    if not user:
        return jsonify({"error": "Kullanıcı bulunamadı"}), 401

    try:
        asset = update_asset_logic(user.id, asset_id, request.json)
        return jsonify({
            "message": "Asset güncellendi",
            "asset": asset.to_dict()
        })
    except ValueError as e:
        return jsonify({"error": str(e)}), 404


@main.route('/api/assets/<int:asset_id>', methods=['DELETE'])
@requires_auth
def delete_asset(asset_id):
    """
    Asset'i sil.
    ---
    tags:
      - Asset
    parameters:
      - in: path
        name: asset_id
        required: true
        schema:
          type: integer
    responses:
      200:
        description: Asset silindi
      404:
        description: Asset bulunamadı
    """
    user = get_or_create_user()
    if not user:
        return jsonify({"error": "Kullanıcı bulunamadı"}), 401

    try:
        delete_asset_logic(user.id, asset_id)
        return jsonify({"message": "Asset silindi"})
    except ValueError as e:
        return jsonify({"error": str(e)}), 404


@main.route('/api/nodes/<int:node_id>/assets', methods=['GET'])
@requires_auth
def get_node_assets(node_id):
    """
    Bir Node'a ait tüm asset'leri listele.
    ---
    tags:
      - Asset
    parameters:
      - in: path
        name: node_id
        required: true
        schema:
          type: integer
    responses:
      200:
        description: Node'a ait asset listesi
      404:
        description: Node bulunamadı
    """
    user = get_or_create_user()
    if not user:
        return jsonify({"error": "Kullanıcı bulunamadı"}), 401

    try:
        assets = get_assets_by_node(user.id, node_id)
        return jsonify([asset.to_dict() for asset in assets])
    except ValueError as e:
        return jsonify({"error": str(e)}), 404


@main.route('/api/sites/<int:site_id>/assets', methods=['GET'])
@requires_auth
def get_site_assets(site_id):
    """
    Bir Site'a ait tüm asset'leri listele (hiyerarşik bilgiyle).
    ---
    tags:
      - Asset
    parameters:
      - in: path
        name: site_id
        required: true
        schema:
          type: integer
    responses:
      200:
        description: Site'a ait asset listesi
      404:
        description: Site bulunamadı
    """
    user = get_or_create_user()
    if not user:
        return jsonify({"error": "Kullanıcı bulunamadı"}), 401

    try:
        assets = get_assets_by_site(user.id, site_id)
        return jsonify(assets)
    except ValueError as e:
        return jsonify({"error": str(e)}), 404


@main.route('/api/sites/<int:site_id>/hierarchy', methods=['GET'])
@requires_auth
def get_site_full_hierarchy(site_id):
    """
    Site'ın tam hiyerarşisini getir (Device -> Node -> Asset).
    ---
    tags:
      - Saha
    parameters:
      - in: path
        name: site_id
        required: true
        schema:
          type: integer
    responses:
      200:
        description: Site hiyerarşisi
      404:
        description: Site bulunamadı
    """
    user = get_or_create_user()
    if not user:
        return jsonify({"error": "Kullanıcı bulunamadı"}), 401

    try:
        hierarchy = get_site_hierarchy(user.id, site_id)
        return jsonify(hierarchy)
    except ValueError as e:
        return jsonify({"error": str(e)}), 404


# ===========================================
# VPP ENUM ENDPOINT'LERİ
# ===========================================

@main.route('/api/enums/node-types', methods=['GET'])
def get_node_type_options():
    """Node tiplerini listele."""
    return jsonify(get_node_types())


@main.route('/api/enums/inverter-brands', methods=['GET'])
def get_inverter_brand_options():
    """Inverter markalarını listele."""
    return jsonify(get_inverter_brands())


@main.route('/api/enums/tariff-types', methods=['GET'])
def get_tariff_type_options():
    """Tarife tiplerini listele."""
    return jsonify(get_tariff_types())


@main.route('/api/enums/vpp-triggers', methods=['GET'])
def get_vpp_trigger_options():
    """VPP tetikleyici tiplerini listele."""
    return jsonify(get_vpp_trigger_types())


@main.route('/api/enums/vpp-actions', methods=['GET'])
def get_vpp_action_options():
    """VPP aksiyon tiplerini listele."""
    return jsonify(get_vpp_action_types())


# ===========================================
# TARİFE YÖNETİMİ
# ===========================================

@main.route('/api/tariffs', methods=['GET'])
@requires_auth
def get_tariffs():
    """Kullanıcının tarifelerini listele."""
    user = get_or_create_user()
    if not user:
        return jsonify({"error": "Kullanıcı bulunamadı"}), 401
    
    tariffs = Tariff.query.filter_by(user_id=user.id).order_by(Tariff.created_at.desc()).all()
    return jsonify([t.to_dict() for t in tariffs])


@main.route('/api/tariffs', methods=['POST'])
@requires_auth
def create_tariff():
    """
    Yeni tarife oluştur.
    ---
    tags:
      - Tarife
    parameters:
      - in: body
        name: tariff
        schema:
          type: object
          required:
            - name
            - periods
          properties:
            name:
              type: string
              example: Sanayi AG - 3 Zamanlı
            tariff_type:
              type: string
              enum: [SINGLE_TIME, THREE_TIME, HOURLY]
            periods:
              type: object
              example: {"T1": {"start": "06:00", "end": "17:00", "price": 2.50}}
    responses:
      201:
        description: Tarife oluşturuldu
    """
    user = get_or_create_user()
    if not user:
        return jsonify({"error": "Kullanıcı bulunamadı"}), 401
    
    try:
        tariff = create_tariff_logic(user.id, request.json)
        return jsonify({
            "message": "Tarife oluşturuldu",
            "tariff": tariff.to_dict()
        }), 201
    except ValueError as e:
        return jsonify({"error": str(e)}), 400


@main.route('/api/tariffs/<int:tariff_id>', methods=['GET'])
@requires_auth
def get_tariff_detail(tariff_id):
    """Tarife detayını getir."""
    user = get_or_create_user()
    if not user:
        return jsonify({"error": "Kullanıcı bulunamadı"}), 401
    
    tariff = Tariff.query.filter_by(id=tariff_id, user_id=user.id).first()
    if not tariff:
        return jsonify({"error": "Tarife bulunamadı"}), 404
    
    return jsonify(tariff.to_dict())


@main.route('/api/tariffs/<int:tariff_id>', methods=['PUT'])
@requires_auth
def update_tariff(tariff_id):
    """Tarife güncelle."""
    user = get_or_create_user()
    if not user:
        return jsonify({"error": "Kullanıcı bulunamadı"}), 401
    
    try:
        tariff = update_tariff_logic(user.id, tariff_id, request.json)
        return jsonify({
            "message": "Tarife güncellendi",
            "tariff": tariff.to_dict()
        })
    except ValueError as e:
        return jsonify({"error": str(e)}), 404


@main.route('/api/tariffs/<int:tariff_id>', methods=['DELETE'])
@requires_auth
def delete_tariff(tariff_id):
    """Tarife sil."""
    user = get_or_create_user()
    if not user:
        return jsonify({"error": "Kullanıcı bulunamadı"}), 401
    
    try:
        delete_tariff_logic(user.id, tariff_id)
        return jsonify({"message": "Tarife silindi"})
    except ValueError as e:
        return jsonify({"error": str(e)}), 404


@main.route('/api/tariffs/<int:tariff_id>/current-price', methods=['GET'])
@requires_auth
def get_tariff_current_price(tariff_id):
    """Tarifenin şu anki fiyatını hesapla."""
    user = get_or_create_user()
    if not user:
        return jsonify({"error": "Kullanıcı bulunamadı"}), 401
    
    try:
        price_info = get_current_tariff_price(user.id, tariff_id)
        return jsonify(price_info)
    except ValueError as e:
        return jsonify({"error": str(e)}), 404


# ===========================================
# ENERJİ PİYASASI FİYATLARI (EPİAŞ)
# ===========================================

@main.route('/api/market-prices', methods=['GET'])
@requires_auth
def get_market_prices():
    """
    Belirli bir gün için piyasa fiyatlarını getir.
    Query params: date (YYYY-MM-DD)
    """
    user = get_or_create_user()
    if not user:
        return jsonify({"error": "Kullanıcı bulunamadı"}), 401
    
    date_str = request.args.get("date")
    if date_str:
        try:
            from datetime import date
            target_date = datetime.strptime(date_str, "%Y-%m-%d").date()
        except ValueError:
            return jsonify({"error": "Geçersiz tarih formatı (YYYY-MM-DD)"}), 400
    else:
        from datetime import date
        target_date = date.today()
    
    prices = get_market_prices_for_date(target_date)
    return jsonify({
        "date": target_date.isoformat(),
        "prices": prices
    })


@main.route('/api/market-prices/current', methods=['GET'])
@requires_auth
def get_current_price():
    """Şu anki saatin piyasa fiyatını getir."""
    user = get_or_create_user()
    if not user:
        return jsonify({"error": "Kullanıcı bulunamadı"}), 401
    
    price = get_current_market_price()
    if not price:
        return jsonify({"error": "Bu saat için fiyat bulunamadı"}), 404
    
    return jsonify(price)


@main.route('/api/market-prices', methods=['POST'])
@requires_auth
def import_market_prices():
    """
    EPİAŞ fiyatlarını içe aktar (Admin/Cron job için).
    Body: {"prices": [{"date": "2024-01-15", "hour": 17, "ptf": 4500.5, "smf": 4600.2}, ...]}
    """
    user = get_or_create_user()
    if not user:
        return jsonify({"error": "Kullanıcı bulunamadı"}), 401
    
    # TODO: Admin kontrolü eklenebilir
    data = request.json
    prices = data.get("prices", [])
    
    if not prices:
        return jsonify({"error": "Fiyat verisi bulunamadı"}), 400
    
    saved_count = save_market_prices(prices)
    return jsonify({
        "message": f"{saved_count} yeni fiyat kaydedildi",
        "total_processed": len(prices)
    }), 201


# ===========================================
# VPP KURAL YÖNETİMİ
# ===========================================

@main.route('/api/vpp/rules', methods=['GET'])
@requires_auth
def get_vpp_rules():
    """Kullanıcının tüm VPP kurallarını listele."""
    user = get_or_create_user()
    if not user:
        return jsonify({"error": "Kullanıcı bulunamadı"}), 401
    
    rules = VppRule.query.filter_by(user_id=user.id).order_by(VppRule.priority).all()
    return jsonify([r.to_dict() for r in rules])


@main.route('/api/vpp/rules', methods=['POST'])
@requires_auth
def create_vpp_rule():
    """
    Yeni VPP kuralı oluştur.
    ---
    tags:
      - VPP
    parameters:
      - in: body
        name: rule
        schema:
          type: object
          required:
            - node_id
            - name
            - trigger
            - action
          properties:
            node_id:
              type: integer
              example: 1
            name:
              type: string
              example: Puant Saatinde Deşarj Et
            trigger:
              type: object
              example: {"type": "TIME_RANGE", "start": "17:00", "end": "22:00"}
            action:
              type: object
              example: {"type": "DISCHARGE_BATTERY", "power_limit_kw": 50}
    responses:
      201:
        description: Kural oluşturuldu
    """
    user = get_or_create_user()
    if not user:
        return jsonify({"error": "Kullanıcı bulunamadı"}), 401
    
    try:
        rule = create_vpp_rule_logic(user.id, request.json)
        return jsonify({
            "message": "VPP kuralı oluşturuldu",
            "rule": rule.to_dict()
        }), 201
    except ValueError as e:
        return jsonify({"error": str(e)}), 400


@main.route('/api/vpp/rules/<int:rule_id>', methods=['GET'])
@requires_auth
def get_vpp_rule_detail(rule_id):
    """VPP kuralı detayını getir."""
    user = get_or_create_user()
    if not user:
        return jsonify({"error": "Kullanıcı bulunamadı"}), 401
    
    rule = VppRule.query.filter_by(id=rule_id, user_id=user.id).first()
    if not rule:
        return jsonify({"error": "Kural bulunamadı"}), 404
    
    return jsonify(rule.to_dict())


@main.route('/api/vpp/rules/<int:rule_id>', methods=['PUT'])
@requires_auth
def update_vpp_rule(rule_id):
    """VPP kuralını güncelle."""
    user = get_or_create_user()
    if not user:
        return jsonify({"error": "Kullanıcı bulunamadı"}), 401
    
    try:
        rule = update_vpp_rule_logic(user.id, rule_id, request.json)
        return jsonify({
            "message": "VPP kuralı güncellendi",
            "rule": rule.to_dict()
        })
    except ValueError as e:
        return jsonify({"error": str(e)}), 404


@main.route('/api/vpp/rules/<int:rule_id>', methods=['DELETE'])
@requires_auth
def delete_vpp_rule(rule_id):
    """VPP kuralını sil."""
    user = get_or_create_user()
    if not user:
        return jsonify({"error": "Kullanıcı bulunamadı"}), 401
    
    try:
        delete_vpp_rule_logic(user.id, rule_id)
        return jsonify({"message": "VPP kuralı silindi"})
    except ValueError as e:
        return jsonify({"error": str(e)}), 404


@main.route('/api/vpp/rules/<int:rule_id>/logs', methods=['GET'])
@requires_auth
def get_rule_logs(rule_id):
    """VPP kuralının çalışma geçmişini getir."""
    user = get_or_create_user()
    if not user:
        return jsonify({"error": "Kullanıcı bulunamadı"}), 401
    
    limit = request.args.get("limit", 50, type=int)
    
    try:
        logs = get_vpp_rule_logs(user.id, rule_id, limit)
        return jsonify(logs)
    except ValueError as e:
        return jsonify({"error": str(e)}), 404


@main.route('/api/nodes/<int:node_id>/vpp-rules', methods=['GET'])
@requires_auth
def get_node_vpp_rules(node_id):
    """Bir Node'a ait VPP kurallarını listele."""
    user = get_or_create_user()
    if not user:
        return jsonify({"error": "Kullanıcı bulunamadı"}), 401
    
    try:
        rules = get_vpp_rules_for_node(user.id, node_id)
        return jsonify([r.to_dict() for r in rules])
    except ValueError as e:
        return jsonify({"error": str(e)}), 404


# ===========================================
# INVERTER VE VPP DASHBOARD
# ===========================================

@main.route('/api/vpp/inverters', methods=['GET'])
@requires_auth
def get_user_inverters():
    """Kullanıcının tüm inverter'larını listele."""
    user = get_or_create_user()
    if not user:
        return jsonify({"error": "Kullanıcı bulunamadı"}), 401
    
    inverters = get_inverters_for_user(user.id)
    return jsonify([
        {
            **inv.to_dict(),
            "site_name": inv.device.site.name,
            "device_name": inv.device.name,
            "device_status": inv.device.status,
        }
        for inv in inverters
    ])


@main.route('/api/vpp/summary', methods=['GET'])
@requires_auth
def get_vpp_summary():
    """
    VPP Dashboard özeti - Toplam kapasite, online inverter sayısı vb.
    """
    user = get_or_create_user()
    if not user:
        return jsonify({"error": "Kullanıcı bulunamadı"}), 401
    
    summary = get_inverter_summary(user.id)
    
    # Aktif kural sayısını ekle
    active_rules = VppRule.query.filter_by(user_id=user.id, is_active=True).count()
    summary["active_rules"] = active_rules
    
    # Bugünkü kural tetiklenme sayısını ekle
    from datetime import date
    today = date.today()
    # TODO: Bugünkü tetiklenme sayısı için VppRuleLog sorgusu
    
    return jsonify(summary)


# ===========================================
# AUTO-DISCOVERY (Otomatik Keşif) YÖNETİMİ
# ===========================================

@main.route('/api/discovery/pending', methods=['GET'])
@requires_auth
def get_pending_discoveries():
    """
    Kullanıcının Gateway'leri tarafından bulunan ama henüz eklenmemiş cihazları getir.
    ---
    tags:
      - Discovery
    security:
      - bearerAuth: []
    responses:
      200:
        description: Bekleyen keşifler listesi
    """
    user = get_or_create_user()
    if not user:
        return jsonify({"error": "Kullanıcı bulunamadı"}), 401
    
    # Kullanıcının tüm gateway'lerini bul
    user_gateways = Device.query.join(Site).filter(Site.user_id == user.id).all()
    gateway_ids = [d.id for d in user_gateways]
    
    if not gateway_ids:
        return jsonify([])
    
    # Bu gateway'lerin bulduğu bekleyen cihazları getir
    pending = (
        DiscoveryQueue.query
        .filter(
            DiscoveryQueue.reported_by_device_id.in_(gateway_ids),
            DiscoveryQueue.status == DiscoveryStatus.PENDING.value
        )
        .order_by(DiscoveryQueue.last_seen_at.desc())
        .all()
    )
    
    return jsonify([d.to_dict() for d in pending])


@main.route('/api/discovery/claim', methods=['POST'])
@requires_auth
def claim_discovered_device():
    """
    Keşfedilen bir cihazı "Gerçek Node" olarak kaydet (Sahiplen).
    ---
    tags:
      - Discovery
    security:
      - bearerAuth: []
    consumes:
      - application/json
    parameters:
      - in: body
        name: payload
        schema:
          type: object
          required:
            - discovery_id
            - name
          properties:
            discovery_id:
              type: integer
              description: Keşif kaydının ID'si
            name:
              type: string
              description: Cihaza verilecek isim
            node_type:
              type: string
              description: Cihaz tipi (SENSOR_NODE, INVERTER, vb.)
            protocol:
              type: string
              description: Haberleşme protokolü
    responses:
      201:
        description: Cihaz başarıyla eklendi
      404:
        description: Keşif bulunamadı
      403:
        description: Yetkisiz işlem
    """
    user = get_or_create_user()
    if not user:
        return jsonify({"error": "Kullanıcı bulunamadı"}), 401
    
    data = request.json or {}
    discovery_id = data.get("discovery_id")
    name = data.get("name", "").strip()
    
    if not discovery_id:
        return jsonify({"error": "discovery_id zorunludur"}), 400
    
    if not name:
        return jsonify({"error": "Cihaz adı zorunludur"}), 400
    
    # 1. Keşif kaydını bul
    discovery = DiscoveryQueue.query.get(discovery_id)
    if not discovery:
        return jsonify({"error": "Keşif kaydı bulunamadı"}), 404
    
    # 2. Yetki kontrolü (Bu keşfi yapan gateway benim mi?)
    gateway = discovery.reporter
    if not gateway or not gateway.site or gateway.site.user_id != user.id:
        return jsonify({"error": "Bu cihazı ekleme yetkiniz yok"}), 403
    
    # 3. Zaten sahiplenilmiş mi?
    if discovery.status != DiscoveryStatus.PENDING.value:
        return jsonify({"error": f"Bu cihaz zaten işlenmiş (durum: {discovery.status})"}), 400
    
    # 4. Node tablosuna terfi ettir
    node_type = data.get("node_type") or discovery.guessed_type or "SENSOR_NODE"
    protocol = data.get("protocol") or discovery.protocol or "UNKNOWN"
    
    new_node = Node(
        device_id=gateway.id,
        name=name,
        node_address=discovery.device_identifier,
        node_type=node_type,
        protocol=protocol,
        brand=discovery.guessed_brand,
        model_number=discovery.guessed_model,
        configuration=discovery.raw_data or {},
    )
    db.session.add(new_node)
    
    # 5. Keşif durumunu güncelle
    discovery.status = DiscoveryStatus.CLAIMED.value
    
    db.session.commit()
    
    return jsonify({
        "message": "Cihaz başarıyla eklendi",
        "node": new_node.to_dict(),
        "gateway": {
            "id": gateway.id,
            "name": gateway.name,
            "serial_number": gateway.serial_number,
        }
    }), 201


@main.route('/api/discovery/<int:discovery_id>/ignore', methods=['POST'])
@requires_auth
def ignore_discovered_device(discovery_id):
    """
    Keşfedilen bir cihazı yoksay (Listeden kaldır).
    ---
    tags:
      - Discovery
    security:
      - bearerAuth: []
    parameters:
      - in: path
        name: discovery_id
        required: true
        schema:
          type: integer
    responses:
      200:
        description: Cihaz yoksayıldı
      404:
        description: Keşif bulunamadı
    """
    user = get_or_create_user()
    if not user:
        return jsonify({"error": "Kullanıcı bulunamadı"}), 401
    
    discovery = DiscoveryQueue.query.get(discovery_id)
    if not discovery:
        return jsonify({"error": "Keşif kaydı bulunamadı"}), 404
    
    # Yetki kontrolü
    gateway = discovery.reporter
    if not gateway or not gateway.site or gateway.site.user_id != user.id:
        return jsonify({"error": "Bu işlem için yetkiniz yok"}), 403
    
    discovery.status = DiscoveryStatus.IGNORED.value
    db.session.commit()
    
    return jsonify({"message": "Cihaz yoksayıldı"})


@main.route('/api/discovery/<int:discovery_id>', methods=['DELETE'])
@requires_auth
def delete_discovered_device(discovery_id):
    """
    Keşif kaydını tamamen sil.
    ---
    tags:
      - Discovery
    security:
      - bearerAuth: []
    parameters:
      - in: path
        name: discovery_id
        required: true
        schema:
          type: integer
    responses:
      200:
        description: Keşif silindi
      404:
        description: Keşif bulunamadı
    """
    user = get_or_create_user()
    if not user:
        return jsonify({"error": "Kullanıcı bulunamadı"}), 401
    
    discovery = DiscoveryQueue.query.get(discovery_id)
    if not discovery:
        return jsonify({"error": "Keşif kaydı bulunamadı"}), 404
    
    # Yetki kontrolü
    gateway = discovery.reporter
    if not gateway or not gateway.site or gateway.site.user_id != user.id:
        return jsonify({"error": "Bu işlem için yetkiniz yok"}), 403
    
    db.session.delete(discovery)
    db.session.commit()
    
    return jsonify({"message": "Keşif kaydı silindi"})


@main.route('/api/discovery/stats', methods=['GET'])
@requires_auth
def get_discovery_stats():
    """
    Keşif istatistiklerini getir.
    ---
    tags:
      - Discovery
    security:
      - bearerAuth: []
    responses:
      200:
        description: Keşif istatistikleri
    """
    user = get_or_create_user()
    if not user:
        return jsonify({"error": "Kullanıcı bulunamadı"}), 401
    
    # Kullanıcının gateway'leri
    user_gateways = Device.query.join(Site).filter(Site.user_id == user.id).all()
    gateway_ids = [d.id for d in user_gateways]
    
    if not gateway_ids:
        return jsonify({
            "pending_count": 0,
            "claimed_count": 0,
            "ignored_count": 0,
            "total_gateways": 0,
        })
    
    # İstatistikler
    pending_count = DiscoveryQueue.query.filter(
        DiscoveryQueue.reported_by_device_id.in_(gateway_ids),
        DiscoveryQueue.status == DiscoveryStatus.PENDING.value
    ).count()
    
    claimed_count = DiscoveryQueue.query.filter(
        DiscoveryQueue.reported_by_device_id.in_(gateway_ids),
        DiscoveryQueue.status == DiscoveryStatus.CLAIMED.value
    ).count()
    
    ignored_count = DiscoveryQueue.query.filter(
        DiscoveryQueue.reported_by_device_id.in_(gateway_ids),
        DiscoveryQueue.status == DiscoveryStatus.IGNORED.value
    ).count()
    
    return jsonify({
        "pending_count": pending_count,
        "claimed_count": claimed_count,
        "ignored_count": ignored_count,
        "total_gateways": len(gateway_ids),
    })