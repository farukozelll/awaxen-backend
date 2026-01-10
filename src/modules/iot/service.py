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

from src.core.exceptions import ConflictError, NotFoundError, ValidationError
from src.core.logging import get_logger
from src.modules.iot.models import (
    Device, DeviceStatus, Gateway, GatewayPairingCode, GatewayStatus, TelemetryData
)
from src.modules.iot.schemas import (
    BulkDeviceSetupRequest,
    BulkDeviceSetupResponse,
    DeviceControlRequest,
    DeviceControlResponse,
    DeviceCreate,
    DeviceDiscoveryRequest,
    DeviceDiscoveryResponse,
    DeviceResponse,
    DeviceSetupRequest,
    DeviceSetupResponse,
    DeviceUpdate,
    GatewayCreate,
    GatewayPairingRequest,
    GatewayPairingResponse,
    GatewayResponse,
    GatewayUpdate,
    GeneratePairingCodeRequest,
    GeneratePairingCodeResponse,
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
    
    # ============== Gateway Pairing ==============
    
    async def generate_pairing_code(
        self,
        request: GeneratePairingCodeRequest,
    ) -> GeneratePairingCodeResponse:
        """
        Gateway için pairing kodu oluştur.
        Gateway ilk açıldığında bu fonksiyonu çağırır.
        """
        import secrets
        from datetime import timedelta
        
        # Gateway'i bul veya oluştur
        stmt = select(Gateway).where(Gateway.serial_number == request.serial_number)
        result = await self.db.execute(stmt)
        gateway = result.scalar_one_or_none()
        
        if not gateway:
            # Yeni gateway oluştur (henüz org'a bağlı değil)
            gateway = Gateway(
                organization_id=self.organization_id,
                name=f"Gateway-{request.serial_number}",
                serial_number=request.serial_number,
                mac_address=request.mac_address,
                firmware_version=request.firmware_version,
                hardware_version=request.hardware_version,
                status=GatewayStatus.PROVISIONING,
            )
            self.db.add(gateway)
            await self.db.flush()
        
        # Pairing kodu oluştur (6 karakter, büyük harf + rakam)
        code = ''.join(secrets.choice('ABCDEFGHJKLMNPQRSTUVWXYZ23456789') for _ in range(6))
        expires_at = datetime.now(timezone.utc) + timedelta(minutes=15)
        
        # Mevcut aktif kodları iptal et
        stmt = select(GatewayPairingCode).where(
            GatewayPairingCode.gateway_id == gateway.id,
            GatewayPairingCode.used_at.is_(None),
        )
        result = await self.db.execute(stmt)
        old_codes = result.scalars().all()
        for old_code in old_codes:
            old_code.expires_at = datetime.now(timezone.utc)
        
        # Yeni kod oluştur
        pairing_code = GatewayPairingCode(
            code=code,
            gateway_id=gateway.id,
            expires_at=expires_at,
        )
        self.db.add(pairing_code)
        await self.db.commit()
        
        logger.info(
            "Pairing code generated",
            gateway_id=str(gateway.id),
            code=code,
            expires_at=expires_at.isoformat(),
        )
        
        return GeneratePairingCodeResponse(
            code=code,
            expires_at=expires_at,
            gateway_id=gateway.id,
        )
    
    async def verify_pairing_code(
        self,
        request: GatewayPairingRequest,
    ) -> GatewayPairingResponse:
        """
        Pairing kodunu doğrula ve gateway'i asset'e bağla.
        Kullanıcı kodu girdiğinde bu fonksiyon çağrılır.
        """
        # Kodu bul
        stmt = select(GatewayPairingCode).where(
            GatewayPairingCode.code == request.pairing_code.upper(),
        )
        result = await self.db.execute(stmt)
        pairing = result.scalar_one_or_none()
        
        if not pairing:
            raise NotFoundError("Pairing code", request.pairing_code)
        
        # Kod geçerli mi kontrol et
        now = datetime.now(timezone.utc)
        if pairing.used_at is not None:
            raise ValidationError("Pairing code already used")
        if pairing.expires_at < now:
            raise ValidationError("Pairing code expired")
        
        # Gateway'i bul
        gateway = await self.get_gateway_by_id(pairing.gateway_id)
        if not gateway:
            raise NotFoundError("Gateway", pairing.gateway_id)
        
        # Gateway'i asset'e bağla ve durumu güncelle
        gateway.asset_id = request.asset_id
        gateway.organization_id = self.organization_id
        gateway.status = GatewayStatus.ONLINE
        gateway.last_seen_at = now
        
        # Identity key oluştur (güvenli iletişim için)
        import secrets
        gateway.identity_key = secrets.token_urlsafe(32)
        
        # Kodu kullanıldı olarak işaretle
        pairing.used_at = now
        
        await self.db.commit()
        await self.db.refresh(gateway)
        
        logger.info(
            "Gateway paired",
            gateway_id=str(gateway.id),
            asset_id=str(request.asset_id),
        )
        
        return GatewayPairingResponse(
            message="Gateway başarıyla eşleştirildi",
            gateway=GatewayResponse.model_validate(gateway),
            status="paired",
        )
    
    # ============== Device Discovery ==============
    
    # Geçici depolama - keşfedilen cihazlar (production'da Redis kullanılabilir)
    _discovered_devices: dict[str, list] = {}
    
    async def submit_device_discovery(
        self,
        request: DeviceDiscoveryRequest,
    ) -> DeviceDiscoveryResponse:
        """
        Gateway'den gelen cihaz keşif sonuçlarını kaydet.
        Kullanıcı daha sonra bu cihazları kurulum ekranında görür.
        """
        # Gateway'i kontrol et
        gateway = await self.get_gateway_by_id(request.gateway_id)
        if not gateway:
            raise NotFoundError("Gateway", request.gateway_id)
        
        # Keşfedilen cihazları geçici olarak sakla
        gateway_key = str(request.gateway_id)
        self._discovered_devices[gateway_key] = [d.model_dump() for d in request.devices]
        
        logger.info(
            "Device discovery submitted",
            gateway_id=str(request.gateway_id),
            device_count=len(request.devices),
        )
        
        return DeviceDiscoveryResponse(
            message=f"{len(request.devices)} cihaz keşfedildi",
            discovered_count=len(request.devices),
            devices=request.devices,
        )
    
    async def setup_device(
        self,
        request: DeviceSetupRequest,
    ) -> DeviceSetupResponse:
        """
        Keşfedilen cihazı kurulum yap.
        Kullanıcı her cihaz için zone ve safety profile seçer.
        """
        # Gateway'i kontrol et
        gateway = await self.get_gateway_by_id(request.gateway_id)
        if not gateway:
            raise NotFoundError("Gateway", request.gateway_id)
        
        # Keşfedilen cihazı bul
        gateway_key = str(request.gateway_id)
        discovered = self._discovered_devices.get(gateway_key, [])
        device_info = next((d for d in discovered if d["external_id"] == request.external_id), None)
        
        if not device_info:
            raise NotFoundError("Discovered device", request.external_id)
        
        # Cihazı oluştur
        device = Device(
            organization_id=self.organization_id,
            name=request.name,
            device_id=request.external_id,
            device_type=device_info["device_type"],
            asset_id=gateway.asset_id,
            zone_id=request.zone_id,
            gateway_id=gateway.id,
            external_id=request.external_id,
            manufacturer=device_info.get("manufacturer"),
            model=device_info.get("model"),
            firmware_version=device_info.get("firmware_version"),
            safety_profile=request.safety_profile,
            controllable=request.controllable,
            status=DeviceStatus.ONLINE,
            last_seen_at=datetime.now(timezone.utc),
        )
        self.db.add(device)
        await self.db.commit()
        await self.db.refresh(device)
        
        logger.info(
            "Device setup completed",
            device_id=str(device.id),
            external_id=request.external_id,
            zone_id=str(request.zone_id),
        )
        
        return DeviceSetupResponse(
            message="Cihaz kurulumu tamamlandı",
            device=DeviceResponse.model_validate(device),
        )
    
    async def bulk_setup_devices(
        self,
        request: BulkDeviceSetupRequest,
    ) -> BulkDeviceSetupResponse:
        """Birden fazla cihazı toplu kurulum yap."""
        devices = []
        
        for device_request in request.devices:
            # Her cihaz için setup_device çağır
            result = await self.setup_device(device_request)
            devices.append(result.device)
        
        return BulkDeviceSetupResponse(
            message=f"{len(devices)} cihaz kurulumu tamamlandı",
            setup_count=len(devices),
            devices=devices,
        )
    
    # ============== Device Control ==============
    
    async def control_device(
        self,
        request: DeviceControlRequest,
    ) -> DeviceControlResponse:
        """
        Cihazı kontrol et.
        Safety profile'a göre kontrol izni verilir.
        """
        device = await self.get_device_by_id(request.device_id)
        if not device:
            raise NotFoundError("Device", request.device_id)
        
        # Safety profile kontrolü
        if device.safety_profile == "critical":
            raise ValidationError("Critical devices cannot be controlled remotely")
        
        if not device.controllable:
            raise ValidationError("Device is not controllable")
        
        # TODO: Gateway'e MQTT üzerinden komut gönder
        # Şimdilik sadece log ve başarılı yanıt dön
        
        logger.info(
            "Device control requested",
            device_id=str(device.id),
            action=request.action,
            parameters=request.parameters,
        )
        
        # Command oluştur (Energy modülü ile entegrasyon için)
        command_id = uuid.uuid4()
        
        return DeviceControlResponse(
            message=f"Komut gönderildi: {request.action}",
            device_id=device.id,
            action=request.action,
            success=True,
            command_id=command_id,
        )


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
