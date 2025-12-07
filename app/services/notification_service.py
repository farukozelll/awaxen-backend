"""Notification helpers (Telegram, etc.)."""
import requests
from flask import current_app


def send_telegram_notification(user, message: str) -> bool:
    """
    Kullanıcıya Telegram üzerinden bildirim gönder.

    Returns:
        bool: Gönderim başarılı ise True.
    """
    token = current_app.config.get("TELEGRAM_BOT_TOKEN")
    chat_id = getattr(user, "telegram_chat_id", None)

    if not token:
        current_app.logger.warning("[Notification] TELEGRAM_BOT_TOKEN not configured.")
        return False

    if not chat_id:
        current_app.logger.info(
            "[Notification] User %s has no telegram_chat_id. Skipping.", user.email
        )
        return False

    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": f"🔔 Awaxen Bildirim\n\n{message}",
        "parse_mode": "Markdown",
    }

    try:
        response = requests.post(url, json=payload, timeout=10)
        response.raise_for_status()
        return True
    except requests.RequestException as exc:
        current_app.logger.error("[Notification] Telegram send failed: %s", exc)
        return False
