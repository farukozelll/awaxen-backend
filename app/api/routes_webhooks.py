"""
Webhook endpoints (Telegram Bot Commands) - Professional Edition.

Desteklenen Komutlar:
- /start: Hesap eşleştirme
- /status: Sistem durumu
- /market: Anlık piyasa fiyatı
- /balance: Cüzdan bakiyesi
- /devices: Cihaz listesi ve kontrolü
- /alerts: Fiyat alarmları yönetimi
- /report: Günlük/haftalık rapor
- /automations: Otomasyon durumu
- /settings: Bildirim ayarları
- /help: Yardım menüsü
"""
import json
import requests
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo
from flask import Blueprint, current_app, jsonify, request
from sqlalchemy import func

from app.extensions import db
from app.models import User, SmartDevice, Wallet, Automation, MarketPrice, DeviceTelemetry, Organization
from app.services import get_current_market_price
from app.services.savings_service import SavingsService

bp = Blueprint("webhooks", __name__)

TELEGRAM_API_URL = "https://api.telegram.org/bot"
TR_TIMEZONE = ZoneInfo("Europe/Istanbul")

# Kullanıcı oturum verileri (basit in-memory cache)
USER_SESSIONS = {}


@bp.route("/telegram", methods=["POST"])
def telegram_webhook():
    """Telegram botundan gelen komutları işle."""
    token = current_app.config.get("TELEGRAM_BOT_TOKEN")
    if not token:
        current_app.logger.error("[Telegram] Bot token missing.")
        return jsonify({"error": "Telegram bot token not configured"}), 500

    payload = request.get_json(silent=True) or {}
    
    # Callback query (buton tıklaması) kontrolü
    callback_query = payload.get("callback_query")
    if callback_query:
        return handle_callback_query(callback_query, token)
    
    message = payload.get("message")
    if not message:
        return jsonify({"status": "ignored"}), 200

    chat_id = message.get("chat", {}).get("id")
    username = message.get("from", {}).get("username")
    text = (message.get("text") or "").strip().lower()

    # Kullanıcıyı bul (chat_id veya username ile)
    user = None
    if chat_id:
        user = User.query.filter_by(telegram_chat_id=str(chat_id)).first()
    if not user and username:
        user = User.query.filter(User.telegram_username.ilike(username)).first()

    # Komut işleme
    if text.startswith("/start"):
        return handle_start(chat_id, username, user, token)
    
    elif text.startswith("/status"):
        return handle_status(chat_id, user, token)
    
    elif text.startswith("/market"):
        return handle_market(chat_id, user, token)
    
    elif text.startswith("/balance"):
        return handle_balance(chat_id, user, token)
    
    elif text.startswith("/devices"):
        return handle_devices(chat_id, user, token)
    
    elif text.startswith("/device "):
        # /device <id> - Cihaz detayı
        device_id = text.replace("/device ", "").strip()
        return handle_device_detail(chat_id, user, device_id, token)
    
    elif text.startswith("/alerts"):
        return handle_alerts(chat_id, user, token)
    
    elif text.startswith("/setalert "):
        # /setalert <price> - Fiyat alarmı kur
        return handle_set_alert(chat_id, user, text, token)
    
    elif text.startswith("/report"):
        return handle_report(chat_id, user, token)
    
    elif text.startswith("/automations"):
        return handle_automations(chat_id, user, token)
    
    elif text.startswith("/settings"):
        return handle_settings(chat_id, user, token)
    
    elif text.startswith("/help"):
        return handle_help(chat_id, token)
    
    else:
        # Bilinmeyen komut
        if text.startswith("/"):
            send_telegram_message(
                chat_id,
                "❓ Bilinmeyen komut. /help yazarak kullanılabilir komutları görebilirsin.",
                token,
            )

    return jsonify({"status": "ok"}), 200


def handle_start(chat_id, username, user, token):
    """Hesap eşleştirme komutu."""
    if not username:
        send_telegram_message(
            chat_id,
            "👋 Merhaba!\n\nLütfen Telegram kullanıcı adınızı (username) profilinizde tanımlayın.",
            token,
        )
        return jsonify({"status": "missing_username"}), 200

    if not user:
        user = User.query.filter(User.telegram_username.ilike(username)).first()
    
    if not user:
        send_telegram_message(
            chat_id,
            "❌ *Kullanıcı bulunamadı*\n\n"
            "Awaxen profilinizde Telegram kullanıcı adınızı kaydedip tekrar /start yazın.",
            token,
            parse_mode="Markdown",
        )
        return jsonify({"status": "user_not_found"}), 200

    user.telegram_chat_id = str(chat_id)
    db.session.commit()

    # Hoşgeldin mesajı + inline butonlar
    keyboard = {
        "inline_keyboard": [
            [
                {"text": "📊 Durum", "callback_data": "cmd_status"},
                {"text": "⚡ Piyasa", "callback_data": "cmd_market"},
            ],
            [
                {"text": "💰 Bakiye", "callback_data": "cmd_balance"},
                {"text": "🔌 Cihazlar", "callback_data": "cmd_devices"},
            ],
            [
                {"text": "❓ Yardım", "callback_data": "cmd_help"},
            ],
        ]
    }
    
    send_telegram_message(
        chat_id,
        f"✅ *Hoşgeldin {user.full_name or user.email}!*\n\n"
        f"Hesabın başarıyla eşleşti. Artık bildirimleri buradan alacaksın.\n\n"
        f"Aşağıdaki butonları kullanabilir veya komut yazabilirsin:",
        token,
        parse_mode="Markdown",
        reply_markup=keyboard,
    )
    return jsonify({"status": "linked"}), 200


