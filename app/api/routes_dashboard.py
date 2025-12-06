from datetime import datetime, timedelta
from flask import Blueprint, jsonify, current_app
from flasgger import swag_from
from sqlalchemy import func, text

from app.auth import requires_auth
from app.api.helpers import get_current_user
from app.extensions import db
from app.models import (
    SmartDevice,
    MarketPrice,
    Wallet,
    WalletTransaction,
    Notification,
)

bp = Blueprint('dashboard', __name__)

CHEAP_PRICE_THRESHOLD = 2.0  # TL
EXPENSIVE_PRICE_THRESHOLD = 3.5 # TL

@bp.route("/summary", methods=["GET"])
@requires_auth
@swag_from({
    "tags": ["Dashboard"],
    "summary": "Dashboard özet verilerini getir (Bento Grid)",
    "security": [{"bearerAuth": []}],
    "responses": {
        200: {
            "description": "Dashboard summary data",
            "schema": {
                "type": "object",
                "properties": {
                    "kpis": {"type": "object", "description": "Altyapı ve Tüketim"},
                    "market_status": {"type": "object", "description": "EPİAŞ ve Öneri"},
                    "wallet_summary": {"type": "object", "description": "Oyunlaştırma"},
                    "active_alerts_count": {"type": "integer"}
                }
            }
        }
    }
})
def get_dashboard_summary():
    """Frontend Dashboard'u tek seferde dolduracak aggregator endpoint."""
    user = get_current_user()
    
    # 1. Güvenlik ve Yetki Kontrolü
    if not user or not user.organization_id:
        return jsonify({"error": "Organizasyon bulunamadı"}), 400

    org_id = user.organization_id
    now = datetime.utcnow()
    day_start = now.replace(hour=0, minute=0, second=0, microsecond=0)

    # 2. Veri Toplama (Aggregation)
    try:
        # A. Altyapı Verileri (Infrastructure)
        total_power = _get_total_active_power(org_id)
        daily_consumption = _get_daily_consumption(org_id, day_start)
        
        # B. Maliyet Hesabı (Cost)
        avg_price = _get_average_market_price(day_start)
        daily_cost = round(daily_consumption * avg_price, 2)

        # C. Sistem Sağlığı (Health)
        grid_score = _get_grid_health_score(org_id)
        
        # D. Pazar ve Cüzdan (Intelligence & Gamification)
        market_info = _get_market_status()
        wallet_info = _get_wallet_summary(user, day_start)
        alerts_count = _get_active_alerts_count(org_id)

        # 3. Yanıt Oluşturma (DTO)
        response = {
            "kpis": {
                "total_active_power_w": round(total_power, 2),      # Speedometer için
                "total_daily_consumption_kwh": round(daily_consumption, 2),
                "daily_cost_try": daily_cost,                       # Finans Kartı için
                "grid_health_score": grid_score,                    # Sağlık Barı için
                "online_devices_count": _get_online_device_count(org_id)
            },
            "market_status": market_info,                           # Traffic Light için
            "wallet_summary": wallet_info,                          # Wallet Kartı için
            "active_alerts_count": alerts_count,                    # Zil üzerindeki badge
            "quick_actions": _get_quick_actions()                   # Butonlar
        }
        
        return jsonify(response), 200

    except Exception as e:
        current_app.logger.error(f"Dashboard Error: {str(e)}")
        return jsonify({"error": "Dashboard verisi hesaplanırken hata oluştu"}), 500


# --- YARDIMCI FONKSİYONLAR (SQL OPTİMİZASYONU) ---

def _get_total_active_power(org_id):
    """
    Tüm cihazların SON gönderdiği 'power_w' değerini toplar.
    TimescaleDB optimize sorgusu.
    """
    sql = text("""
        SELECT COALESCE(SUM(latest_power), 0)
        FROM (
            SELECT DISTINCT ON (t.device_id) t.value AS latest_power
            FROM device_telemetry t
            JOIN smart_devices d ON d.id = t.device_id
            WHERE d.organization_id = :org_id
              AND t.key = 'power_w'
              AND t.time > NOW() - INTERVAL '1 hour'
            ORDER BY t.device_id, t.time DESC
        ) AS subquery
    """)
    result = db.session.execute(sql, {"org_id": org_id}).scalar()
    return float(result or 0)

