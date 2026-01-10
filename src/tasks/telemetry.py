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
    Clean up telemetry data older than specified days using TimescaleDB drop_chunks.
    Runs daily via Celery Beat.
    
    PERFORMANS: TimescaleDB drop_chunks kullanılır, standart DELETE değil.
    DELETE milyonlarca satırda çok yavaştır ve DB'yi kilitler.
    drop_chunks ise chunk bazlı silme yapar, çok hızlıdır.
    """
    import asyncio
    from sqlalchemy import text
    from src.core.database import async_session_maker
    
    async def _cleanup():
        async with async_session_maker() as session:
            cutoff = datetime.now(timezone.utc) - timedelta(days=days)
            
            # TimescaleDB drop_chunks kullan (standart DELETE yerine)
            # Bu fonksiyon chunk bazlı silme yapar, çok daha hızlıdır
            try:
                # TimescaleDB drop_chunks - eski chunk'ları siler
                result = await session.execute(
                    text("""
                        SELECT drop_chunks(
                            'telemetry_data',
                            older_than => :cutoff_interval
                        )
                    """),
                    {"cutoff_interval": f"{days} days"}
                )
                await session.commit()
                
                dropped_chunks = result.fetchall()
                chunk_count = len(dropped_chunks) if dropped_chunks else 0
                
                logger.info(
                    "Telemetry cleanup completed with drop_chunks",
                    cutoff=cutoff.isoformat(),
                    chunks_dropped=chunk_count,
                )
                
                return {
                    "status": "completed",
                    "method": "drop_chunks",
                    "cutoff": cutoff.isoformat(),
                    "chunks_dropped": chunk_count,
                }
                
            except Exception as e:
                # TimescaleDB yoksa veya hypertable değilse fallback
                logger.warning(
                    "drop_chunks failed, table may not be a hypertable",
                    error=str(e),
                )
                
                # Fallback: Batch delete (yine de tek seferde silme)
                from src.modules.iot.models import TelemetryData
                from sqlalchemy import delete
                
                stmt = delete(TelemetryData).where(
                    TelemetryData.timestamp < cutoff
                )
                result = await session.execute(stmt)
                await session.commit()
                
                deleted_count = result.rowcount
                logger.info(
                    "Telemetry cleanup completed with DELETE",
                    cutoff=cutoff.isoformat(),
                    deleted_count=deleted_count,
                )
                
                return {
                    "status": "completed",
                    "method": "delete",
                    "cutoff": cutoff.isoformat(),
                    "deleted_count": deleted_count,
                }
    
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