def handle_status(chat_id, user, token):
    """Sistem durumu komutu."""
    if not user:
        send_telegram_message(chat_id, "❌ Önce /start ile hesabını eşleştir.", token)
        return jsonify({"status": "not_linked"}), 200

    # Cihaz istatistikleri
    org_id = user.organization_id
    total_devices = SmartDevice.query.filter_by(organization_id=org_id, is_active=True).count()
    online_devices = SmartDevice.query.filter_by(organization_id=org_id, is_active=True, is_online=True).count()
    
    # Cüzdan
    wallet = Wallet.query.filter_by(user_id=user.id).first()
    balance = wallet.balance if wallet else 0
    
    # Piyasa fiyatı (fallback garantili)
    market_info = get_current_market_price()
    market_text = format_market_summary(market_info)

    msg = (
        f"📊 *Sistem Durumu*\n\n"
        f"👤 Kullanıcı: {user.full_name or user.email}\n"
        f"🏠 Organizasyon: {user.organization.name if user.organization else 'N/A'}\n\n"
        f"🔌 Toplam Cihaz: {total_devices}\n"
        f"✅ Çevrimiçi: {online_devices}\n"
        f"❌ Çevrimdışı: {total_devices - online_devices}\n\n"
        f"💰 Bakiye: {balance:.2f} AWX\n\n"
        f"{market_text}"
    )
    
    send_telegram_message(chat_id, msg, token, parse_mode="Markdown")
    return jsonify({"status": "ok"}), 200


def handle_market(chat_id, user, token):
    """Anlık piyasa özetini gönder."""
    if not user:
        send_telegram_message(chat_id, "❌ Önce /start ile hesabını eşleştir.", token)
        return jsonify({"status": "not_linked"}), 200

    market_info = get_current_market_price()
    market_text = format_market_summary(market_info, header="⚡ *Anlık Piyasa Özeti*")

    send_telegram_message(chat_id, market_text, token, parse_mode="Markdown")
    return jsonify({"status": "ok"}), 200


def format_market_summary(market_info, header="⚡ *Anlık Piyasa*"):
    """Market servisinden gelen veriyi kullanıcı dostu metne çevir."""
    price_kwh = market_info.get("price")
    ptf_price = market_info.get("ptf")
    price_time = market_info.get("time")
    currency = market_info.get("currency", "TL/kWh")
    price_source = market_info.get("source", "unknown")
    is_default = market_info.get("is_default")

    lines = [header]
    lines.append(
        f"Fiyat: {price_kwh:.3f} {currency}" if price_kwh is not None else "Fiyat: Bilinmiyor"
    )
    if ptf_price:
        lines.append(f"PTF: {ptf_price:.0f} TL/MWh")
    local_time = _format_tr_time(price_time, include_date=True)
    if local_time:
        lines.append(f"Zaman: {local_time}")
    if is_default:
        lines.append("Kaynak: 🔁 Varsayılan (veri yok)")
    else:
        lines.append("Kaynak: EPİAŞ Şeffaflık Platformu")
        if price_source and price_source not in {"database", "cache"}:
            lines.append(f"İç Kaynak: {price_source}")

    return "\n".join(lines)


def _format_tr_time(price_time, include_date=False):
    """ISO time string'i Avrupa/İstanbul saatine çevir."""
    if not price_time:
        return None
    try:
        dt = datetime.fromisoformat(price_time.replace("Z", "+00:00"))
        if not dt.tzinfo:
            dt = dt.replace(tzinfo=ZoneInfo("UTC"))
        tr_dt = dt.astimezone(TR_TIMEZONE)
        fmt = "%d.%m.%Y %H:%M" if include_date else "%H:%M"
        return tr_dt.strftime(f"{fmt} (TR)")
    except ValueError:
        return price_time


def handle_balance(chat_id, user, token):
    """Cüzdan bakiyesi komutu."""
    if not user:
        send_telegram_message(chat_id, "❌ Önce /start ile hesabını eşleştir.", token)
        return jsonify({"status": "not_linked"}), 200

    wallet = Wallet.query.filter_by(user_id=user.id).first()
    balance = wallet.balance if wallet else 0
    
    msg = (
        f"💰 *Cüzdan Bilgileri*\n\n"
        f"Bakiye: *{balance:.2f} AWX*\n\n"
        f"_Enerji tasarrufu yaparak daha fazla AWX kazan!_"
    )
    
    send_telegram_message(chat_id, msg, token, parse_mode="Markdown")
    return jsonify({"status": "ok"}), 200


