"""Tarife yönetimi endpoint'leri."""
from flask import jsonify, request

from . import api_bp
from .helpers import get_or_create_user
from ..models import Tariff
from ..auth import requires_auth
from ..services import (
    create_tariff_logic,
    update_tariff_logic,
    delete_tariff_logic,
    get_current_tariff_price,
)


@api_bp.route('/tariffs', methods=['GET'])
@requires_auth
def get_tariffs():
    """Kullanıcının tarifelerini listele."""
    user = get_or_create_user()
    if not user:
        return jsonify({"error": "Kullanıcı bulunamadı"}), 401

    tariffs = Tariff.query.filter_by(user_id=user.id).order_by(Tariff.created_at.desc()).all()
    return jsonify([t.to_dict() for t in tariffs])


@api_bp.route('/tariffs', methods=['POST'])
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


@api_bp.route('/tariffs/<int:tariff_id>', methods=['GET'])
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


@api_bp.route('/tariffs/<int:tariff_id>', methods=['PUT'])
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


@api_bp.route('/tariffs/<int:tariff_id>', methods=['DELETE'])
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


@api_bp.route('/tariffs/<int:tariff_id>/current-price', methods=['GET'])
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
