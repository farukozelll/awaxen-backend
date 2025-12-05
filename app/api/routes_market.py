"""Enerji piyasası fiyatları (EPİAŞ) endpoint'leri."""
from datetime import datetime

from flask import jsonify, request

from . import api_bp
from .helpers import get_or_create_user
from ..auth import requires_auth
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


@api_bp.route('/market-prices/current', methods=['GET'])
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


@api_bp.route('/market-prices', methods=['POST'])
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