def handle_devices(chat_id, user, token):
    """Cihaz listesi komutu."""
    if not user:
        send_telegram_message(chat_id, "❌ Önce /start ile hesabını eşleştir.", token)
        return jsonify({"status": "not_linked"}), 200

    devices = SmartDevice.query.filter_by(
        organization_id=user.organization_id, 
        is_active=True
    ).limit(10).all()
    
    if not devices:
        send_telegram_message(chat_id, "🔌 Henüz kayıtlı cihaz yok.", token)
        return jsonify({"status": "ok"}), 200

    lines = ["🔌 *Cihazlarınız*\n"]
    for d in devices:
        status = "🟢" if d.is_online else "🔴"
        lines.append(f"{status} {d.name or d.device_type}")
    
    # Cihaz kontrol butonları
    keyboard = {
        "inline_keyboard": [
            [
                {"text": "🔄 Yenile", "callback_data": "cmd_devices"},
            ]
        ]
    }
    
    send_telegram_message(chat_id, "\n".join(lines), token, parse_mode="Markdown", reply_markup=keyboard)
    return jsonify({"status": "ok"}), 200


def handle_help(chat_id, token):
    """Yardım menüsü."""
    msg = (
        "❓ *Awaxen Bot Komutları*\n\n"
        "📊 *Durum & Bilgi*\n"
        "/start - Hesap eşleştirme\n"
        "/status - Sistem durumu\n"
        "/market - Anlık piyasa fiyatı\n"
        "/balance - Cüzdan bakiyesi\n\n"
        "🔌 *Cihaz Yönetimi*\n"
        "/devices - Cihaz listesi\n"
        "/device `<numara>` - Cihaz detayı\n\n"
        "⚡ *Fiyat Alarmları*\n"
        "/alerts - Aktif alarmlar\n"
        "/setalert `<fiyat>` - Yeni alarm kur\n\n"
        "📈 *Raporlar*\n"
        "/report - Günlük/haftalık rapor\n"
        "/automations - Otomasyon durumu\n\n"
        "⚙️ *Ayarlar*\n"
        "/settings - Bildirim ayarları\n"
        "/help - Bu yardım menüsü\n\n"
        "_Sorularınız için: support@awaxen.com_"
    )
    
    keyboard = {
        "inline_keyboard": [
            [
                {"text": "📊 Durum", "callback_data": "cmd_status"},
                {"text": "⚡ Piyasa", "callback_data": "cmd_market"},
            ],
            [
                {"text": "🔌 Cihazlar", "callback_data": "cmd_devices"},
                {"text": "📈 Rapor", "callback_data": "cmd_report"},
            ],
        ]
    }
    
    send_telegram_message(chat_id, msg, token, parse_mode="Markdown", reply_markup=keyboard)
    return jsonify({"status": "ok"}), 200


def handle_callback_query(callback_query, token):
    """Inline buton tıklamalarını işle."""
    callback_id = callback_query.get("id")
    chat_id = callback_query.get("message", {}).get("chat", {}).get("id")
    data = callback_query.get("data", "")
    
    # Callback'i onayla (loading spinner'ı kaldır)
    answer_callback(callback_id, token)
    
    # Kullanıcıyı bul
    user = User.query.filter_by(telegram_chat_id=str(chat_id)).first() if chat_id else None
    
    if data == "cmd_status":
        return handle_status(chat_id, user, token)
    elif data == "cmd_balance":
        return handle_balance(chat_id, user, token)
    elif data == "cmd_devices":
        return handle_devices(chat_id, user, token)
    elif data == "cmd_help":
        return handle_help(chat_id, token)
    elif data == "cmd_market":
        return handle_market(chat_id, user, token)
    elif data == "cmd_report":
        return handle_report(chat_id, user, token)
    elif data == "cmd_alerts":
        return handle_alerts(chat_id, user, token)
    elif data == "cmd_automations":
        return handle_automations(chat_id, user, token)
    elif data == "cmd_settings":
        return handle_settings(chat_id, user, token)
    elif data.startswith("device_"):
        # device_<id> - Cihaz detayı
        device_id = data.replace("device_", "")
        return handle_device_detail(chat_id, user, device_id, token)
    elif data.startswith("toggle_"):
        # toggle_<device_id> - Cihaz aç/kapa
        device_id = data.replace("toggle_", "")
        return handle_device_toggle(chat_id, user, device_id, token)
    elif data.startswith("alert_del_"):
        # alert_del_<index> - Alarm sil
        alert_idx = data.replace("alert_del_", "")
        return handle_delete_alert(chat_id, user, alert_idx, token)
    elif data == "report_daily":
        return handle_report_daily(chat_id, user, token)
    elif data == "report_weekly":
        return handle_report_weekly(chat_id, user, token)
    elif data.startswith("notif_"):
        # notif_<type>_<on/off> - Bildirim ayarı
        return handle_notification_toggle(chat_id, user, data, token)
    
    return jsonify({"status": "ok"}), 200


def answer_callback(callback_id, token):
    """Callback query'yi onayla."""
    url = f"{TELEGRAM_API_URL}{token}/answerCallbackQuery"
    try:
        requests.post(url, json={"callback_query_id": callback_id}, timeout=5)
    except requests.RequestException:
        pass


