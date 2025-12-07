"""
Telegram Webhook Manager - Otomatik ngrok URL algılama ve webhook güncelleme.

Docker Compose içinde ngrok servisi çalışırken, bu modül:
1. Ngrok API'den güncel public URL'yi alır
2. Telegram Bot API'ye webhook'u kaydeder
3. Kullanıcıya bildirim gönderir
"""
import time
import requests
from flask import current_app


def get_ngrok_public_url(max_retries: int = 10, retry_delay: int = 3) -> str | None:
    """
    Ngrok API'den public URL'yi al.
    Docker içinde ngrok servisi 'awaxen_ngrok' olarak çalışır.
    """
    # Docker içindeyken ngrok container'ına, dışarıdayken localhost'a bağlan
    ngrok_api_urls = [
        "http://ngrok:4040/api/tunnels",      # Docker network içinden
        "http://localhost:4040/api/tunnels",  # Lokal geliştirme
    ]
    
    for attempt in range(max_retries):
        for api_url in ngrok_api_urls:
            try:
                response = requests.get(api_url, timeout=5)
                if response.status_code == 200:
                    data = response.json()
                    tunnels = data.get("tunnels", [])
                    for tunnel in tunnels:
                        if tunnel.get("proto") == "https":
                            return tunnel.get("public_url")
            except requests.RequestException:
                continue
        
        if attempt < max_retries - 1:
            time.sleep(retry_delay)
    
    return None


def set_telegram_webhook(public_url: str) -> bool:
    """Telegram Bot API'ye webhook URL'sini kaydet."""
    token = current_app.config.get("TELEGRAM_BOT_TOKEN")
    if not token:
        current_app.logger.warning("[WebhookManager] TELEGRAM_BOT_TOKEN not configured")
        return False
    
    webhook_url = f"{public_url}/webhooks/telegram"
    api_url = f"https://api.telegram.org/bot{token}/setWebhook"
    
    try:
        response = requests.post(api_url, json={"url": webhook_url}, timeout=10)
        result = response.json()
        
        if result.get("ok"):
            current_app.logger.info(f"[WebhookManager] Webhook set: {webhook_url}")
            return True
        else:
            current_app.logger.error(f"[WebhookManager] Failed: {result}")
            return False
    except requests.RequestException as e:
        current_app.logger.error(f"[WebhookManager] Request error: {e}")
        return False


def send_startup_notification(message: str) -> bool:
    """Admin kullanıcıya startup bildirimi gönder."""
    from app.models import User
    from app.services.notification_service import send_telegram_notification
    
    # İlk super_admin kullanıcıyı bul
    admin = User.query.join(User.role).filter_by(code="super_admin").first()
    if not admin:
        admin = User.query.first()
    
    if admin and admin.telegram_chat_id:
        return send_telegram_notification(admin, message)
    return False


def auto_setup_webhook(app=None):
    """
    Uygulama başladığında otomatik webhook kurulumu.
    
    1. Ngrok URL'sini bekle ve al
    2. Telegram webhook'unu güncelle
    3. Admin'e bildirim gönder
    """
    if app is None:
        from flask import current_app as app
    
    with app.app_context():
        app.logger.info("[WebhookManager] Ngrok URL bekleniyor...")
        
        public_url = get_ngrok_public_url()
        
        if not public_url:
            app.logger.warning("[WebhookManager] Ngrok URL alınamadı. Manuel ayarlama gerekebilir.")
            return False
        
        app.logger.info(f"[WebhookManager] Ngrok URL: {public_url}")
        
        # Webhook'u ayarla
        if set_telegram_webhook(public_url):
            # Başarı bildirimi
            send_startup_notification(
                f"✅ *Sistem Online!*\n\n"
                f"🌐 Webhook güncellendi\n"
                f"🔗 `{public_url}`\n\n"
                f"Tüm bildirimler aktif."
            )
            return True
        
        return False
