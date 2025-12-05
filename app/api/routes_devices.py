"""Device (Cihaz/Gateway) yönetimi endpoint'leri."""
from flask import jsonify, request

from . import api_bp
from .helpers import get_or_create_user, get_pagination_params, paginate_response
from ..models import Device, Site
from ..auth import requires_auth
from ..services import create_device_logic, update_device_logic, delete_device_logic


@api_bp.route('/devices', methods=['GET'])
@requires_auth
def get_devices():
    """
    Kullanıcının tüm cihazlarını (Gateway) listele.
    ---
    tags:
      - Cihaz
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
        name: site_id
        schema:
          type: integer
        description: Belirli bir sahadaki cihazları filtrele
    responses:
      200:
        description: Cihaz listesi
    """
    user = get_or_create_user()
    if not user:
        return jsonify({"error": "Kullanıcı bulunamadı"}), 401

    page, page_size = get_pagination_params()
    site_id = request.args.get('site_id', type=int)

    query = Device.query.join(Site).filter(Site.user_id == user.id)
    if site_id:
        query = query.filter(Device.site_id == site_id)

    total = query.count()
    devices = query.offset((page - 1) * page_size).limit(page_size).all()

    items = [d.to_dict() for d in devices]
    return jsonify(paginate_response(items, total, page, page_size))


@api_bp.route('/devices', methods=['POST'])
@requires_auth
def create_device():
    """
    Yeni cihaz (Gateway) ekle.
    ---
    tags:
      - Cihaz
    consumes:
      - application/json
    parameters:
      - in: body
        name: device
        schema:
          type: object
          required:
            - site_id
            - serial_number
            - name
          properties:
            site_id:
              type: integer
              example: 1
            serial_number:
              type: string
              example: AWX-GW-001
            name:
              type: string
              example: Giriş Panosu
            model:
              type: string
              example: Teltonika RUT956
    responses:
      201:
        description: Cihaz oluşturuldu
      400:
        description: Validasyon hatası
    """
    user = get_or_create_user()
    if not user:
        return jsonify({"error": "Kullanıcı bulunamadı"}), 401

    try:
        device = create_device_logic(user.id, request.json)
        return jsonify({
            "message": "Cihaz oluşturuldu",
            "device": device.to_dict()
        }), 201
    except ValueError as e:
        return jsonify({"error": str(e)}), 400


@api_bp.route('/devices/<int:device_id>', methods=['GET'])
@requires_auth
def get_device_detail(device_id):
    """
    Tek bir cihazın detaylarını getir.
    ---
    tags:
      - Cihaz
    parameters:
      - in: path
        name: device_id
        required: true
        schema:
          type: integer
    responses:
      200:
        description: Cihaz detayları
      404:
        description: Cihaz bulunamadı
    """
    user = get_or_create_user()
    if not user:
        return jsonify({"error": "Kullanıcı bulunamadı"}), 401

    device = Device.query.join(Site).filter(
        Device.id == device_id,
        Site.user_id == user.id
    ).first()

    if not device:
        return jsonify({"error": "Cihaz bulunamadı"}), 404

    return jsonify(device.to_dict(include_nodes=True))


@api_bp.route('/devices/<int:device_id>', methods=['PUT'])
@requires_auth
def update_device(device_id):
    """
    Cihaz bilgilerini güncelle.
    ---
    tags:
      - Cihaz
    parameters:
      - in: path
        name: device_id
        required: true
        schema:
          type: integer
    responses:
      200:
        description: Cihaz güncellendi
      404:
        description: Cihaz bulunamadı
    """
    user = get_or_create_user()
    if not user:
        return jsonify({"error": "Kullanıcı bulunamadı"}), 401

    try:
        device = update_device_logic(user.id, device_id, request.json or {})
        return jsonify({
            "message": "Cihaz güncellendi",
            "device": device.to_dict()
        })
    except ValueError as e:
        return jsonify({"error": str(e)}), 404


@api_bp.route('/devices/<int:device_id>', methods=['DELETE'])
@requires_auth
def delete_device(device_id):
    """
    Cihazı sil.
    ---
    tags:
      - Cihaz
    parameters:
      - in: path
        name: device_id
        required: true
        schema:
          type: integer
    responses:
      200:
        description: Cihaz silindi
      404:
        description: Cihaz bulunamadı
    """
    user = get_or_create_user()
    if not user:
        return jsonify({"error": "Kullanıcı bulunamadı"}), 401

    try:
        delete_device_logic(user.id, device_id)
        return jsonify({"message": "Cihaz silindi"})
    except ValueError as e:
        return jsonify({"error": str(e)}), 404