def _get_daily_consumption(org_id, day_start):
    """
    Bugün harcanan toplam enerji (kWh).
    Mantık: (Bugünkü Son Okuma - Bugünkü İlk Okuma)
    """
    # Basitleştirilmiş: energy_total_kwh kümülatif artıyorsa max-min yapılabilir.
    # Şimdilik basitçe saatlik tüketimlerin toplamı varsayalım.
    sql = text("""
        SELECT COALESCE(SUM(t.value), 0)
        FROM device_telemetry t
        JOIN smart_devices d ON d.id = t.device_id
        WHERE d.organization_id = :org_id
          AND t.key = 'energy_total_kwh'
          AND t.time >= :day_start
    """)
    result = db.session.execute(sql, {"org_id": org_id, "day_start": day_start}).scalar()
    return float(result or 0)

def _get_average_market_price(day_start):
    """Bugünün ortalama elektrik fiyatı (TL)."""
    avg = (
        db.session.query(func.avg(MarketPrice.price))
        .filter(MarketPrice.time >= day_start)
        .scalar()
    )
    return float(avg or 0)

def _get_grid_health_score(org_id):
    """Sistem Sağlık Skoru: (Online / Toplam) * 100"""
    total = SmartDevice.query.filter_by(organization_id=org_id).count()
    if total == 0: return 100
    online = SmartDevice.query.filter_by(organization_id=org_id, is_online=True).count()
    return int((online / total) * 100)

def _get_online_device_count(org_id):
    return SmartDevice.query.filter_by(organization_id=org_id, is_online=True).count()

def _get_market_status():
    """Şu anki piyasa durumu ve yapay zeka önerisi."""
    now = datetime.utcnow()
    
    # En son fiyatı bul
    latest = MarketPrice.query.filter(MarketPrice.time <= now)\
        .order_by(MarketPrice.time.desc()).first()
    
    current_price = float(latest.price) if latest else 0.0
    
    # Durum Belirle
    if current_price < CHEAP_PRICE_THRESHOLD:
        status = "cheap"
    elif current_price > EXPENSIVE_PRICE_THRESHOLD:
        status = "expensive"
    else:
        status = "normal"
        
    # Gelecek ucuz saati bul
    next_slot = "Şu an!"
    if status == "expensive":
        future = MarketPrice.query.filter(
            MarketPrice.time > now, 
            MarketPrice.price < CHEAP_PRICE_THRESHOLD
        ).order_by(MarketPrice.time.asc()).first()
        
        if future:
            next_slot = future.time.strftime("%H:%00")
            
    return {
        "current_price": current_price,
        "status": status,
        "next_cheap_slot": next_slot,
        "currency": "TL/MWh"
    }

def _get_wallet_summary(user, day_start):
    """Kullanıcı cüzdan özeti."""
    wallet = Wallet.query.filter_by(user_id=user.id).first()
    
    if not wallet:
        return {"balance": 0, "todays_earnings": 0, "rank": 0, "level": 1}

    # Bugün kazanılan
    today_earn = db.session.query(func.sum(WalletTransaction.amount))\
        .filter(
            WalletTransaction.wallet_id == wallet.id,
            WalletTransaction.created_at >= day_start,
            WalletTransaction.amount > 0
        ).scalar() or 0.0

    return {
        "balance": float(wallet.balance),
        "todays_earnings": float(today_earn),
        "level": wallet.level,
        "rank": 5 # TODO: Leaderboard query eklenebilir
    }

def _get_active_alerts_count(org_id):
    """Okunmamış kritik bildirim sayısı."""
    return Notification.query.filter_by(
        organization_id=org_id, 
        is_read=False
    ).count()

def _get_quick_actions():
    """Frontend'deki butonlar için konfigürasyon."""
    return [
        {"id": "mode_eco", "label": "Tasarruf Modu", "icon": "leaf", "active": False},
        {"id": "mode_comfort", "label": "Konfor Modu", "icon": "sun", "active": True},
        {"id": "all_off", "label": "Hepsini Kapat", "icon": "power", "active": False}
    ]
