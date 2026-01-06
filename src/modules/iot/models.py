"""
IoT Module - Database Models
Device, Gateway, and TelemetryData (TimescaleDB Hypertable).

IMPORTANT: TelemetryData is designed as a TimescaleDB hypertable.
Run the following SQL after table creation:
    SELECT create_hypertable('telemetry_data', 'timestamp');
"""
import uuid
from datetime import datetime
from decimal import Decimal
from enum import Enum
from typing import TYPE_CHECKING

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.core.models import Base, TenantMixin

if TYPE_CHECKING:
    from src.modules.real_estate.models import Asset, Zone


class SafetyProfile(str, Enum):
    """Device safety profile for automation control."""
    CRITICAL = "critical"   # Never auto-control (life safety, medical)
    HIGH = "high"           # Only with explicit user approval
    NORMAL = "normal"       # Can be auto-controlled


class DeviceType(str, Enum):
    """Device type enumeration."""
    SMART_PLUG = "smart_plug"
    ENERGY_METER = "energy_meter"
    WATER_METER = "water_meter"
    GAS_METER = "gas_meter"
    TEMPERATURE_SENSOR = "temperature_sensor"
    HUMIDITY_SENSOR = "humidity_sensor"
    MOTION_SENSOR = "motion_sensor"
    DOOR_SENSOR = "door_sensor"
    RELAY = "relay"
    THERMOSTAT = "thermostat"
    HVAC_CONTROLLER = "hvac_controller"


class DeviceStatus(str, Enum):
    """Device operational status."""
    ONLINE = "online"
    OFFLINE = "offline"
    ERROR = "error"
    MAINTENANCE = "maintenance"
    PROVISIONING = "provisioning"


class GatewayStatus(str, Enum):
    """Gateway operational status."""
    ONLINE = "online"
    OFFLINE = "offline"
    ERROR = "error"
    UPDATING = "updating"
    PROVISIONING = "provisioning"


class Gateway(Base, TenantMixin):
    """
    Gateway model.
    Physical hardware linking assets to cloud via MQTT.
    """
    __tablename__ = "gateway"
    
    __table_args__ = (
        UniqueConstraint("organization_id", "serial_number", name="uq_gateway_serial"),
        Index("ix_gateway_org_status", "organization_id", "status"),
    )
    
    # Identification
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    serial_number: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        index=True,
    )
    mac_address: Mapped[str | None] = mapped_column(String(17), nullable=True)
    
    # Identity key for secure communication
    identity_key: Mapped[str | None] = mapped_column(
        String(255),
        unique=True,
        nullable=True,
        comment="Gateway identity key for secure pairing",
    )
    
    # Location
    asset_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("asset.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    
    # Connection
    mqtt_client_id: Mapped[str | None] = mapped_column(
        String(100),
        unique=True,
        nullable=True,
    )
    ip_address: Mapped[str | None] = mapped_column(String(45), nullable=True)
    
    # Firmware
    firmware_version: Mapped[str | None] = mapped_column(String(50), nullable=True)
    hardware_version: Mapped[str | None] = mapped_column(String(50), nullable=True)
    
    # Status
    status: Mapped[GatewayStatus] = mapped_column(
        String(20),
        default=GatewayStatus.PROVISIONING,
        nullable=False,
        index=True,
    )
    last_seen_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    
    # Configuration
    config: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    
    # Version info
    versions: Mapped[dict | None] = mapped_column(
        JSONB,
        nullable=True,
        default=dict,
        comment="ha_version, agent_version, os_version",
    )
    
    # Relationships
    asset: Mapped["Asset | None"] = relationship(
        "Asset",
        back_populates="gateways",
    )
    
    devices: Mapped[list["Device"]] = relationship(
        "Device",
        back_populates="gateway",
        cascade="all, delete-orphan",
        lazy="selectin",
    )
    
    pairing_codes: Mapped[list["GatewayPairingCode"]] = relationship(
        "GatewayPairingCode",
        back_populates="gateway",
        cascade="all, delete-orphan",
        lazy="selectin",
    )


class Device(Base, TenantMixin):
    """
    Device model.
    Sensors, relays, meters connected to assets.
    Optionally linked to a Gateway.
    """
    __tablename__ = "device"
    
    __table_args__ = (
        UniqueConstraint("organization_id", "device_id", name="uq_device_id"),
        Index("ix_device_org_type", "organization_id", "device_type"),
        Index("ix_device_asset", "asset_id"),
    )
    
    # Identification
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    device_id: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        index=True,
        comment="Unique device identifier (e.g., MAC, serial)",
    )
    device_type: Mapped[DeviceType] = mapped_column(
        String(30),
        nullable=False,
        index=True,
    )
    
    # Location
    asset_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("asset.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    
    # Zone (optional - room/area within asset)
    zone_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("zone.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    
    # Gateway (optional)
    gateway_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("gateway.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    
    # External ID from Home Assistant
    external_id: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
        comment="HA entity_id or device_id",
    )
    
    # Hardware info
    manufacturer: Mapped[str | None] = mapped_column(String(100), nullable=True)
    model: Mapped[str | None] = mapped_column(String(100), nullable=True)
    firmware_version: Mapped[str | None] = mapped_column(String(50), nullable=True)
    
    # Safety and control
    safety_profile: Mapped[str] = mapped_column(
        String(20),
        default=SafetyProfile.NORMAL.value,
        nullable=False,
        comment="critical/high/normal - controls automation behavior",
    )
    controllable: Mapped[bool] = mapped_column(
        Boolean,
        default=True,
        nullable=False,
        comment="Can this device be controlled remotely?",
    )
    
    # Status
    status: Mapped[DeviceStatus] = mapped_column(
        String(20),
        default=DeviceStatus.PROVISIONING,
        nullable=False,
        index=True,
    )
    last_seen_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    
    # Configuration
    config: Mapped[dict | None] = mapped_column(
        JSONB,
        nullable=True,
        comment="Device-specific configuration",
    )
    
    # Metadata
    metadata_: Mapped[dict | None] = mapped_column(
        "metadata",
        JSONB,
        nullable=True,
    )
    
    # Relationships
    asset: Mapped["Asset"] = relationship(
        "Asset",
        back_populates="devices",
    )
    
    gateway: Mapped["Gateway | None"] = relationship(
        "Gateway",
        back_populates="devices",
    )


class TelemetryData(Base):
    """
    Telemetry data model - TimescaleDB Hypertable.
    
    IMPORTANT: This table should be converted to a hypertable:
        SELECT create_hypertable('telemetry_data', 'timestamp');
    
    Stores time-series data: voltage, current, power, temperature, etc.
    
    TRICK: Use batch inserts for high-throughput IoT data.
    Never insert readings one by one - buffer and batch insert.
    """
    __tablename__ = "telemetry_data"
    
    __table_args__ = (
        Index("ix_telemetry_device_time", "device_id", "timestamp"),
        Index("ix_telemetry_time", "timestamp"),
        Index("ix_telemetry_metric", "metric_name", "timestamp"),
    )
    
    # Override base id - use composite key for hypertable
    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    
    # Time - Primary dimension for hypertable
    timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        index=True,
    )
    
    # Device reference
    device_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("device.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    
    # Metric identification
    metric_name: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        index=True,
        comment="e.g., voltage, current, power, temperature, humidity",
    )
    
    # Value
    value: Mapped[Decimal] = mapped_column(
        Numeric(18, 6),
        nullable=False,
    )
    
    # Unit
    unit: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        comment="e.g., V, A, W, kWh, °C, %",
    )
    
    # Quality indicator
    quality: Mapped[int] = mapped_column(
        default=100,
        nullable=False,
        comment="Data quality 0-100",
    )
    
    # Additional data
    metadata_: Mapped[dict | None] = mapped_column(
        "metadata",
        JSONB,
        nullable=True,
    )


