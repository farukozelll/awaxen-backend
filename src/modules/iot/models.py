"""
IoT Module - Database Models
Device, Gateway, and TelemetryData (TimescaleDB Hypertable).

IMPORTANT: TelemetryData is designed as a TimescaleDB hypertable.
Run the following SQL after table creation:
    SELECT create_hypertable('telemetry_data', 'timestamp');
"""
import uuid
from datetime import UTC, datetime
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
    from src.modules.real_estate.models import Asset


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
    
    # Health SLA tracking
    health_status: Mapped[str] = mapped_column(
        String(20),
        default="unknown",
        nullable=False,
        comment="healthy/degraded/offline/unknown - for SLA monitoring",
    )
    last_data_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        comment="Last telemetry data received timestamp",
    )
    offline_since: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        comment="When gateway went offline (for SLA calculation)",
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
        # lazy="selectin" REMOVED - Performance: Gateway may have 500+ devices
    )
    
    pairing_codes: Mapped[list["GatewayPairingCode"]] = relationship(
        "GatewayPairingCode",
        back_populates="gateway",
        cascade="all, delete-orphan",
        # lazy="selectin" REMOVED - Load explicitly when needed
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
    
    # Metadata - Flexible device attributes
    # Recommended fields:
    #   - ingestion_path: "modbus" | "ha" | "api" | "mqtt" - data source
    #   - coverage_label: "Kat3 odalar" - human-readable coverage (V2: use device_coverage table)
    #   - rated_power_w: 2000 - device rated power for estimation
    #   - installation_date: "2024-01-15" - for warranty/maintenance
    metadata_: Mapped[dict | None] = mapped_column(
        "metadata",
        JSONB,
        nullable=True,
        comment="Flexible attrs: ingestion_path, coverage_label, rated_power_w, etc.",
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


class MetricDefinition(Base, TenantMixin):
    """
    Metric definition for standardized telemetry data.
    
    Prevents metric_name pollution by defining canonical metrics.
    Each organization can have custom metrics but must define them here.
    """
    __tablename__ = "metric_definition"
    
    __table_args__ = (
        UniqueConstraint("organization_id", "name", name="uq_metric_def_org_name"),
        Index("ix_metric_def_device_type", "device_type"),
    )
    
    # Metric identification
    name: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        index=True,
        comment="Canonical metric name (e.g., power, voltage, temperature)",
    )
    
    # Display name for UI
    display_name: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True,
        comment="Human-readable name for UI",
    )
    
    # Unit
    unit: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        comment="Standard unit (e.g., W, V, °C)",
    )
    
    # Device type this metric applies to (optional)
    device_type: Mapped[str | None] = mapped_column(
        String(30),
        nullable=True,
        index=True,
        comment="Device type this metric applies to (null = all)",
    )
    
    # Canonical name for cross-org analytics
    canonical_name: Mapped[str | None] = mapped_column(
        String(50),
        nullable=True,
        comment="Standard name for cross-org comparison (e.g., active_power)",
    )
    
    # Value constraints
    min_value: Mapped[Decimal | None] = mapped_column(
        Numeric(18, 6),
        nullable=True,
        comment="Minimum valid value",
    )
    max_value: Mapped[Decimal | None] = mapped_column(
        Numeric(18, 6),
        nullable=True,
        comment="Maximum valid value",
    )
    
    # Description
    description: Mapped[str | None] = mapped_column(Text, nullable=True)


class TelemetryData(Base):
    """
    Telemetry data model - TimescaleDB Hypertable.
    
    IMPORTANT: This table should be converted to a hypertable:
        SELECT create_hypertable('telemetry_data', 'timestamp');
    
    Stores time-series data: voltage, current, power, temperature, etc.
    
    TRICK: Use batch inserts for high-throughput IoT data.
    Never insert readings one by one - buffer and batch insert.
    
    NOTE: organization_id is denormalized from device for query performance.
    Always populate organization_id when inserting telemetry data.
    
    METRIC NAMING CONSISTENCY:
    - metric_name (VARCHAR): Legacy field, always populated for backward compat
    - metric_definition_id (UUID): Optional FK to metric_definition for standardization
    
    Insert pipeline rule:
    1. If metric_definition_id is provided, derive metric_name from canonical_name
    2. V2: Consider making metric_name nullable and using only metric_definition_id
    """
    __tablename__ = "telemetry_data"
    
    __table_args__ = (
        Index("ix_telemetry_device_time", "device_id", "timestamp"),
        Index("ix_telemetry_time", "timestamp"),
        Index("ix_telemetry_metric", "metric_name", "timestamp"),
        # NEW: Denormalized org index for tenant filtering without joins
        Index("ix_telemetry_org_time", "organization_id", "timestamp"),
        Index("ix_telemetry_org_device_time", "organization_id", "device_id", "timestamp"),
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
    
    # DENORMALIZED: Organization ID for fast tenant filtering
    # Populated from device.organization_id on insert
    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("organization.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        comment="Denormalized from device for query performance",
    )
    
    # Metric identification
    metric_name: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        index=True,
        comment="e.g., voltage, current, power, temperature, humidity",
    )
    
    # Optional reference to metric definition (for validation)
    metric_definition_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("metric_definition.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
        comment="Optional reference to metric definition",
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
        now = datetime.now(UTC)
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


class CoverageType(str, Enum):
    """Device coverage type."""
    PRIMARY = "primary"       # Main coverage area
    SECONDARY = "secondary"   # Partial coverage
    SHARED = "shared"         # Shared with other devices


class DeviceCoverage(Base):
    """
    Device coverage mapping (V2).
    
    Maps which zones/assets a device covers.
    A floor meter may cover multiple rooms.
    A room sensor may cover part of a zone.
    
    Enables accurate reporting:
    - "Which devices cover this area?"
    - "What percentage of this zone is monitored?"
    """
    __tablename__ = "device_coverage"
    
    __table_args__ = (
        Index("idx_coverage_device", "device_id"),
        Index("idx_coverage_asset", "asset_id"),
        Index("idx_coverage_zone", "zone_id"),
        UniqueConstraint(
            "device_id", "asset_id", "zone_id",
            name="uq_device_coverage_target",
        ),
    )
    
    device_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("device.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    
    # Target: Either asset_id or zone_id (zone is more specific)
    asset_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("asset.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )
    
    zone_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("zone.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )
    
    # Coverage ratio (0.0 - 1.0)
    ratio: Mapped[Decimal] = mapped_column(
        Numeric(5, 4),
        default=Decimal("1.0"),
        nullable=False,
        comment="Coverage ratio: 1.0 = full, 0.5 = half",
    )
    
    coverage_type: Mapped[str] = mapped_column(
        String(20),
        default=CoverageType.PRIMARY.value,
        nullable=False,
        comment="primary/secondary/shared",
    )
    
    # Optional notes
    notes: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
        comment="Coverage description, e.g., 'Covers rooms 301-305'",
    )
