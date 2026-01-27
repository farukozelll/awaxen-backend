"""
IoT MQTT Ingestion Service
Async MQTT client for ingesting device telemetry data.

TRICK: Use batch inserts - buffer readings and flush periodically.
NEVER perform blocking I/O inside async functions.
"""
import asyncio
import uuid
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

import aiomqtt
from pydantic import ValidationError

from src.core.config import settings
from src.core.logging import get_logger
from src.modules.iot.schemas import MQTTMessage, TelemetryDataBatch, TelemetryDataCreate

logger = get_logger(__name__)


class TelemetryBuffer:
    """
    Buffer for telemetry readings.
    Implements batch insert strategy to reduce DB load.
    """
    
    def __init__(
        self,
        max_size: int = 100,
        flush_interval: float = 5.0,
    ):
        self.max_size = max_size
        self.flush_interval = flush_interval
        self._buffer: list[TelemetryDataCreate] = []
        self._lock = asyncio.Lock()
        self._flush_callback: Any = None
    
    def set_flush_callback(self, callback: Any) -> None:
        """Set callback function for flushing buffer to DB."""
        self._flush_callback = callback
    
    async def add(self, reading: TelemetryDataCreate) -> None:
        """Add a reading to the buffer."""
        async with self._lock:
            self._buffer.append(reading)
            
            if len(self._buffer) >= self.max_size:
                await self._flush()
    
    async def _flush(self) -> None:
        """Flush buffer to database."""
        if not self._buffer or not self._flush_callback:
            return
        
        readings = self._buffer.copy()
        self._buffer.clear()
        
        try:
            batch = TelemetryDataBatch(readings=readings)
            await self._flush_callback(batch)
            logger.debug("Telemetry buffer flushed", count=len(readings))
        except Exception as e:
            logger.error("Failed to flush telemetry buffer", error=str(e))
            # Re-add to buffer on failure (with limit to prevent memory issues)
            if len(self._buffer) < self.max_size * 2:
                self._buffer.extend(readings)
    
    async def flush(self) -> None:
        """Public method to force flush."""
        async with self._lock:
            await self._flush()
    
    async def periodic_flush(self) -> None:
        """Periodically flush buffer."""
        while True:
            await asyncio.sleep(self.flush_interval)
            await self.flush()


