"""
Integration Background Tasks
Scheduled tasks for external service integrations.
"""
from datetime import date

from src.worker import celery_app
from src.core.logging import get_logger

logger = get_logger(__name__)


@celery_app.task(name="src.tasks.integrations.fetch_daily_prices")
def fetch_daily_prices() -> dict:
    """
    Fetch and cache daily electricity prices from EPİAŞ.
    Runs daily at 00:05 via Celery Beat.
    """
    import asyncio
    from src.modules.integrations.epias import get_epias_service
    
    async def _fetch():
        service = get_epias_service()
        prices = await service.get_day_ahead_prices(date.today())
        avg = await service.get_average_price(date.today())
        
        logger.info(
            "Daily prices fetched",
            date=date.today().isoformat(),
            price_count=len(prices),
            average=float(avg) if avg else None,
        )
        
        return {
            "status": "completed",
            "date": date.today().isoformat(),
            "price_count": len(prices),
            "average_price": float(avg) if avg else None,
        }
    
    return asyncio.run(_fetch())


@celery_app.task(name="src.tasks.integrations.send_daily_report")
def send_daily_report(chat_id: str) -> dict:
    """
    Send daily energy report via Telegram.
    """
    import asyncio
    from src.modules.integrations.telegram import get_telegram_service
    from src.modules.integrations.epias import get_epias_service
    
    async def _send():
        telegram = get_telegram_service()
        epias = get_epias_service()
        
        if not telegram.is_configured:
            return {"status": "skipped", "reason": "Telegram not configured"}
        
        avg_price = await epias.get_average_price(date.today())
        
        await telegram.send_message(
            chat_id=chat_id,
            text=f"""
📊 <b>Günlük Enerji Raporu</b>

<b>Tarih:</b> {date.today().isoformat()}
<b>Ortalama Elektrik Fiyatı:</b> {float(avg_price):.2f} TRY/MWh

<i>Awaxen Energy Platform</i>
""",
        )
        
        return {"status": "sent", "chat_id": chat_id}
    
    return asyncio.run(_send())


@celery_app.task(name="src.tasks.integrations.send_alert")
def send_telegram_alert(
    chat_id: str,
    title: str,
    message: str,
    level: str = "INFO",
) -> dict:
    """
    Send alert notification via Telegram.
    """
    import asyncio
    from src.modules.integrations.telegram import get_telegram_service
    
    async def _send():
        telegram = get_telegram_service()
        
        if not telegram.is_configured:
            logger.warning("Telegram not configured, skipping alert")
            return {"status": "skipped", "reason": "Telegram not configured"}
        
        result = await telegram.send_alert(chat_id, title, message, level)
        
        return {
            "status": "sent" if result.get("ok") else "failed",
            "chat_id": chat_id,
        }
    
    return asyncio.run(_send())


@celery_app.task(name="src.tasks.integrations.check_price_threshold")
def check_price_threshold(
    threshold: float,
    chat_id: str | None = None,
) -> dict:
    """
    Check if current electricity price exceeds threshold.
    Sends alert if configured.
    """
    import asyncio
    from src.modules.integrations.epias import get_epias_service
    from src.modules.integrations.telegram import get_telegram_service
    
    async def _check():
        epias = get_epias_service()
        price = await epias.get_hourly_price()
        
        if price is None:
            return {"status": "error", "reason": "Price not available"}
        
        price_float = float(price)
        exceeded = price_float > threshold
        
        result = {
            "status": "completed",
            "current_price": price_float,
            "threshold": threshold,
            "exceeded": exceeded,
        }
        
        if exceeded and chat_id:
            telegram = get_telegram_service()
            if telegram.is_configured:
                await telegram.send_alert(
                    chat_id=chat_id,
                    title="⚡ Yüksek Elektrik Fiyatı",
                    message=f"Mevcut fiyat: {price_float:.2f} TRY/MWh\nEşik: {threshold:.2f} TRY/MWh",
                    level="WARNING",
                )
                result["alert_sent"] = True
        
        return result
    
    return asyncio.run(_check())