def send_telegram_message(chat_id, text, token, parse_mode=None, reply_markup=None):
    """Telegram'a mesaj gönder (buton desteğiyle)."""
    url = f"{TELEGRAM_API_URL}{token}/sendMessage"
    payload = {"chat_id": chat_id, "text": text}
    
    if parse_mode:
        payload["parse_mode"] = parse_mode
    if reply_markup:
        payload["reply_markup"] = reply_markup
    
    try:
        requests.post(url, json=payload, timeout=10)
    except requests.RequestException as exc:
        current_app.logger.error(f"[Telegram] sendMessage failed: {exc}")


# ==========================================
# Yeni Profesyonel Komutlar
# ==========================================

def handle_device_detail(chat_id, user, device_id, token):
    """Cihaz detayı ve kontrol butonları."""
    if not user:
        send_telegram_message(chat_id, "❌ Önce /start ile hesabını eşleştir.", token)
        return jsonify({"status": "not_linked"}), 200
    
    # Cihazı bul (numara veya ID ile)
    device = None
    try:
        # Önce numara olarak dene
        idx = int(device_id) - 1
        devices = SmartDevice.query.filter_by(
            organization_id=user.organization_id,
            is_active=True
        ).order_by(SmartDevice.name).all()
        if 0 <= idx < len(devices):
            device = devices[idx]
    except ValueError:
        # UUID olarak dene
        device = SmartDevice.query.filter_by(
            id=device_id,
            organization_id=user.organization_id
        ).first()
    
    if not device:
        send_telegram_message(chat_id, "❌ Cihaz bulunamadı.", token)
        return jsonify({"status": "not_found"}), 200
    
    # Son telemetri
    last_telemetry = DeviceTelemetry.query.filter_by(
        device_id=device.id
    ).order_by(DeviceTelemetry.time.desc()).first()
    
    status_emoji = "🟢" if device.is_online else "🔴"
    status_text = "Çevrimiçi" if device.is_online else "Çevrimdışı"
    
    msg = (
        f"🔌 *{device.name or device.device_type}*\n\n"
        f"Durum: {status_emoji} {status_text}\n"
        f"Tip: {device.device_type or 'Bilinmiyor'}\n"
    )
    
    if device.last_seen:
        last_seen = device.last_seen.astimezone(TR_TIMEZONE).strftime("%d.%m.%Y %H:%M")
        msg += f"Son Görülme: {last_seen}\n"
    
    if last_telemetry:
        msg += f"\n📊 *Son Ölçümler*\n"
        if last_telemetry.power_w is not None:
            msg += f"⚡ Güç: {last_telemetry.power_w:.1f} W\n"
        if last_telemetry.voltage is not None:
            msg += f"🔋 Voltaj: {last_telemetry.voltage:.1f} V\n"
        if last_telemetry.current is not None:
            msg += f"⚡ Akım: {last_telemetry.current:.2f} A\n"
        if last_telemetry.temperature is not None:
            msg += f"🌡️ Sıcaklık: {last_telemetry.temperature:.1f}°C\n"
        if last_telemetry.energy_total_kwh is not None:
            msg += f"📈 Toplam: {last_telemetry.energy_total_kwh:.2f} kWh\n"
    
    # Kontrol butonları
    toggle_text = "🔴 Kapat" if device.is_online else "🟢 Aç"
    keyboard = {
        "inline_keyboard": [
            [
                {"text": toggle_text, "callback_data": f"toggle_{device.id}"},
                {"text": "🔄 Yenile", "callback_data": f"device_{device.id}"},
            ],
            [
                {"text": "◀️ Cihazlar", "callback_data": "cmd_devices"},
            ]
        ]
    }
    
    send_telegram_message(chat_id, msg, token, parse_mode="Markdown", reply_markup=keyboard)
    return jsonify({"status": "ok"}), 200


def handle_device_toggle(chat_id, user, device_id, token):
    """Cihazı aç/kapa (MQTT komutu gönder)."""
    if not user:
        send_telegram_message(chat_id, "❌ Önce /start ile hesabını eşleştir.", token)
        return jsonify({"status": "not_linked"}), 200
    
    device = SmartDevice.query.filter_by(
        id=device_id,
        organization_id=user.organization_id
    ).first()
    
    if not device:
        send_telegram_message(chat_id, "❌ Cihaz bulunamadı.", token)
        return jsonify({"status": "not_found"}), 200
    
    # MQTT komutu gönder
    try:
        from app.mqtt_client import mqtt_client
        
        new_state = not device.is_online
        topic = f"awaxen/devices/{device.external_id or device.id}/command"
        payload = {
            "command": "power",
            "state": "on" if new_state else "off",
            "triggered_by": "telegram",
            "user_id": str(user.id)
        }
        
        mqtt_client.publish(topic, payload)
        
        action = "açıldı" if new_state else "kapatıldı"
        send_telegram_message(
            chat_id,
            f"✅ *{device.name}* {action}.\n\n_Komut gönderildi, cihaz yanıt bekleniyor..._",
            token,
            parse_mode="Markdown"
        )
        
    except Exception as e:
        current_app.logger.error(f"[Telegram] Device toggle error: {e}")
        send_telegram_message(chat_id, f"❌ Komut gönderilemedi: {e}", token)
    
    return jsonify({"status": "ok"}), 200


