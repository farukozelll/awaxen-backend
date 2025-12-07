"""Enerji piyasası fiyatları (EPİAŞ) endpoint'leri."""
from datetime import datetime

from flask import jsonify, request

from . import api_bp
from .helpers import get_or_create_user
from ..auth import requires_auth, requires_role, get_db_user
from ..services import (
    save_market_prices,
    get_market_prices_for_date,
    get_current_market_price,
) 


@api_bp.route('/market-prices', methods=['GET'])
@requires_auth
def get_market_prices():
    """
    Belirli bir gün için piyasa fiyatlarını getir.
    ---
    tags:
      - Market
    security:
      - bearerAuth: []
    parameters:
      - name: date
        in: query
        type: string
        format: date
        example: "2024-01-15"
        description: Tarih (YYYY-MM-DD). Belirtilmezse bugün.
    responses:
      200:
        description: Piyasa fiyatları
        schema:
          type: object
          properties:
            date:
              type: string
              format: date
            prices:
              type: array
              items:
                type: object
                properties:
                  hour:
                    type: integer
                  ptf:
                    type: number
                  smf:
                    type: number
                  currency:
                    type: string
      400:
        description: Geçersiz tarih formatı
      401:
        description: Yetkisiz erişim
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


@api_bp.route('/market-prices/current', methods=['GET'])
@requires_auth
def get_current_price():
    """
    Şu anki saatin piyasa fiyatını getir.
    ---
    tags:
      - Market
    security:
      - bearerAuth: []
    responses:
      200:
        description: Güncel piyasa fiyatı
        schema:
          type: object
          properties:
            hour:
              type: integer
              example: 14
            ptf:
              type: number
              example: 3.45
            smf:
              type: number
              example: 3.52
            currency:
              type: string
              example: TRY/kWh
            date:
              type: string
              format: date
      401:
        description: Yetkisiz erişim
      404:
        description: Bu saat için fiyat bulunamadı
    """
    user = get_or_create_user()
    if not user:
        return jsonify({"error": "Kullanıcı bulunamadı"}), 401

    price = get_current_market_price()
    if not price:
        return jsonify({"error": "Bu saat için fiyat bulunamadı"}), 404

    return jsonify(price)


@api_bp.route('/market-prices', methods=['POST'])
@requires_auth
@requires_role('admin', 'super_admin')
def import_market_prices():
    """
    EPİAŞ fiyatlarını içe aktar (Sadece Admin).
    ---
    tags:
      - Market
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
            - prices
          properties:
            prices:
              type: array
              items:
                type: object
                properties:
                  date:
                    type: string
                    format: date
                    example: "2024-01-15"
                  hour:
                    type: integer
                    example: 17
                  ptf:
                    type: number
                    example: 3.45
                  smf:
                    type: number
                    example: 3.52
    responses:
      201:
        description: Fiyatlar kaydedildi
        schema:
          type: object
          properties:
            message:
              type: string
            total_processed:
              type: integer
      400:
        description: Fiyat verisi bulunamadı
      401:
        description: Yetkisiz erişim
      403:
        description: Yetki yetersiz (Admin gerekli)
    """
    user = get_db_user()
    
    data = request.json
    prices = data.get("prices", [])

    if not prices:
        return jsonify({"error": "Fiyat verisi bulunamadı"}), 400

    saved_count = save_market_prices(prices)
    return jsonify({
        "message": f"{saved_count} yeni fiyat kaydedildi",
        "total_processed": len(prices)
    }), 201