class MQTTIngestionService:
    """
    MQTT client for ingesting IoT device data.
    
    Topics:
    - awaxen/devices/{device_id}/telemetry - Device telemetry data
    - awaxen/devices/{device_id}/status - Device status updates
    - awaxen/gateways/{gateway_id}/status - Gateway status updates
    """
    
    TELEMETRY_TOPIC = "awaxen/devices/+/telemetry"
    DEVICE_STATUS_TOPIC = "awaxen/devices/+/status"
    GATEWAY_STATUS_TOPIC = "awaxen/gateways/+/status"
    
    def __init__(self):
        self.buffer = TelemetryBuffer(
            max_size=settings.telemetry_batch_size,
            flush_interval=settings.telemetry_flush_interval,
        )
        self._running = False
        self._client: aiomqtt.Client | None = None
        self._session_factory: Any = None
    
    async def start(self, session_factory: Any = None) -> None:
        """
        Start MQTT client and begin listening.
        
        Args:
            session_factory: Async session factory for DB operations.
                           Each flush creates a fresh session to avoid stale connections.
        """
        self._session_factory = session_factory
        self.buffer.set_flush_callback(self._flush_to_db)
        self._running = True
        
        # Start periodic flush task
        asyncio.create_task(self.buffer.periodic_flush())
        
        logger.info(
            "Starting MQTT ingestion service",
            broker=settings.mqtt_broker_host,
            port=settings.mqtt_broker_port,
        )
        
        while self._running:
            try:
                async with aiomqtt.Client(
                    hostname=settings.mqtt_broker_host,
                    port=settings.mqtt_broker_port,
                    username=settings.mqtt_username,
                    password=settings.mqtt_password,
                    identifier=settings.mqtt_client_id,
                ) as client:
                    self._client = client
                    
                    # Subscribe to topics
                    await client.subscribe(self.TELEMETRY_TOPIC)
                    await client.subscribe(self.DEVICE_STATUS_TOPIC)
                    await client.subscribe(self.GATEWAY_STATUS_TOPIC)
                    
                    logger.info("MQTT client connected and subscribed")
                    
                    async for message in client.messages:
                        await self._handle_message(message)
                        
            except aiomqtt.MqttError as e:
                logger.error("MQTT connection error", error=str(e))
                if self._running:
                    await asyncio.sleep(5)  # Reconnect delay
            except Exception as e:
                logger.error("Unexpected error in MQTT client", error=str(e))
                if self._running:
                    await asyncio.sleep(5)
    
    async def stop(self) -> None:
        """Stop MQTT client."""
        self._running = False
        await self.buffer.flush()
        logger.info("MQTT ingestion service stopped")
    
    async def _flush_to_db(self, batch) -> None:
        """
        Flush telemetry batch to database with fresh session.
        
        KRITIK: Her flush işleminde yeni session oluşturulur.
        Bu, uzun süreli MQTT bağlantılarında 'stale session' hatasını önler.
        """
        if not self._session_factory:
            logger.warning("No session factory configured, skipping DB flush")
            return
        
        try:
            # Her flush'ta taze session kullan (Stale Session Fix)
            async with self._session_factory() as session:
                from src.modules.iot.service import TelemetryService
                service = TelemetryService(session)
                count = await service.insert_batch(batch)
                logger.debug("MQTT telemetry flushed to DB", count=count)
        except Exception as e:
            logger.error("Failed to flush MQTT telemetry to DB", error=str(e))
            raise
    
    async def _handle_message(self, message: aiomqtt.Message) -> None:
        """Handle incoming MQTT message."""
        topic = str(message.topic)
        payload = message.payload
        
        try:
            if "/telemetry" in topic:
                await self._handle_telemetry(topic, payload)
            elif "/devices/" in topic and "/status" in topic:
                await self._handle_device_status(topic, payload)
            elif "/gateways/" in topic and "/status" in topic:
                await self._handle_gateway_status(topic, payload)
        except Exception as e:
            logger.error(
                "Error handling MQTT message",
                topic=topic,
                error=str(e),
            )
    
    async def _handle_telemetry(self, topic: str, payload: bytes) -> None:
        """Handle telemetry message."""
        import orjson
        
        # Extract device_id from topic: awaxen/devices/{device_id}/telemetry
        parts = topic.split("/")
        if len(parts) < 4:
            return
        
        external_device_id = parts[2]
        
        try:
            data = orjson.loads(payload)
            msg = MQTTMessage(
                device_id=external_device_id,
                timestamp=data.get("timestamp"),
                readings=data.get("readings", []),
            )
        except (orjson.JSONDecodeError, ValidationError) as e:
            logger.warning("Invalid telemetry payload", error=str(e))
            return
        
        timestamp = msg.timestamp or datetime.now(UTC)
        
        # Note: In production, you'd look up the internal device UUID
        # from the external device_id. For now, we'll skip invalid UUIDs.
        try:
            device_uuid = uuid.UUID(external_device_id)
        except ValueError:
            logger.warning("Invalid device UUID in topic", device_id=external_device_id)
            return
        
        for reading in msg.readings:
            telemetry = TelemetryDataCreate(
                device_id=device_uuid,
                timestamp=timestamp,
                metric_name=reading.get("metric_name", "unknown"),
                value=Decimal(str(reading.get("value", 0))),
                unit=reading.get("unit", ""),
                quality=reading.get("quality", 100),
            )
            await self.buffer.add(telemetry)
    
    async def _handle_device_status(self, topic: str, payload: bytes) -> None:
        """Handle device status message."""
        # Implementation for device status updates
        logger.debug("Device status received", topic=topic)
    
    async def _handle_gateway_status(self, topic: str, payload: bytes) -> None:
        """Handle gateway status message."""
        # Implementation for gateway status updates
        logger.debug("Gateway status received", topic=topic)
    
    async def publish_command(
        self,
        topic: str,
        payload: dict[str, Any],
    ) -> bool:
        """
        Publish a command to a gateway via MQTT.
        
        Args:
            topic: MQTT topic (e.g., "awaxen/gateways/{serial}/command")
            payload: Command payload dict
            
        Returns:
            True if published successfully, False otherwise
        """
        import orjson
        
        if not self._client:
            logger.warning("MQTT client not connected, cannot publish command")
            return False
        
        try:
            message = orjson.dumps(payload)
            await self._client.publish(topic, message, qos=1)
            
            logger.info(
                "MQTT command published",
                topic=topic,
                command_id=payload.get("command_id"),
                action=payload.get("action"),
            )
            return True
            
        except Exception as e:
            logger.error(
                "Failed to publish MQTT command",
                topic=topic,
                error=str(e),
            )
            return False
    
    async def publish_device_command(
        self,
        gateway_serial: str,
        device_id: str,
        action: str,
        parameters: dict[str, Any] | None = None,
        command_id: str | None = None,
    ) -> bool:
        """
        Convenience method to publish a device control command.
        
        Args:
            gateway_serial: Gateway serial number
            device_id: Device ID (external or internal)
            action: Action to perform (turn_on, turn_off, set_brightness, etc.)
            parameters: Optional action parameters
            command_id: Optional command ID for tracking
            
        Returns:
            True if published successfully
        """
        topic = f"awaxen/gateways/{gateway_serial}/command"
        payload = {
            "command_id": command_id or str(uuid.uuid4()),
            "device_id": device_id,
            "action": action,
            "parameters": parameters or {},
            "timestamp": datetime.now(UTC).isoformat(),
        }
        
        return await self.publish_command(topic, payload)


# Singleton instance
mqtt_service = MQTTIngestionService()


async def get_mqtt_service() -> MQTTIngestionService:
    """Get MQTT service singleton (for dependency injection)."""
    return mqtt_service
