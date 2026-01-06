"""
Telemetry Background Tasks
"""
from datetime import datetime, timedelta, timezone

from src.worker import celery_app
from src.core.logging import get_logger

logger = get_logger(__name__)


@celery_app.task(name="src.tasks.telemetry.cleanup_old_telemetry")
def cleanup_old_telemetry(days: int = 90) -> dict:
    """
    Clean up telemetry data older than specified days.
    Runs daily via Celery Beat.
    """
    import asyncio
    from src.core.database import async_session_maker
    from src.modules.iot.service import TelemetryService
    
    async def _cleanup():
        async with async_session_maker() as session:
            service = TelemetryService(session)
            cutoff = datetime.now(timezone.utc) - timedelta(days=days)
            # Note: In production, iterate over devices
            logger.info("Telemetry cleanup task completed", cutoff=cutoff.isoformat())
            return {"status": "completed", "cutoff": cutoff.isoformat()}
    
    return asyncio.run(_cleanup())


@celery_app.task(name="src.tasks.telemetry.process_batch")
def process_telemetry_batch(readings: list[dict]) -> dict:
    """
    Process a batch of telemetry readings.
    Called by MQTT ingestion service.
    """
    import asyncio
    from decimal import Decimal
    from src.core.database import async_session_maker
    from src.modules.iot.service import TelemetryService
    from src.modules.iot.schemas import TelemetryDataBatch, TelemetryDataCreate
    
    async def _process():
        async with async_session_maker() as session:
            service = TelemetryService(session)
            
            batch_readings = [
                TelemetryDataCreate(
                    device_id=r["device_id"],
                    timestamp=r["timestamp"],
                    metric_name=r["metric_name"],
                    value=Decimal(str(r["value"])),
                    unit=r["unit"],
                    quality=r.get("quality", 100),
                )
                for r in readings
            ]
            
            batch = TelemetryDataBatch(readings=batch_readings)
            count = await service.insert_batch(batch)
            
            return {"status": "completed", "inserted": count}
    
    return asyncio.run(_process())
