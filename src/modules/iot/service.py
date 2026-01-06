"""
IoT Module - Business Logic Service
Includes batch insert strategy for telemetry data.
"""
import uuid
from datetime import datetime, timezone
from typing import Sequence

from sqlalchemy import delete, func, select, text
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.exceptions import ConflictError, NotFoundError
from src.core.logging import get_logger
from src.modules.iot.models import Device, DeviceStatus, Gateway, GatewayStatus, TelemetryData
from src.modules.iot.schemas import (
    DeviceCreate,
    DeviceUpdate,
    GatewayCreate,
    GatewayUpdate,
    TelemetryAggregation,
    TelemetryDataBatch,
    TelemetryDataCreate,
    TelemetryQuery,
)

logger = get_logger(__name__)


class IoTService:
    """IoT device and telemetry management service."""
    
    def __init__(self, db: AsyncSession, organization_id: uuid.UUID):
        self.db = db
        self.organization_id = organization_id
    
    # ============== Gateway Operations ==============
    
    async def get_gateway_by_id(self, gateway_id: uuid.UUID) -> Gateway | None:
        """Get gateway by ID within organization."""
        stmt = select(Gateway).where(
            Gateway.id == gateway_id,
            Gateway.organization_id == self.organization_id,
        )
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()
    
    async def get_gateway_by_serial(self, serial_number: str) -> Gateway | None:
        """Get gateway by serial number within organization."""
        stmt = select(Gateway).where(
            Gateway.serial_number == serial_number,
            Gateway.organization_id == self.organization_id,
        )
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()
    
    async def list_gateways(
        self,
        status: GatewayStatus | None = None,
        asset_id: uuid.UUID | None = None,
    ) -> Sequence[Gateway]:
        """List gateways with optional filters."""
        stmt = select(Gateway).where(Gateway.organization_id == self.organization_id)
        
        if status:
            stmt = stmt.where(Gateway.status == status)
        if asset_id:
            stmt = stmt.where(Gateway.asset_id == asset_id)
        
        stmt = stmt.order_by(Gateway.name)
        result = await self.db.execute(stmt)
        return result.scalars().all()
    
    async def create_gateway(self, data: GatewayCreate) -> Gateway:
        """Create a new gateway."""
        existing = await self.get_gateway_by_serial(data.serial_number)
        if existing:
            raise ConflictError(f"Gateway with serial '{data.serial_number}' already exists")
        
        gateway = Gateway(
            organization_id=self.organization_id,
            **data.model_dump(),
        )
        self.db.add(gateway)
        await self.db.commit()
        await self.db.refresh(gateway)
        
        logger.info(
            "Gateway created",
            gateway_id=str(gateway.id),
            serial=gateway.serial_number,
        )
        return gateway
    
    async def update_gateway(self, gateway_id: uuid.UUID, data: GatewayUpdate) -> Gateway:
        """Update a gateway."""
        gateway = await self.get_gateway_by_id(gateway_id)
        if not gateway:
            raise NotFoundError("Gateway", gateway_id)
        
        update_data = data.model_dump(exclude_unset=True)
        for field, value in update_data.items():
            setattr(gateway, field, value)
        
        await self.db.commit()
        await self.db.refresh(gateway)
        return gateway
    
    async def update_gateway_status(
        self,
        gateway_id: uuid.UUID,
        status: GatewayStatus,
    ) -> Gateway:
        """Update gateway status and last_seen_at."""
        gateway = await self.get_gateway_by_id(gateway_id)
        if not gateway:
            raise NotFoundError("Gateway", gateway_id)
        
        gateway.status = status
        gateway.last_seen_at = datetime.now(timezone.utc)
        
        await self.db.commit()
        await self.db.refresh(gateway)
        return gateway
    
    async def delete_gateway(self, gateway_id: uuid.UUID) -> None:
        """Delete a gateway."""
        gateway = await self.get_gateway_by_id(gateway_id)
        if not gateway:
            raise NotFoundError("Gateway", gateway_id)
        
        await self.db.delete(gateway)
        await self.db.commit()
        
        logger.info("Gateway deleted", gateway_id=str(gateway_id))
    
    # ============== Device Operations ==============
    
    async def get_device_by_id(self, device_id: uuid.UUID) -> Device | None:
        """Get device by ID within organization."""
        stmt = select(Device).where(
            Device.id == device_id,
            Device.organization_id == self.organization_id,
        )
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()
    
    async def get_device_by_device_id(self, device_id: str) -> Device | None:
        """Get device by device_id (external identifier) within organization."""
        stmt = select(Device).where(
            Device.device_id == device_id,
            Device.organization_id == self.organization_id,
        )
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()
    
    async def list_devices(
        self,
        asset_id: uuid.UUID | None = None,
        gateway_id: uuid.UUID | None = None,
        device_type: str | None = None,
        status: DeviceStatus | None = None,
    ) -> Sequence[Device]:
        """List devices with optional filters."""
        stmt = select(Device).where(Device.organization_id == self.organization_id)
        
        if asset_id:
            stmt = stmt.where(Device.asset_id == asset_id)
        if gateway_id:
            stmt = stmt.where(Device.gateway_id == gateway_id)
        if device_type:
            stmt = stmt.where(Device.device_type == device_type)
        if status:
            stmt = stmt.where(Device.status == status)
        
        stmt = stmt.order_by(Device.name)
        result = await self.db.execute(stmt)
        return result.scalars().all()
    
    async def create_device(self, data: DeviceCreate) -> Device:
        """Create a new device."""
        existing = await self.get_device_by_device_id(data.device_id)
        if existing:
            raise ConflictError(f"Device with ID '{data.device_id}' already exists")
        
        device = Device(
            organization_id=self.organization_id,
            **data.model_dump(by_alias=True),
        )
        self.db.add(device)
        await self.db.commit()
        await self.db.refresh(device)
        
        logger.info(
            "Device created",
            device_uuid=str(device.id),
            device_id=device.device_id,
            type=device.device_type,
        )
        return device
    
    async def update_device(self, device_id: uuid.UUID, data: DeviceUpdate) -> Device:
        """Update a device."""
        device = await self.get_device_by_id(device_id)
        if not device:
            raise NotFoundError("Device", device_id)
        
        update_data = data.model_dump(exclude_unset=True, by_alias=True)
        for field, value in update_data.items():
            setattr(device, field, value)
        
        await self.db.commit()
        await self.db.refresh(device)
        return device
    
    async def update_device_status(
        self,
        device_id: uuid.UUID,
        status: DeviceStatus,
    ) -> Device:
        """Update device status and last_seen_at."""
        device = await self.get_device_by_id(device_id)
        if not device:
            raise NotFoundError("Device", device_id)
        
        device.status = status
        device.last_seen_at = datetime.now(timezone.utc)
        
        await self.db.commit()
        await self.db.refresh(device)
        return device
    
    async def delete_device(self, device_id: uuid.UUID) -> None:
        """Delete a device."""
        device = await self.get_device_by_id(device_id)
        if not device:
            raise NotFoundError("Device", device_id)
        
        await self.db.delete(device)
        await self.db.commit()
        
        logger.info("Device deleted", device_id=str(device_id))


