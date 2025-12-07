"""
Webhook endpoints (Telegram Bot Commands).

Desteklenen Komutlar:
- /start: Hesap eşleştirme
- /status: Sistem durumu
- /balance: Cüzdan bakiyesi
- /devices: Cihaz listesi
- /help: Yardım menüsü
"""
import requests
from flask import Blueprint, current_app, jsonify, request

from app.extensions import db
from app.models import User, SmartDevice, Wallet

bp = Blueprint("webhooks", __name__)

TELEGRAM_API_URL = "https://api.telegram.org/bot"


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
    
    elif text.startswith("/balance"):
        return handle_balance(chat_id, user, token)
    
    elif text.startswith("/devices"):
        return handle_devices(chat_id, user, token)
    
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
                {"text": "💰 Bakiye", "callback_data": "cmd_balance"},
            ],
            [
                {"text": "🔌 Cihazlar", "callback_data": "cmd_devices"},
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
    
    msg = (
        f"📊 *Sistem Durumu*\n\n"
        f"👤 Kullanıcı: {user.full_name or user.email}\n"
        f"🏠 Organizasyon: {user.organization.name if user.organization else 'N/A'}\n\n"
        f"🔌 Toplam Cihaz: {total_devices}\n"
        f"✅ Çevrimiçi: {online_devices}\n"
        f"❌ Çevrimdışı: {total_devices - online_devices}\n\n"
        f"💰 Bakiye: {balance:.2f} AWX"
    )
    
    send_telegram_message(chat_id, msg, token, parse_mode="Markdown")
    return jsonify({"status": "ok"}), 200


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
        "/start - Hesap eşleştirme\n"
        "/status - Sistem durumu\n"
        "/balance - Cüzdan bakiyesi\n"
        "/devices - Cihaz listesi\n"
        "/help - Bu yardım menüsü\n\n"
        "_Sorularınız için: support@awaxen.com_"
    )
    send_telegram_message(chat_id, msg, token, parse_mode="Markdown")
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
