from datetime import datetime, timedelta, date
from flask import Blueprint, jsonify, current_app, request
from flasgger import swag_from
from sqlalchemy import func, text, and_, cast, Date

from app.auth import requires_auth
from app.api.helpers import get_current_user
from app.extensions import db
from app.models import (
    SmartDevice,
    MarketPrice,
    Wallet,
    WalletTransaction,
    Notification,
    AutomationLog,
    Automation,
    Organization,
    EnergySavings,
    DeviceTelemetry,
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

    # Leaderboard sıralaması hesapla
    rank = _calculate_user_rank(wallet)

    return {
        "balance": float(wallet.balance),
        "todays_earnings": float(today_earn),
        "level": wallet.level,
        "rank": rank
    }


def _calculate_user_rank(wallet: Wallet) -> int:
    """Kullanıcının organizasyon içindeki sıralamasını hesapla."""
    if not wallet or not wallet.user:
        return 0
    
    org_id = wallet.user.organization_id
    if not org_id:
        return 0
    
    # Aynı organizasyondaki kullanıcıları bakiyeye göre sırala
    higher_ranked = db.session.query(func.count(Wallet.id)).join(
        Wallet.user
    ).filter(
        Wallet.user.has(organization_id=org_id),
        Wallet.balance > wallet.balance
    ).scalar() or 0
    
    return higher_ranked + 1  # 1-indexed rank

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


def _parse_date_range(start_date_str: str = None, end_date_str: str = None, period: str = None):
    """
    Tarih aralığını parse et.
    
    Args:
        start_date_str: Başlangıç tarihi (YYYY-MM-DD)
        end_date_str: Bitiş tarihi (YYYY-MM-DD)
        period: Önceden tanımlı dönem (today, week, month, year)
    
    Returns:
        tuple: (start_datetime, end_datetime)
    """
    now = datetime.utcnow()
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    
    if period:
        if period == "today":
            return today_start, now
        elif period == "yesterday":
            yesterday = today_start - timedelta(days=1)
            return yesterday, today_start
        elif period == "week":
            week_start = today_start - timedelta(days=today_start.weekday())
            return week_start, now
        elif period == "month":
            month_start = today_start.replace(day=1)
            return month_start, now
        elif period == "year":
            year_start = today_start.replace(month=1, day=1)
            return year_start, now
        elif period == "last_7_days":
            return today_start - timedelta(days=7), now
        elif period == "last_30_days":
            return today_start - timedelta(days=30), now
        elif period == "last_90_days":
            return today_start - timedelta(days=90), now
    
    # Custom date range
    if start_date_str:
        try:
            start_date = datetime.strptime(start_date_str, "%Y-%m-%d")
        except ValueError:
            start_date = today_start - timedelta(days=30)
    else:
        start_date = today_start - timedelta(days=30)
    
    if end_date_str:
        try:
            end_date = datetime.strptime(end_date_str, "%Y-%m-%d").replace(hour=23, minute=59, second=59)
        except ValueError:
            end_date = now
    else:
        end_date = now
    
    return start_date, end_date


@bp.route("/statistics", methods=["GET"])
@requires_auth
@swag_from({
    "tags": ["Dashboard"],
    "summary": "Dashboard istatistikleri - Tarih filtrelemeli",
    "security": [{"bearerAuth": []}],
    "parameters": [
        {
            "name": "period",
            "in": "query",
            "type": "string",
            "enum": ["today", "yesterday", "week", "month", "year", "last_7_days", "last_30_days", "last_90_days"],
            "description": "Önceden tanımlı dönem"
        },
        {
            "name": "start_date",
            "in": "query",
            "type": "string",
            "format": "date",
            "description": "Başlangıç tarihi (YYYY-MM-DD)"
        },
        {
            "name": "end_date",
            "in": "query",
            "type": "string",
            "format": "date",
            "description": "Bitiş tarihi (YYYY-MM-DD)"
        }
    ],
    "responses": {
        200: {
            "description": "Dashboard statistics with date filtering",
            "schema": {
                "type": "object",
                "properties": {
                    "period": {"type": "object"},
                    "energy": {"type": "object"},
                    "savings": {"type": "object"},
                    "devices": {"type": "object"},
                    "automations": {"type": "object"},
                    "costs": {"type": "object"}
                }
            }
        }
    }
})
def get_dashboard_statistics():
    """Tarih filtrelemeli dashboard istatistikleri."""
    user = get_current_user()
    if not user or not user.organization_id:
        return jsonify({"error": "Organizasyon bulunamadı"}), 400
    
    org_id = user.organization_id
    
    # Parse date range
    period = request.args.get("period")
    start_date_str = request.args.get("start_date")
    end_date_str = request.args.get("end_date")
    start_date, end_date = _parse_date_range(start_date_str, end_date_str, period)
    
    try:
        # Get organization for pricing
        org = Organization.query.get(org_id)
        electricity_price = float(org.electricity_price_kwh) if org and org.electricity_price_kwh else 2.5
        currency = org.currency if org else "TRY"
        
        # Energy statistics
        energy_stats = _get_energy_statistics(org_id, start_date, end_date)
        
        # Savings statistics
        savings_stats = _get_savings_statistics(org_id, start_date, end_date, electricity_price, currency)
        
        # Device statistics
        device_stats = _get_device_statistics(org_id, start_date, end_date)
        
        # Automation statistics
        automation_stats = _get_automation_statistics(org_id, start_date, end_date)
        
        # Cost statistics
        cost_stats = _get_cost_statistics(org_id, start_date, end_date, electricity_price, currency)
        
        response = {
            "period": {
                "start_date": start_date.isoformat(),
                "end_date": end_date.isoformat(),
                "days": (end_date - start_date).days + 1
            },
            "energy": energy_stats,
            "savings": savings_stats,
            "devices": device_stats,
            "automations": automation_stats,
            "costs": cost_stats
        }
        
        return jsonify(response), 200
        
    except Exception as e:
        current_app.logger.error(f"Dashboard Statistics Error: {str(e)}")
        return jsonify({"error": "İstatistik hesaplanırken hata oluştu"}), 500


def _get_energy_statistics(org_id, start_date, end_date):
    """Enerji tüketim istatistikleri."""
    # Total consumption in period
    sql = text("""
        SELECT 
            COALESCE(SUM(t.value), 0) as total_consumption,
            COALESCE(AVG(t.value), 0) as avg_daily_consumption,
            COALESCE(MAX(t.value), 0) as peak_consumption
        FROM device_telemetry t
        JOIN smart_devices d ON d.id = t.device_id
        WHERE d.organization_id = :org_id
          AND t.key = 'energy_total_kwh'
          AND t.time >= :start_date
          AND t.time <= :end_date
    """)
    result = db.session.execute(sql, {
        "org_id": org_id, 
        "start_date": start_date,
        "end_date": end_date
    }).fetchone()
    
    # Daily breakdown
    daily_sql = text("""
        SELECT 
            DATE(t.time) as date,
            COALESCE(SUM(t.value), 0) as consumption
        FROM device_telemetry t
        JOIN smart_devices d ON d.id = t.device_id
        WHERE d.organization_id = :org_id
          AND t.key = 'energy_total_kwh'
          AND t.time >= :start_date
          AND t.time <= :end_date
        GROUP BY DATE(t.time)
        ORDER BY DATE(t.time)
    """)
    daily_result = db.session.execute(daily_sql, {
        "org_id": org_id,
        "start_date": start_date,
        "end_date": end_date
    }).fetchall()
    
    return {
        "total_consumption_kwh": round(float(result[0] or 0), 2),
        "avg_daily_consumption_kwh": round(float(result[1] or 0), 2),
        "peak_consumption_kwh": round(float(result[2] or 0), 2),
        "daily_breakdown": [
            {"date": str(row[0]), "consumption_kwh": round(float(row[1]), 2)}
            for row in daily_result
        ]
    }


def _get_savings_statistics(org_id, start_date, end_date, electricity_price, currency):
    """Tasarruf istatistikleri."""
    # Query savings from EnergySavings table
    savings = db.session.query(
        func.sum(EnergySavings.energy_saved_kwh).label('total_energy'),
        func.sum(EnergySavings.money_saved).label('total_money'),
        func.sum(EnergySavings.off_duration_minutes).label('total_minutes')
    ).filter(
        EnergySavings.organization_id == org_id,
        EnergySavings.date >= start_date.date(),
        EnergySavings.date <= end_date.date()
    ).first()
    
    # Daily savings breakdown
    daily_savings = db.session.query(
        EnergySavings.date,
        func.sum(EnergySavings.energy_saved_kwh).label('energy'),
        func.sum(EnergySavings.money_saved).label('money')
    ).filter(
        EnergySavings.organization_id == org_id,
        EnergySavings.date >= start_date.date(),
        EnergySavings.date <= end_date.date()
    ).group_by(EnergySavings.date).order_by(EnergySavings.date).all()
    
    # Savings by source type
    by_source = db.session.query(
        EnergySavings.source_type,
        func.sum(EnergySavings.energy_saved_kwh).label('energy'),
        func.sum(EnergySavings.money_saved).label('money')
    ).filter(
        EnergySavings.organization_id == org_id,
        EnergySavings.date >= start_date.date(),
        EnergySavings.date <= end_date.date()
    ).group_by(EnergySavings.source_type).all()
    
    return {
        "total_energy_saved_kwh": round(float(savings[0] or 0), 2),
        "total_money_saved": round(float(savings[1] or 0), 2),
        "total_off_duration_hours": round(float(savings[2] or 0) / 60, 1),
        "currency": currency,
        "electricity_price_kwh": electricity_price,
        "daily_breakdown": [
            {
                "date": str(row[0]),
                "energy_saved_kwh": round(float(row[1] or 0), 2),
                "money_saved": round(float(row[2] or 0), 2)
            }
            for row in daily_savings
        ],
        "by_source": [
            {
                "source": row[0],
                "energy_saved_kwh": round(float(row[1] or 0), 2),
                "money_saved": round(float(row[2] or 0), 2)
            }
            for row in by_source
        ]
    }


def _get_device_statistics(org_id, start_date, end_date):
    """Cihaz istatistikleri."""
    # Device counts
    total_devices = SmartDevice.query.filter_by(organization_id=org_id, is_active=True).count()
    online_devices = SmartDevice.query.filter_by(organization_id=org_id, is_active=True, is_online=True).count()
    
    # Devices by brand
    by_brand = db.session.query(
        SmartDevice.brand,
        func.count(SmartDevice.id).label('count')
    ).filter(
        SmartDevice.organization_id == org_id,
        SmartDevice.is_active == True
    ).group_by(SmartDevice.brand).all()
    
    # Devices by type
    by_type = db.session.query(
        SmartDevice.device_type,
        func.count(SmartDevice.id).label('count')
    ).filter(
        SmartDevice.organization_id == org_id,
        SmartDevice.is_active == True
    ).group_by(SmartDevice.device_type).all()
    
    # Total power rating
    total_power = db.session.query(
        func.sum(SmartDevice.power_rating_watt)
    ).filter(
        SmartDevice.organization_id == org_id,
        SmartDevice.is_active == True
    ).scalar() or 0
    
    return {
        "total_devices": total_devices,
        "online_devices": online_devices,
        "offline_devices": total_devices - online_devices,
        "online_percentage": round((online_devices / total_devices * 100) if total_devices > 0 else 0, 1),
        "total_power_rating_watt": int(total_power),
        "by_brand": [
            {"brand": row[0] or "unknown", "count": row[1]}
            for row in by_brand
        ],
        "by_type": [
            {"type": row[0] or "unknown", "count": row[1]}
            for row in by_type
        ]
    }


def _get_automation_statistics(org_id, start_date, end_date):
    """Otomasyon istatistikleri."""
    # Automation counts
    total_automations = Automation.query.filter_by(organization_id=org_id).count()
    active_automations = Automation.query.filter_by(organization_id=org_id, is_active=True).count()
    
    # Automation logs in period
    total_triggers = AutomationLog.query.filter(
        AutomationLog.organization_id == org_id,
        AutomationLog.triggered_at >= start_date,
        AutomationLog.triggered_at <= end_date
    ).count()
    
    successful_triggers = AutomationLog.query.filter(
        AutomationLog.organization_id == org_id,
        AutomationLog.triggered_at >= start_date,
        AutomationLog.triggered_at <= end_date,
        AutomationLog.status == "success"
    ).count()
    
    failed_triggers = AutomationLog.query.filter(
        AutomationLog.organization_id == org_id,
        AutomationLog.triggered_at >= start_date,
        AutomationLog.triggered_at <= end_date,
        AutomationLog.status == "failed"
    ).count()
    
    # Daily automation triggers
    daily_triggers = db.session.query(
        func.date(AutomationLog.triggered_at).label('date'),
        func.count(AutomationLog.id).label('count')
    ).filter(
        AutomationLog.organization_id == org_id,
        AutomationLog.triggered_at >= start_date,
        AutomationLog.triggered_at <= end_date
    ).group_by(func.date(AutomationLog.triggered_at)).order_by(func.date(AutomationLog.triggered_at)).all()
    
    return {
        "total_automations": total_automations,
        "active_automations": active_automations,
        "total_triggers": total_triggers,
        "successful_triggers": successful_triggers,
        "failed_triggers": failed_triggers,
        "success_rate": round((successful_triggers / total_triggers * 100) if total_triggers > 0 else 0, 1),
        "daily_triggers": [
            {"date": str(row[0]), "count": row[1]}
            for row in daily_triggers
        ]
    }


def _get_cost_statistics(org_id, start_date, end_date, electricity_price, currency):
    """Maliyet istatistikleri."""
    # Get energy consumption
    sql = text("""
        SELECT COALESCE(SUM(t.value), 0) as total_consumption
        FROM device_telemetry t
        JOIN smart_devices d ON d.id = t.device_id
        WHERE d.organization_id = :org_id
          AND t.key = 'energy_total_kwh'
          AND t.time >= :start_date
          AND t.time <= :end_date
    """)
    result = db.session.execute(sql, {
        "org_id": org_id,
        "start_date": start_date,
        "end_date": end_date
    }).scalar() or 0
    
    total_consumption = float(result)
    total_cost = total_consumption * electricity_price
    
    # Get savings
    savings = db.session.query(
        func.sum(EnergySavings.money_saved)
    ).filter(
        EnergySavings.organization_id == org_id,
        EnergySavings.date >= start_date.date(),
        EnergySavings.date <= end_date.date()
    ).scalar() or 0
    
    # Daily cost breakdown
    daily_sql = text("""
        SELECT 
            DATE(t.time) as date,
            COALESCE(SUM(t.value), 0) as consumption
        FROM device_telemetry t
        JOIN smart_devices d ON d.id = t.device_id
        WHERE d.organization_id = :org_id
          AND t.key = 'energy_total_kwh'
          AND t.time >= :start_date
          AND t.time <= :end_date
        GROUP BY DATE(t.time)
        ORDER BY DATE(t.time)
    """)
    daily_result = db.session.execute(daily_sql, {
        "org_id": org_id,
        "start_date": start_date,
        "end_date": end_date
    }).fetchall()
    
    return {
        "total_consumption_kwh": round(total_consumption, 2),
        "total_cost": round(total_cost, 2),
        "total_savings": round(float(savings), 2),
        "net_cost": round(total_cost - float(savings), 2),
        "currency": currency,
        "electricity_price_kwh": electricity_price,
        "daily_breakdown": [
            {
                "date": str(row[0]),
                "consumption_kwh": round(float(row[1]), 2),
                "cost": round(float(row[1]) * electricity_price, 2)
            }
            for row in daily_result
        ]
    }


@bp.route("/savings/summary", methods=["GET"])
@requires_auth
@swag_from({
    "tags": ["Dashboard"],
    "summary": "Tasarruf özeti - Organizasyon bazlı",
    "security": [{"bearerAuth": []}],
    "parameters": [
        {
            "name": "period",
            "in": "query",
            "type": "string",
            "enum": ["today", "week", "month", "year"],
            "default": "month",
            "description": "Dönem"
        }
    ],
    "responses": {
        200: {
            "description": "Savings summary",
            "schema": {
                "type": "object",
                "properties": {
                    "total_energy_saved_kwh": {"type": "number"},
                    "total_money_saved": {"type": "number"},
                    "co2_avoided_kg": {"type": "number"},
                    "trees_equivalent": {"type": "number"}
                }
            }
        }
    }
})
def get_savings_summary():
    """Organizasyon tasarruf özeti."""
    user = get_current_user()
    if not user or not user.organization_id:
        return jsonify({"error": "Organizasyon bulunamadı"}), 400
    
    org_id = user.organization_id
    period = request.args.get("period", "month")
    start_date, end_date = _parse_date_range(period=period)
    
    try:
        org = Organization.query.get(org_id)
        currency = org.currency if org else "TRY"
        
        # Query savings
        savings = db.session.query(
            func.sum(EnergySavings.energy_saved_kwh).label('total_energy'),
            func.sum(EnergySavings.money_saved).label('total_money')
        ).filter(
            EnergySavings.organization_id == org_id,
            EnergySavings.date >= start_date.date(),
            EnergySavings.date <= end_date.date()
        ).first()
        
        total_energy = float(savings[0] or 0)
        total_money = float(savings[1] or 0)
        
        # CO2 calculation: ~0.5 kg CO2 per kWh (Turkey average)
        co2_avoided = total_energy * 0.5
        
        # Trees equivalent: 1 tree absorbs ~22 kg CO2 per year
        trees_equivalent = co2_avoided / 22 * 12  # Monthly equivalent
        
        return jsonify({
            "period": {
                "name": period,
                "start_date": start_date.isoformat(),
                "end_date": end_date.isoformat()
            },
            "total_energy_saved_kwh": round(total_energy, 2),
            "total_money_saved": round(total_money, 2),
            "currency": currency,
            "co2_avoided_kg": round(co2_avoided, 2),
            "trees_equivalent": round(trees_equivalent, 1),
            "comparison": {
                "phone_charges": int(total_energy * 100),  # ~0.01 kWh per charge
                "led_bulb_hours": int(total_energy * 100),  # 10W LED
                "km_driven": round(co2_avoided / 0.12, 1)  # ~0.12 kg CO2/km
            }
        }), 200
        
    except Exception as e:
        current_app.logger.error(f"Savings Summary Error: {str(e)}")
        return jsonify({"error": "Tasarruf özeti hesaplanırken hata oluştu"}), 500


@bp.route("/activity", methods=["GET"])
@requires_auth
@swag_from({
    "tags": ["Dashboard"],
    "summary": "Activity Log - Son olayları listele",
    "security": [{"bearerAuth": []}],
    "parameters": [
        {
            "name": "limit",
            "in": "query",
            "type": "integer",
            "default": 20,
            "description": "Döndürülecek aktivite sayısı (max 100)"
        },
        {
            "name": "organization_id",
            "in": "query",
            "type": "string",
            "description": "Sadece super_admin için: Belirli bir organizasyonun aktivitelerini getir"
        }
    ],
    "responses": {
        200: {
            "description": "Aktivite listesi",
            "schema": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "id": {"type": "string"},
                        "type": {"type": "string", "example": "automation"},
                        "title": {"type": "string"},
                        "status": {"type": "string", "example": "success"},
                        "detail": {"type": "string"},
                        "timestamp": {"type": "string", "format": "date-time"},
                        "organization_id": {"type": "string"}
                    }
                }
            }
        },
        401: {"description": "Yetkisiz erişim"},
        403: {"description": "Yetki yok"}
    }
})
def get_activity_log():
    """Dashboard Activity Log endpoint'i."""
    user = get_current_user()
    if not user:
        return jsonify({"error": "Unauthorized"}), 401

    limit = request.args.get("limit", 20, type=int)
    limit = max(1, min(limit, 100))
    org_id_param = request.args.get("organization_id")

    # Yetki kontrolü: normal kullanıcılar sadece kendi organizasyonlarını görebilir
    user_role = user.role.code if user.role else None
    if user_role == "super_admin":
        target_org_id = org_id_param or (str(user.organization_id) if user.organization_id else None)
    else:
        target_org_id = str(user.organization_id) if user.organization_id else None

    if not target_org_id:
        return jsonify({"error": "Organizasyon bulunamadı"}), 400

    # Şimdilik otomasyon loglarını temel alıyoruz; ileride farklı kaynaklardan da birleşebilir
    query = AutomationLog.query.order_by(AutomationLog.triggered_at.desc())
    if target_org_id:
        query = query.filter_by(organization_id=target_org_id)
    logs = query.limit(limit).all()

    activities = []
    for log in logs:
        activities.append({
            "id": str(log.id),
            "type": "automation",
            "title": log.action_taken or "Otomasyon",
            "status": log.status,
            "detail": log.reason,
            "timestamp": log.triggered_at.isoformat() if log.triggered_at else None,
            "automation_id": str(log.automation_id),
            "organization_id": str(log.organization_id) if log.organization_id else None,
        })

    return jsonify(activities)
