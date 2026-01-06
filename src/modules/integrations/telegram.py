"""
Telegram Bot Integration
Sends notifications and alerts via Telegram.
"""
import asyncio
from typing import Any

import httpx

from src.core.config import settings
from src.core.logging import get_logger

logger = get_logger(__name__)

TELEGRAM_API_BASE = "https://api.telegram.org/bot"


class TelegramService:
    """
    Telegram Bot Service for sending notifications.
    
    Usage:
        telegram = TelegramService()
        await telegram.send_message(chat_id, "Hello!")
    """
    
    def __init__(self, token: str | None = None):
        """
        Initialize Telegram service.
        
        Args:
            token: Bot token. Uses settings if not provided.
        """
        self.token = token or settings.telegram_bot_token
        self.base_url = f"{TELEGRAM_API_BASE}{self.token}"
        self._client: httpx.AsyncClient | None = None
    
    @property
    def is_configured(self) -> bool:
        """Check if Telegram is properly configured."""
        return bool(self.token)
    
    async def _get_client(self) -> httpx.AsyncClient:
        """Get or create HTTP client."""
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(timeout=30.0)
        return self._client
    
    async def close(self) -> None:
        """Close HTTP client."""
        if self._client and not self._client.is_closed:
            await self._client.aclose()
    
    async def _request(self, method: str, **kwargs) -> dict[str, Any]:
        """
        Make a request to Telegram API.
        
        Args:
            method: API method name
            **kwargs: Method parameters
            
        Returns:
            API response
        """
        if not self.is_configured:
            logger.warning("Telegram not configured, skipping request")
            return {"ok": False, "error": "Not configured"}
        
        client = await self._get_client()
        url = f"{self.base_url}/{method}"
        
        try:
            response = await client.post(url, json=kwargs)
            response.raise_for_status()
            data = response.json()
            
            if not data.get("ok"):
                logger.error(
                    "Telegram API error",
                    method=method,
                    error=data.get("description"),
                )
            
            return data
        except httpx.HTTPError as e:
            logger.error("Telegram request failed", method=method, error=str(e))
            return {"ok": False, "error": str(e)}
    
    async def send_message(
        self,
        chat_id: int | str,
        text: str,
        parse_mode: str = "HTML",
        disable_notification: bool = False,
    ) -> dict[str, Any]:
        """
        Send a text message.
        
        Args:
            chat_id: Telegram chat ID
            text: Message text
            parse_mode: HTML or Markdown
            disable_notification: Send silently
            
        Returns:
            API response
        """
        return await self._request(
            "sendMessage",
            chat_id=chat_id,
            text=text,
            parse_mode=parse_mode,
            disable_notification=disable_notification,
        )
    
    async def send_alert(
        self,
        chat_id: int | str,
        title: str,
        message: str,
        level: str = "INFO",
    ) -> dict[str, Any]:
        """
        Send a formatted alert message.
        
        Args:
            chat_id: Telegram chat ID
            title: Alert title
            message: Alert message
            level: Alert level (INFO, WARNING, ERROR, CRITICAL)
        """
        emoji_map = {
            "INFO": "ℹ️",
            "WARNING": "⚠️",
            "ERROR": "❌",
            "CRITICAL": "🚨",
            "SUCCESS": "✅",
        }
        emoji = emoji_map.get(level.upper(), "📢")
        
        text = f"""
{emoji} <b>{title}</b>

{message}

<i>Level: {level}</i>
<i>Service: Awaxen Backend</i>
"""
        return await self.send_message(chat_id, text.strip())
    
    async def send_device_alert(
        self,
        chat_id: int | str,
        device_name: str,
        device_id: str,
        alert_type: str,
        value: float | None = None,
        unit: str = "",
    ) -> dict[str, Any]:
        """
        Send IoT device alert.
        
        Args:
            chat_id: Telegram chat ID
            device_name: Device name
            device_id: Device ID
            alert_type: Type of alert
            value: Current value
            unit: Value unit
        """
        value_str = f"{value} {unit}" if value is not None else "N/A"
        
        text = f"""
🔔 <b>Device Alert</b>

<b>Device:</b> {device_name}
<b>ID:</b> <code>{device_id}</code>
<b>Alert:</b> {alert_type}
<b>Value:</b> {value_str}

<i>Awaxen IoT Platform</i>
"""
        return await self.send_message(chat_id, text.strip())
    
    async def send_energy_report(
        self,
        chat_id: int | str,
        date: str,
        total_consumption: float,
        total_cost: float,
        currency: str = "TRY",
    ) -> dict[str, Any]:
        """
        Send daily energy report.
        
        Args:
            chat_id: Telegram chat ID
            date: Report date
            total_consumption: Total kWh
            total_cost: Total cost
            currency: Currency code
        """
        text = f"""
📊 <b>Daily Energy Report</b>

<b>Date:</b> {date}
<b>Total Consumption:</b> {total_consumption:.2f} kWh
<b>Total Cost:</b> {total_cost:.2f} {currency}

<i>Awaxen Energy Platform</i>
"""
        return await self.send_message(chat_id, text.strip())
    
    async def get_me(self) -> dict[str, Any]:
        """Get bot information."""
        return await self._request("getMe")
    
    async def get_updates(self, offset: int | None = None) -> dict[str, Any]:
        """Get bot updates (messages)."""
        params = {}
        if offset:
            params["offset"] = offset
        return await self._request("getUpdates", **params)


# Singleton instance
_telegram_service: TelegramService | None = None


def get_telegram_service() -> TelegramService:
    """Get or create Telegram service singleton."""
    global _telegram_service
    if _telegram_service is None:
        _telegram_service = TelegramService()
    return _telegram_service


async def send_telegram_notification(
    chat_id: int | str,
    message: str,
    level: str = "INFO",
) -> bool:
    """
    Convenience function to send a notification.
    
    Returns:
        True if sent successfully
    """
    service = get_telegram_service()
    result = await service.send_alert(chat_id, "Notification", message, level)
    return result.get("ok", False)