def handle_alerts(chat_id, user, token):
    """Fiyat alarmlarını listele."""
    if not user:
        send_telegram_message(chat_id, "❌ Önce /start ile hesabını eşleştir.", token)
        return jsonify({"status": "not_linked"}), 200
    
    # Kullanıcının alarmlarını al (user settings'den)
    alerts = []
    if user.settings and user.settings.preferences:
        alerts = user.settings.preferences.get("price_alerts", [])
    
    if not alerts:
        msg = (
            "⚡ *Fiyat Alarmları*\n\n"
            "Henüz alarm kurulmamış.\n\n"
            "Yeni alarm kurmak için:\n"
            "`/setalert 2.5` - Fiyat 2.5 TL/kWh altına düşünce bildir\n"
            "`/setalert >3.0` - Fiyat 3.0 TL/kWh üstüne çıkınca bildir"
        )
        send_telegram_message(chat_id, msg, token, parse_mode="Markdown")
        return jsonify({"status": "ok"}), 200
    
    lines = ["⚡ *Aktif Fiyat Alarmları*\n"]
    keyboard_buttons = []
    
    for i, alert in enumerate(alerts):
        direction = "📉" if alert.get("direction") == "below" else "📈"
        threshold = alert.get("threshold", 0)
        lines.append(f"{i+1}. {direction} {threshold:.2f} TL/kWh")
        keyboard_buttons.append([
            {"text": f"🗑️ Alarm {i+1} Sil", "callback_data": f"alert_del_{i}"}
        ])
    
    keyboard_buttons.append([{"text": "◀️ Geri", "callback_data": "cmd_status"}])
    
    send_telegram_message(
        chat_id, 
        "\n".join(lines), 
        token, 
        parse_mode="Markdown",
        reply_markup={"inline_keyboard": keyboard_buttons}
    )
    return jsonify({"status": "ok"}), 200


def handle_set_alert(chat_id, user, text, token):
    """Yeni fiyat alarmı kur."""
    if not user:
        send_telegram_message(chat_id, "❌ Önce /start ile hesabını eşleştir.", token)
        return jsonify({"status": "not_linked"}), 200
    
    # Parse: /setalert 2.5 veya /setalert >3.0
    parts = text.replace("/setalert", "").strip()
    
    direction = "below"
    if parts.startswith(">"):
        direction = "above"
        parts = parts[1:]
    elif parts.startswith("<"):
        parts = parts[1:]
    
    try:
        threshold = float(parts.replace(",", "."))
    except ValueError:
        send_telegram_message(
            chat_id,
            "❌ Geçersiz fiyat formatı.\n\nÖrnek: `/setalert 2.5` veya `/setalert >3.0`",
            token,
            parse_mode="Markdown"
        )
        return jsonify({"status": "invalid"}), 200
    
    # Alarmı kaydet
    from app.models import UserSettings
    
    if not user.settings:
        user.settings = UserSettings(user_id=user.id, preferences={})
        db.session.add(user.settings)
    
    if not user.settings.preferences:
        user.settings.preferences = {}
    
    alerts = user.settings.preferences.get("price_alerts", [])
    alerts.append({
        "threshold": threshold,
        "direction": direction,
        "created_at": datetime.now(timezone.utc).isoformat()
    })
    user.settings.preferences["price_alerts"] = alerts
    
    # JSONB güncelleme için flag
    from sqlalchemy.orm.attributes import flag_modified
    flag_modified(user.settings, "preferences")
    db.session.commit()
    
    direction_text = "altına düşünce" if direction == "below" else "üstüne çıkınca"
    send_telegram_message(
        chat_id,
        f"✅ Alarm kuruldu!\n\nFiyat *{threshold:.2f} TL/kWh* {direction_text} bildirim alacaksın.",
        token,
        parse_mode="Markdown"
    )
    return jsonify({"status": "ok"}), 200


def handle_delete_alert(chat_id, user, alert_idx, token):
    """Fiyat alarmını sil."""
    if not user or not user.settings:
        return handle_alerts(chat_id, user, token)
    
    try:
        idx = int(alert_idx)
        alerts = user.settings.preferences.get("price_alerts", [])
        
        if 0 <= idx < len(alerts):
            deleted = alerts.pop(idx)
            user.settings.preferences["price_alerts"] = alerts
            
            from sqlalchemy.orm.attributes import flag_modified
            flag_modified(user.settings, "preferences")
            db.session.commit()
            
            send_telegram_message(
                chat_id,
                f"✅ Alarm silindi: {deleted.get('threshold', 0):.2f} TL/kWh",
                token
            )
    except (ValueError, IndexError):
        pass
    
    return handle_alerts(chat_id, user, token)