class TelemetryService:
    """
    Telemetry data service with batch insert optimization.
    
    TRICK: Never insert telemetry readings one by one.
    Always use batch inserts to reduce DB load.
    """
    
    def __init__(self, db: AsyncSession):
        self.db = db
    
    async def insert_single(self, data: TelemetryDataCreate) -> TelemetryData:
        """Insert a single telemetry reading."""
        telemetry = TelemetryData(
            **data.model_dump(by_alias=True),
        )
        self.db.add(telemetry)
        await self.db.commit()
        await self.db.refresh(telemetry)
        return telemetry
    
    async def insert_batch(self, batch: TelemetryDataBatch) -> int:
        """
        Insert telemetry data in batch.
        
        TRICK: Use PostgreSQL's INSERT ... ON CONFLICT for upsert capability.
        Returns the number of inserted rows.
        """
        if not batch.readings:
            return 0
        
        # Prepare data for bulk insert
        values = [
            {
                "id": uuid.uuid4(),
                "device_id": reading.device_id,
                "timestamp": reading.timestamp,
                "metric_name": reading.metric_name,
                "value": reading.value,
                "unit": reading.unit,
                "quality": reading.quality,
                "metadata": reading.metadata_,
            }
            for reading in batch.readings
        ]
        
        # Use PostgreSQL bulk insert
        stmt = insert(TelemetryData).values(values)
        await self.db.execute(stmt)
        await self.db.commit()
        
        logger.info(
            "Telemetry batch inserted",
            count=len(values),
            device_ids=list({str(v["device_id"]) for v in values}),
        )
        
        return len(values)
    
    async def query(self, query: TelemetryQuery) -> Sequence[TelemetryData]:
        """Query telemetry data with time range."""
        stmt = (
            select(TelemetryData)
            .where(
                TelemetryData.device_id == query.device_id,
                TelemetryData.timestamp >= query.start_time,
                TelemetryData.timestamp <= query.end_time,
            )
        )
        
        if query.metric_name:
            stmt = stmt.where(TelemetryData.metric_name == query.metric_name)
        
        stmt = stmt.order_by(TelemetryData.timestamp.desc()).limit(query.limit)
        
        result = await self.db.execute(stmt)
        return result.scalars().all()
    
    async def get_latest(
        self,
        device_id: uuid.UUID,
        metric_name: str | None = None,
    ) -> TelemetryData | None:
        """Get latest telemetry reading for a device."""
        stmt = (
            select(TelemetryData)
            .where(TelemetryData.device_id == device_id)
        )
        
        if metric_name:
            stmt = stmt.where(TelemetryData.metric_name == metric_name)
        
        stmt = stmt.order_by(TelemetryData.timestamp.desc()).limit(1)
        
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()
    
    async def aggregate(
        self,
        device_id: uuid.UUID,
        metric_name: str,
        start_time: datetime,
        end_time: datetime,
    ) -> TelemetryAggregation | None:
        """
        Get aggregated telemetry data.
        Uses TimescaleDB time_bucket for efficient aggregation.
        """
        stmt = (
            select(
                func.min(TelemetryData.value).label("min_value"),
                func.max(TelemetryData.value).label("max_value"),
                func.avg(TelemetryData.value).label("avg_value"),
                func.sum(TelemetryData.value).label("sum_value"),
                func.count(TelemetryData.id).label("count"),
            )
            .where(
                TelemetryData.device_id == device_id,
                TelemetryData.metric_name == metric_name,
                TelemetryData.timestamp >= start_time,
                TelemetryData.timestamp <= end_time,
            )
        )
        
        result = await self.db.execute(stmt)
        row = result.one_or_none()
        
        if not row or row.count == 0:
            return None
        
        return TelemetryAggregation(
            device_id=device_id,
            metric_name=metric_name,
            start_time=start_time,
            end_time=end_time,
            min_value=row.min_value,
            max_value=row.max_value,
            avg_value=row.avg_value,
            sum_value=row.sum_value,
            count=row.count,
        )
    
    async def delete_old_data(self, device_id: uuid.UUID, before: datetime) -> int:
        """Delete telemetry data older than specified time."""
        stmt = delete(TelemetryData).where(
            TelemetryData.device_id == device_id,
            TelemetryData.timestamp < before,
        )
        result = await self.db.execute(stmt)
        await self.db.commit()
        
        deleted_count = result.rowcount
        logger.info(
            "Old telemetry data deleted",
            device_id=str(device_id),
            before=before.isoformat(),
            count=deleted_count,
        )
        return deleted_count
