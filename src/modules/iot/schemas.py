"""
IoT Module - Pydantic Schemas (DTOs)
"""
import uuid
from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field

from src.modules.iot.models import DeviceStatus, DeviceType, GatewayStatus


# ============== Gateway Schemas ==============

class GatewayBase(BaseModel):
    """Base gateway schema."""
    name: str = Field(..., min_length=1, max_length=255)
    serial_number: str = Field(..., min_length=1, max_length=100)
    mac_address: str | None = Field(None, max_length=17)
    ip_address: str | None = Field(None, max_length=45)
    firmware_version: str | None = None
    hardware_version: str | None = None
    config: dict | None = None


class GatewayCreate(GatewayBase):
    """Schema for creating a gateway."""
    asset_id: uuid.UUID | None = None
    mqtt_client_id: str | None = None


class GatewayUpdate(BaseModel):
    """Schema for updating a gateway."""
    name: str | None = Field(None, min_length=1, max_length=255)
    asset_id: uuid.UUID | None = None
    ip_address: str | None = None
    firmware_version: str | None = None
    status: GatewayStatus | None = None
    config: dict | None = None


class GatewayResponse(GatewayBase):
    """Gateway response schema."""
    model_config = ConfigDict(from_attributes=True)
    
    id: uuid.UUID
    organization_id: uuid.UUID
    asset_id: uuid.UUID | None = None
    mqtt_client_id: str | None = None
    status: GatewayStatus
    last_seen_at: datetime | None = None
    created_at: datetime
    updated_at: datetime


class GatewayWithDevices(GatewayResponse):
    """Gateway with devices list."""
    devices: list["DeviceResponse"] = []


# ============== Device Schemas ==============

class DeviceBase(BaseModel):
    """Base device schema."""
    name: str = Field(..., min_length=1, max_length=255)
    device_id: str = Field(..., min_length=1, max_length=100)
    device_type: DeviceType
    manufacturer: str | None = None
    model: str | None = None
    firmware_version: str | None = None
    config: dict | None = None
    metadata_: dict | None = Field(None, alias="metadata")


class DeviceCreate(DeviceBase):
    """Schema for creating a device."""
    asset_id: uuid.UUID
    gateway_id: uuid.UUID | None = None


class DeviceUpdate(BaseModel):
    """Schema for updating a device."""
    name: str | None = Field(None, min_length=1, max_length=255)
    asset_id: uuid.UUID | None = None
    gateway_id: uuid.UUID | None = None
    firmware_version: str | None = None
    status: DeviceStatus | None = None
    config: dict | None = None
    metadata_: dict | None = Field(None, alias="metadata")


class DeviceResponse(DeviceBase):
    """Device response schema."""
    model_config = ConfigDict(from_attributes=True, populate_by_name=True)
    
    id: uuid.UUID
    organization_id: uuid.UUID
    asset_id: uuid.UUID
    gateway_id: uuid.UUID | None = None
    status: DeviceStatus
    last_seen_at: datetime | None = None
    created_at: datetime
    updated_at: datetime


# ============== Telemetry Schemas ==============

class TelemetryDataCreate(BaseModel):
    """Schema for creating telemetry data."""
    device_id: uuid.UUID
    timestamp: datetime
    metric_name: str = Field(..., max_length=50)
    value: Decimal
    unit: str = Field(..., max_length=20)
    quality: int = Field(default=100, ge=0, le=100)
    metadata_: dict | None = Field(None, alias="metadata")


class TelemetryDataBatch(BaseModel):
    """
    Schema for batch telemetry data insertion.
    TRICK: Always use batch inserts for IoT data.
    """
    readings: list[TelemetryDataCreate] = Field(
        ...,
        min_length=1,
        max_length=1000,
        description="Batch of telemetry readings (max 1000)",
    )


class TelemetryDataResponse(BaseModel):
    """Telemetry data response schema."""
    model_config = ConfigDict(from_attributes=True, populate_by_name=True)
    
    id: uuid.UUID
    device_id: uuid.UUID
    timestamp: datetime
    metric_name: str
    value: Decimal
    unit: str
    quality: int
    metadata_: dict | None = Field(None, alias="metadata")


class TelemetryQuery(BaseModel):
    """Query parameters for telemetry data."""
    device_id: uuid.UUID
    metric_name: str | None = None
    start_time: datetime
    end_time: datetime
    limit: int = Field(default=1000, le=10000)


class TelemetryAggregation(BaseModel):
    """Aggregated telemetry data."""
    device_id: uuid.UUID
    metric_name: str
    start_time: datetime
    end_time: datetime
    min_value: Decimal
    max_value: Decimal
    avg_value: Decimal
    sum_value: Decimal
    count: int


# ============== Gateway Pairing Schemas ==============