def handle_report(chat_id, user, token):
    """Rapor seçenekleri."""
    if not user:
        send_telegram_message(chat_id, "❌ Önce /start ile hesabını eşleştir.", token)
        return jsonify({"status": "not_linked"}), 200
    
    msg = (
        "📈 *Enerji Raporları*\n\n"
        "Hangi raporu görmek istersin?"
    )
    
    keyboard = {
        "inline_keyboard": [
            [
                {"text": "📊 Günlük Rapor", "callback_data": "report_daily"},
                {"text": "📈 Haftalık Rapor", "callback_data": "report_weekly"},
            ],
            [
                {"text": "◀️ Geri", "callback_data": "cmd_status"},
            ]
        ]
    }
    
    send_telegram_message(chat_id, msg, token, parse_mode="Markdown", reply_markup=keyboard)
    return jsonify({"status": "ok"}), 200


def handle_report_daily(chat_id, user, token):
    """Günlük enerji raporu."""
    if not user:
        return jsonify({"status": "not_linked"}), 200
    
    today = datetime.now(TR_TIMEZONE).date()
    start_of_day = datetime.combine(today, datetime.min.time()).replace(tzinfo=TR_TIMEZONE)
    
    # Günlük tüketim
    daily_consumption = db.session.query(
        func.sum(DeviceTelemetry.power_w)
    ).join(SmartDevice).filter(
        SmartDevice.organization_id == user.organization_id,
        DeviceTelemetry.time >= start_of_day
    ).scalar() or 0
    
    # kWh'e çevir (ortalama güç * saat sayısı / 1000)
    hours_passed = (datetime.now(TR_TIMEZONE) - start_of_day).total_seconds() / 3600
    daily_kwh = (daily_consumption / max(1, hours_passed)) * hours_passed / 1000
    
    # Ortalama fiyat
    avg_price = db.session.query(
        func.avg(MarketPrice.price)
    ).filter(
        MarketPrice.time >= start_of_day
    ).scalar() or 2.5
    
    estimated_cost = daily_kwh * float(avg_price)
    
    msg = (
        f"📊 *Günlük Rapor - {today.strftime('%d.%m.%Y')}*\n\n"
        f"⚡ Tahmini Tüketim: *{daily_kwh:.2f} kWh*\n"
        f"💰 Tahmini Maliyet: *{estimated_cost:.2f} TL*\n"
        f"📈 Ort. Fiyat: {float(avg_price):.3f} TL/kWh\n\n"
        f"_Veriler anlık tahmindir._"
    )
    
    send_telegram_message(chat_id, msg, token, parse_mode="Markdown")
    return jsonify({"status": "ok"}), 200


def handle_report_weekly(chat_id, user, token):
    """Haftalık enerji raporu."""
    if not user:
        return jsonify({"status": "not_linked"}), 200
    
    today = datetime.now(TR_TIMEZONE).date()
    week_ago = today - timedelta(days=7)
    start_of_week = datetime.combine(week_ago, datetime.min.time()).replace(tzinfo=TR_TIMEZONE)
    
    # Haftalık tüketim (basitleştirilmiş)
    device_count = SmartDevice.query.filter_by(
        organization_id=user.organization_id,
        is_active=True
    ).count()
    
    # Ortalama fiyat
    avg_price = db.session.query(
        func.avg(MarketPrice.price)
    ).filter(
        MarketPrice.time >= start_of_week
    ).scalar() or 2.5
    
    # Tahmini değerler
    estimated_kwh = device_count * 24 * 7 * 0.5  # Cihaz başı günlük 12 kWh tahmin
    estimated_cost = estimated_kwh * float(avg_price)
    
    msg = (
        f"📈 *Haftalık Rapor*\n"
        f"_{week_ago.strftime('%d.%m')} - {today.strftime('%d.%m.%Y')}_\n\n"
        f"🔌 Aktif Cihaz: *{device_count}*\n"
        f"⚡ Tahmini Tüketim: *{estimated_kwh:.1f} kWh*\n"
        f"💰 Tahmini Maliyet: *{estimated_cost:.2f} TL*\n"
        f"📊 Ort. Fiyat: {float(avg_price):.3f} TL/kWh\n\n"
        f"_Detaylı rapor için web panelini ziyaret edin._"
    )
    
    send_telegram_message(chat_id, msg, token, parse_mode="Markdown")
    return jsonify({"status": "ok"}), 200


def handle_automations(chat_id, user, token):
    """Otomasyon durumu."""
    if not user:
        send_telegram_message(chat_id, "❌ Önce /start ile hesabını eşleştir.", token)
        return jsonify({"status": "not_linked"}), 200
    
    automations = Automation.query.filter_by(
        organization_id=user.organization_id
    ).limit(10).all()
    
    if not automations:
        send_telegram_message(
            chat_id,
            "🤖 *Otomasyonlar*\n\nHenüz otomasyon kurulmamış.\n\n_Web panelinden otomasyon oluşturabilirsin._",
            token,
            parse_mode="Markdown"
        )
        return jsonify({"status": "ok"}), 200
    
    lines = ["🤖 *Otomasyonlarınız*\n"]
    
    for auto in automations:
        status = "✅" if auto.is_active else "⏸️"
        last_run = ""
        if auto.last_triggered:
            last_run = f" (Son: {auto.last_triggered.strftime('%d.%m %H:%M')})"
        lines.append(f"{status} {auto.name}{last_run}")
    
    active_count = sum(1 for a in automations if a.is_active)
    lines.append(f"\n_Aktif: {active_count}/{len(automations)}_")
    
    send_telegram_message(chat_id, "\n".join(lines), token, parse_mode="Markdown")
    return jsonify({"status": "ok"}), 200