# Common metric names for reference
class MetricName:
    """Standard metric names for telemetry data."""
    VOLTAGE = "voltage"
    CURRENT = "current"
    POWER = "power"
    POWER_FACTOR = "power_factor"
    ENERGY = "energy"
    FREQUENCY = "frequency"
    TEMPERATURE = "temperature"
    HUMIDITY = "humidity"
    PRESSURE = "pressure"
    CO2 = "co2"
    WATER_FLOW = "water_flow"
    GAS_FLOW = "gas_flow"


# Common units for reference
class MetricUnit:
    """Standard units for telemetry data."""
    VOLT = "V"
    AMPERE = "A"
    WATT = "W"
    KILOWATT = "kW"
    KILOWATT_HOUR = "kWh"
    HERTZ = "Hz"
    CELSIUS = "°C"
    FAHRENHEIT = "°F"
    PERCENT = "%"
    PPM = "ppm"
    CUBIC_METER = "m³"
    LITER = "L"


class GatewayPairingCode(Base):
    """
    Gateway pairing codes for initial setup.
    
    User enters this code during onboarding to pair gateway with their account.
    Codes expire after a set time and can only be used once.
    """
    __tablename__ = "gateway_pairing_code"
    
    __table_args__ = (
        Index("idx_pairing_code", "code"),
        Index("idx_pairing_expires", "expires_at"),
    )
    
    code: Mapped[str] = mapped_column(
        String(20),
        unique=True,
        nullable=False,
        index=True,
    )
    
    gateway_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("gateway.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )
    
    used_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    
    # Relationships
    gateway: Mapped["Gateway | None"] = relationship(
        "Gateway",
        back_populates="pairing_codes",
    )
    
    @property
    def is_valid(self) -> bool:
        """Check if code is still valid."""
        from datetime import timezone
        now = datetime.now(timezone.utc)
        return self.used_at is None and self.expires_at > now


class DeviceAlias(Base):
    """
    User-defined device aliases/labels.
    
    Allows users to give friendly names to devices.
    Separate from device.name to preserve original discovery name.
    """
    __tablename__ = "device_alias"
    
    __table_args__ = (
        Index("idx_device_alias_device", "device_id"),
    )
    
    device_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("device.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    
    label: Mapped[str] = mapped_column(String(100), nullable=False)
    
    created_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("user.id", ondelete="SET NULL"),
        nullable=True,
    )


class DeviceStateEvent(Base):
    """
    Device state change events for command proof.
    
    Records state transitions (on/off, temperature changes, etc.)
    Used to verify that commands were executed successfully.
    """
    __tablename__ = "device_state_event"
    
    __table_args__ = (
        Index("idx_state_device_ts", "device_id", "ts"),
    )
    
    ts: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        index=True,
    )
    
    device_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("device.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    
    state_key: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        comment="e.g., power, state, temperature",
    )
    
    state_value: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        comment="e.g., on, off, 23.5",
    )
    
    source: Mapped[str] = mapped_column(
        String(20),
        default="ha",
        nullable=False,
        comment="ha/manual/system",
    )