class GatewayPairingRequest(BaseModel):
    """
    Gateway pairing isteği.
    Kullanıcı gateway ekranında görünen kodu girer.
    """
    pairing_code: str = Field(..., min_length=6, max_length=20, examples=["ABC123"])
    asset_id: uuid.UUID = Field(..., description="Gateway'in bağlanacağı asset")


class GatewayPairingResponse(BaseModel):
    """Gateway pairing yanıtı."""
    message: str
    gateway: GatewayResponse
    status: str = Field(default="paired", examples=["paired"])


class GatewayPairingCodeResponse(BaseModel):
    """Gateway pairing kodu bilgisi."""
    model_config = ConfigDict(from_attributes=True)
    
    id: uuid.UUID
    code: str
    gateway_id: uuid.UUID | None
    expires_at: datetime
    used_at: datetime | None
    is_valid: bool


class GeneratePairingCodeRequest(BaseModel):
    """Pairing kodu oluşturma isteği (Gateway tarafından)."""
    serial_number: str = Field(..., min_length=1, max_length=100)
    mac_address: str | None = None
    firmware_version: str | None = None
    hardware_version: str | None = None


class GeneratePairingCodeResponse(BaseModel):
    """Pairing kodu oluşturma yanıtı."""
    code: str
    expires_at: datetime
    gateway_id: uuid.UUID


# ============== Device Discovery Schemas ==============

class DiscoveredDevice(BaseModel):
    """Gateway tarafından keşfedilen cihaz."""
    external_id: str = Field(..., description="HA entity_id veya device_id")
    name: str
    device_type: DeviceType
    manufacturer: str | None = None
    model: str | None = None
    firmware_version: str | None = None
    capabilities: list[str] = Field(default_factory=list, examples=[["switch", "power_meter"]])


class DeviceDiscoveryRequest(BaseModel):
    """
    Gateway'den gelen cihaz keşif sonuçları.
    Gateway Home Assistant'tan cihazları keşfeder ve bu endpoint'e gönderir.
    """
    gateway_id: uuid.UUID
    devices: list[DiscoveredDevice] = Field(..., min_length=1)


class DeviceDiscoveryResponse(BaseModel):
    """Cihaz keşif yanıtı."""
    message: str
    discovered_count: int
    devices: list[DiscoveredDevice]


class DeviceSetupRequest(BaseModel):
    """
    Keşfedilen cihazı kurulum isteği.
    Kullanıcı her cihaz için zone ve safety profile seçer.
    """
    gateway_id: uuid.UUID
    external_id: str = Field(..., description="Keşfedilen cihazın external_id'si")
    name: str = Field(..., min_length=1, max_length=255, examples=["Salon Prizi"])
    zone_id: uuid.UUID = Field(..., description="Cihazın bağlanacağı zone")
    safety_profile: str = Field(
        default="normal",
        description="critical/high/normal",
        examples=["normal"]
    )
    controllable: bool = Field(default=True, description="Uzaktan kontrol edilebilir mi?")


class DeviceSetupResponse(BaseModel):
    """Cihaz kurulum yanıtı."""
    message: str
    device: DeviceResponse


class BulkDeviceSetupRequest(BaseModel):
    """
    Birden fazla cihazı toplu kurulum.
    Kullanıcı tüm cihazları tek seferde kurabilir.
    """
    gateway_id: uuid.UUID
    devices: list[DeviceSetupRequest] = Field(..., min_length=1)


class BulkDeviceSetupResponse(BaseModel):
    """Toplu cihaz kurulum yanıtı."""
    message: str
    setup_count: int
    devices: list[DeviceResponse]


# ============== Device Control Schemas ==============

class DeviceControlRequest(BaseModel):
    """
    Cihaz kontrol isteği.
    Kullanıcı veya sistem cihazı kontrol etmek için kullanır.
    """
    device_id: uuid.UUID
    action: str = Field(..., examples=["turn_on", "turn_off", "set_temperature"])
    parameters: dict | None = Field(None, examples=[{"temperature": 22}])


class DeviceControlResponse(BaseModel):
    """Cihaz kontrol yanıtı."""
    message: str
    device_id: uuid.UUID
    action: str
    success: bool
    command_id: uuid.UUID | None = Field(None, description="Oluşturulan command ID")


# ============== MQTT Schemas ==============

class MQTTMessage(BaseModel):
    """MQTT message schema for device data ingestion."""
    device_id: str
    timestamp: datetime | None = None
    readings: list[dict] = Field(
        ...,
        description="List of readings: [{metric_name, value, unit}]",
    )


class DeviceHeartbeat(BaseModel):
    """Device heartbeat message."""
    device_id: str
    timestamp: datetime
    status: DeviceStatus = DeviceStatus.ONLINE
    firmware_version: str | None = None
    ip_address: str | None = None


# Forward references
GatewayWithDevices.model_rebuild()