def handle_settings(chat_id, user, token):
    """Bildirim ayarları."""
    if not user:
        send_telegram_message(chat_id, "❌ Önce /start ile hesabını eşleştir.", token)
        return jsonify({"status": "not_linked"}), 200
    
    # Mevcut ayarları al
    prefs = {}
    if user.settings and user.settings.preferences:
        prefs = user.settings.preferences.get("notifications", {})
    
    device_alerts = prefs.get("device_alerts", True)
    price_alerts = prefs.get("price_alerts", True)
    automation_alerts = prefs.get("automation_alerts", True)
    daily_report = prefs.get("daily_report", False)
    
    msg = (
        "⚙️ *Bildirim Ayarları*\n\n"
        "Hangi bildirimleri almak istiyorsun?"
    )
    
    keyboard = {
        "inline_keyboard": [
            [
                {"text": f"{'✅' if device_alerts else '❌'} Cihaz Alarmları", 
                 "callback_data": f"notif_device_{'off' if device_alerts else 'on'}"},
            ],
            [
                {"text": f"{'✅' if price_alerts else '❌'} Fiyat Alarmları", 
                 "callback_data": f"notif_price_{'off' if price_alerts else 'on'}"},
            ],
            [
                {"text": f"{'✅' if automation_alerts else '❌'} Otomasyon Bildirimleri", 
                 "callback_data": f"notif_automation_{'off' if automation_alerts else 'on'}"},
            ],
            [
                {"text": f"{'✅' if daily_report else '❌'} Günlük Rapor", 
                 "callback_data": f"notif_daily_{'off' if daily_report else 'on'}"},
            ],
            [
                {"text": "◀️ Geri", "callback_data": "cmd_status"},
            ]
        ]
    }
    
    send_telegram_message(chat_id, msg, token, parse_mode="Markdown", reply_markup=keyboard)
    return jsonify({"status": "ok"}), 200


def handle_notification_toggle(chat_id, user, data, token):
    """Bildirim ayarını değiştir."""
    if not user:
        return jsonify({"status": "not_linked"}), 200
    
    # Parse: notif_<type>_<on/off>
    parts = data.split("_")
    if len(parts) < 3:
        return handle_settings(chat_id, user, token)
    
    notif_type = parts[1]
    new_state = parts[2] == "on"
    
    from app.models import UserSettings
    
    if not user.settings:
        user.settings = UserSettings(user_id=user.id, preferences={})
        db.session.add(user.settings)
    
    if not user.settings.preferences:
        user.settings.preferences = {}
    
    if "notifications" not in user.settings.preferences:
        user.settings.preferences["notifications"] = {}
    
    type_map = {
        "device": "device_alerts",
        "price": "price_alerts",
        "automation": "automation_alerts",
        "daily": "daily_report"
    }
    
    key = type_map.get(notif_type)
    if key:
        user.settings.preferences["notifications"][key] = new_state
        
        from sqlalchemy.orm.attributes import flag_modified
        flag_modified(user.settings, "preferences")
        db.session.commit()
    
    return handle_settings(chat_id, user, token)


# ==========================================
# HOME ASSISTANT WEBHOOK ENDPOINTS
# ==========================================

