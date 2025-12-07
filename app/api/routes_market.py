"""Enerji piyasası fiyatları (EPİAŞ) endpoint'leri."""
from datetime import datetime, timedelta

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
    """
    user = get_or_create_user()
    if not user:
        return jsonify({"error": "Kullanıcı bulunamadı"}), 401

    # get_current_market_price artık her zaman bir değer döner (fallback mekanizması)
    price = get_current_market_price()
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


@api_bp.route('/market-prices/health', methods=['GET'])
@requires_auth
@requires_role('admin', 'super_admin')
def get_market_health():
    """
    Market verilerinin sağlık durumunu getir (Super Admin).
    ---
    tags:
      - Market
    security:
      - bearerAuth: []
    responses:
      200:
        description: Market veri sağlık durumu
        schema:
          type: object
          properties:
            status:
              type: string
              enum: [healthy, warning, critical]
            last_update:
              type: string
              format: date-time
            record_count_24h:
              type: integer
            record_count_total:
              type: integer
            source:
              type: string
            epias_credentials_configured:
              type: boolean
            message:
              type: string
      401:
        description: Yetkisiz erişim
      403:
        description: Yetki yetersiz
    """
    from app.models import MarketPrice
    import os
    
    now = datetime.utcnow()
    yesterday = now - timedelta(hours=24)
    
    # Son kayıt
    latest = MarketPrice.query.order_by(MarketPrice.time.desc()).first()
    
    # 24 saatlik kayıt sayısı
    count_24h = MarketPrice.query.filter(MarketPrice.time >= yesterday).count()
    
    # Toplam kayıt
    total_count = MarketPrice.query.count()
    
    # EPİAŞ credentials kontrolü
    epias_configured = bool(os.getenv("EPIAS_USERNAME") and os.getenv("EPIAS_PASSWORD"))
    
    # Sağlık durumu belirleme
    if latest is None:
        status = "critical"
        message = "Veritabanında hiç fiyat verisi yok"
    elif (now - latest.time.replace(tzinfo=None)).total_seconds() > 7200:  # 2 saatten eski
        status = "warning"
        message = f"Son veri 2 saatten eski: {latest.time.isoformat()}"
    elif count_24h < 20:  # 24 saatte en az 20 kayıt olmalı
        status = "warning"
        message = f"Son 24 saatte sadece {count_24h} kayıt var (beklenen: 24)"
    else:
        status = "healthy"
        message = "Market verileri güncel"
    
    return jsonify({
        "status": status,
        "message": message,
        "last_update": latest.time.isoformat() if latest else None,
        "last_price_try_kwh": latest.price if latest else None,
        "record_count_24h": count_24h,
        "record_count_total": total_count,
        "source": "EPİAŞ Şeffaflık Platformu",
        "epias_credentials_configured": epias_configured,
        "checked_at": now.isoformat(),
    })


@api_bp.route('/market-prices/refresh', methods=['POST'])
@requires_auth
@requires_role('admin', 'super_admin')
def refresh_market_prices():
    """
    EPİAŞ'tan fiyatları manuel olarak yenile (Super Admin).
    ---
    tags:
      - Market
    security:
      - bearerAuth: []
    responses:
      200:
        description: Yenileme başlatıldı
      401:
        description: Yetkisiz erişim
      403:
        description: Yetki yetersiz
    """
    try:
        from app.tasks.market_tasks import fetch_epias_prices
        # Celery task olarak async çalıştır
        fetch_epias_prices.delay()
        return jsonify({
            "message": "EPİAŞ fiyat güncelleme görevi başlatıldı",
            "status": "queued"
        })
    except Exception as e:
        return jsonify({
            "error": str(e),
            "status": "failed"
        }), 500