@bp.route("/homeassistant/device", methods=["POST"])
def homeassistant_device_webhook():
    """
    Home Assistant'tan gelen cihaz durum güncellemelerini işle.
    
    Payload format:
    {
        "entity_id": "switch.tapo_plug_1",
        "from_state": "off",
        "to_state": "on",
        "timestamp": "2024-01-15T10:30:00+03:00",
        "attributes": {
            "power": 150.5,
            "energy": 12.34,
            "friendly_name": "Tapo Plug 1"
        }
    }
    """
    try:
        data = request.get_json(silent=True) or {}
        
        entity_id = data.get("entity_id")
        from_state = data.get("from_state")
        to_state = data.get("to_state")
        attributes = data.get("attributes", {})
        
        if not entity_id:
            return jsonify({"error": "entity_id required"}), 400
        
        current_app.logger.info(f"[HA Webhook] Device update: {entity_id} {from_state} -> {to_state}")
        
        # Find device by external_id (entity_id from HA)
        device = SmartDevice.query.filter_by(external_id=entity_id).first()
        
        if not device:
            # Try to find by name match
            friendly_name = attributes.get("friendly_name", "")
            if friendly_name:
                device = SmartDevice.query.filter(
                    SmartDevice.name.ilike(f"%{friendly_name}%")
                ).first()
        
        if device:
            # Update device online status
            device.is_online = True
            device.last_seen = datetime.now(timezone.utc)
            
            # Record state change for savings calculation
            from app.services.savings_service import SavingsService
            if to_state in ("on", "off"):
                SavingsService.record_device_state_change(
                    device_id=str(device.id),
                    new_state=to_state,
                    triggered_by="homeassistant"
                )
            
            # Store telemetry if power/energy data available
            power = attributes.get("power") or attributes.get("current_power_w")
            energy = attributes.get("energy") or attributes.get("total_energy_kwh")
            
            if power is not None:
                telemetry = DeviceTelemetry(
                    time=datetime.now(timezone.utc),
                    device_id=device.id,
                    key="power_w",
                    value=float(power)
                )
                db.session.add(telemetry)
            
            if energy is not None:
                telemetry = DeviceTelemetry(
                    time=datetime.now(timezone.utc),
                    device_id=device.id,
                    key="energy_total_kwh",
                    value=float(energy)
                )
                db.session.add(telemetry)
            
            db.session.commit()
            
            return jsonify({
                "status": "success",
                "device_id": str(device.id),
                "message": f"Device {device.name} updated"
            }), 200
        else:
            current_app.logger.warning(f"[HA Webhook] Device not found: {entity_id}")
            return jsonify({
                "status": "ignored",
                "message": f"Device {entity_id} not found in Awaxen"
            }), 200
            
    except Exception as e:
        current_app.logger.error(f"[HA Webhook] Error: {e}")
        return jsonify({"error": str(e)}), 500


@bp.route("/homeassistant/telemetry", methods=["POST"])
def homeassistant_telemetry_webhook():
    """
    Home Assistant'tan gelen toplu telemetri verilerini işle.
    """
    try:
        data = request.get_json(silent=True) or {}
        devices_data = data.get("devices", [])
        
        if not devices_data:
            return jsonify({"error": "devices array required"}), 400
        
        processed = 0
        
        for device_data in devices_data:
            entity_id = device_data.get("entity_id")
            state = device_data.get("state")
            
            if not entity_id or state is None:
                continue
            
            parts = entity_id.replace("sensor.", "").rsplit("_", 1)
            if len(parts) < 2:
                continue
            
            device_name = parts[0]
            metric = parts[1]
            
            device = SmartDevice.query.filter(
                SmartDevice.external_id.ilike(f"%{device_name}%")
            ).first()
            
            if device:
                key_map = {
                    "power": "power_w",
                    "energy": "energy_total_kwh",
                    "temperature": "temperature_c",
                    "humidity": "humidity_pct"
                }
                telemetry_key = key_map.get(metric, metric)
                
                try:
                    telemetry = DeviceTelemetry(
                        time=datetime.now(timezone.utc),
                        device_id=device.id,
                        key=telemetry_key,
                        value=float(state)
                    )
                    db.session.add(telemetry)
                    processed += 1
                except (ValueError, TypeError):
                    pass
        
        db.session.commit()
        return jsonify({"status": "success", "processed": processed}), 200
        
    except Exception as e:
        current_app.logger.error(f"[HA Telemetry] Error: {e}")
        return jsonify({"error": str(e)}), 500


@bp.route("/homeassistant/discovery", methods=["POST"])
def homeassistant_discovery_webhook():
    """
    Home Assistant'tan gelen cihaz keşif bilgilerini işle.
    """
    try:
        data = request.get_json(silent=True) or {}
        organization_id = data.get("organization_id")
        devices_data = data.get("devices", [])
        
        if not organization_id:
            return jsonify({"error": "organization_id required"}), 400
        
        from app.models import Organization
        org = Organization.query.get(organization_id)
        if not org:
            return jsonify({"error": "Organization not found"}), 404
        
        created = 0
        updated = 0
        
        for device_data in devices_data:
            entity_id = device_data.get("entity_id")
            friendly_name = device_data.get("friendly_name", entity_id)
            device_class = device_data.get("device_class", "switch")
            manufacturer = device_data.get("manufacturer", "unknown")
            model = device_data.get("model", "")
            
            if not entity_id:
                continue
            
            existing = SmartDevice.query.filter_by(
                organization_id=organization_id,
                external_id=entity_id
            ).first()
            
            if existing:
                existing.name = friendly_name
                existing.model = model
                existing.is_online = True
                existing.last_seen = datetime.now(timezone.utc)
                updated += 1
            else:
                new_device = SmartDevice(
                    organization_id=organization_id,
                    external_id=entity_id,
                    name=friendly_name,
                    brand=manufacturer.lower() if manufacturer else "homeassistant",
                    model=model,
                    device_type=device_class,
                    is_sensor=device_class in ("sensor", "binary_sensor"),
                    is_actuator=device_class in ("switch", "light", "climate", "cover"),
                    is_online=True,
                    last_seen=datetime.now(timezone.utc),
                    is_active=True
                )
                db.session.add(new_device)
                created += 1
        
        db.session.commit()
        return jsonify({"status": "success", "created": created, "updated": updated}), 200
        
    except Exception as e:
        current_app.logger.error(f"[HA Discovery] Error: {e}")
        return jsonify({"error": str(e)}), 500
