# AWAXEN Backend Database Schema

## Overview
This document outlines the complete database schema for the AWAXEN backend system. The system uses PostgreSQL with SQLAlchemy ORM and follows a multi-tenant architecture.

## Core Architecture

### Base Model (`src/core/models.py`)
All models inherit from the `Base` class which provides:
- **UUID Primary Key**: `id` (UUID, auto-generated)
- **Timestamps**: `created_at`, `updated_at` (UTC timezone)
- **Automatic Table Naming**: CamelCase to snake_case conversion
- **Tenant Mixin**: `organization_id` for multi-tenant isolation

### Naming Conventions
- **Tables**: snake_case (e.g., `organization_user`)
- **Indexes**: `ix_<table>_<column>` 
- **Unique Constraints**: `uq_<table>_<column>`
- **Foreign Keys**: `fk_<table>_<column>_<referred_table>`

---

## Module Schemas

## 1. Authentication Module (`src/modules/auth/models.py`)

### Users Table
```sql
user (
    id UUID PRIMARY KEY,
    auth0_id VARCHAR(100) UNIQUE,
    email VARCHAR(255) UNIQUE NOT NULL,
    hashed_password VARCHAR(255),
    full_name VARCHAR(255),
    first_name VARCHAR(100),
    last_name VARCHAR(100),
    phone VARCHAR(50),
    telegram_username VARCHAR(100),
    telegram_chat_id VARCHAR(50),
    country VARCHAR(100),
    city VARCHAR(100),
    district VARCHAR(100),
    address TEXT,
    postal_code VARCHAR(20),
    notification_settings JSONB,
    consent_settings JSONB,
    kvkk_accepted BOOLEAN DEFAULT FALSE,
    kvkk_accepted_at TIMESTAMPTZ,
    marketing_consent BOOLEAN DEFAULT FALSE,
    marketing_consent_at TIMESTAMPTZ,
    onboarding_completed BOOLEAN DEFAULT FALSE,
    onboarding_step INTEGER,
    fcm_token VARCHAR(500),
    referral_code VARCHAR(20) UNIQUE,
    referred_by_code VARCHAR(20),
    is_active BOOLEAN DEFAULT TRUE,
    is_superuser BOOLEAN DEFAULT FALSE,
    is_verified BOOLEAN DEFAULT FALSE,
    status VARCHAR(20) DEFAULT 'active',
    last_login TIMESTAMPTZ,
    last_login_ip VARCHAR(45),
    last_login_user_agent VARCHAR(500),
    mfa_enabled BOOLEAN DEFAULT FALSE,
    preferences JSONB,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
)
```

### Organizations Table
```sql
organization (
    id UUID PRIMARY KEY,
    name VARCHAR(255) NOT NULL,
    slug VARCHAR(100) UNIQUE NOT NULL,
    description TEXT,
    organization_type VARCHAR(50),
    company_size INTEGER,
    email VARCHAR(255),
    phone VARCHAR(50),
    city VARCHAR(100),
    district VARCHAR(100),
    neighborhood VARCHAR(100),
    street VARCHAR(255),
    postal_code VARCHAR(20),
    country VARCHAR(100) DEFAULT 'Türkiye',
    latitude DECIMAL(10,7),
    longitude DECIMAL(10,7),
    address TEXT,
    tax_number VARCHAR(20),
    tax_office VARCHAR(100),
    billing_email VARCHAR(255),
    billing_address TEXT,
    tier VARCHAR(20) DEFAULT 'free',
    status VARCHAR(20) DEFAULT 'active',
    suspended_at TIMESTAMPTZ,
    suspended_reason VARCHAR(255),
    is_active BOOLEAN DEFAULT TRUE,
    settings JSONB,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
)
```

### Roles Table
```sql
role (
    id UUID PRIMARY KEY,
    name VARCHAR(100) NOT NULL,
    code VARCHAR(50) UNIQUE NOT NULL,
    description TEXT,
    permissions TEXT[] DEFAULT '{}',
    is_system BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
)
```

### Organization Users Table (Many-to-Many)
```sql
organization_user (
    id UUID PRIMARY KEY,
    user_id UUID NOT NULL REFERENCES user(id) ON DELETE CASCADE,
    organization_id UUID NOT NULL REFERENCES organization(id) ON DELETE CASCADE,
    role_id UUID REFERENCES role(id) ON DELETE SET NULL,
    is_default BOOLEAN DEFAULT FALSE,
    joined_at TIMESTAMPTZ NOT NULL,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(user_id, organization_id)
)
```

### Organization Modules Table
```sql
organization_module (
    id UUID PRIMARY KEY,
    organization_id UUID NOT NULL REFERENCES organization(id) ON DELETE CASCADE,
    module_code VARCHAR(50) NOT NULL,
    is_active BOOLEAN DEFAULT TRUE,
    settings JSONB,
    activated_at TIMESTAMPTZ NOT NULL,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(organization_id, module_code)
)
```

### Invitations Table
```sql
invitation (
    id UUID PRIMARY KEY,
    email VARCHAR(255) NOT NULL,
    token VARCHAR(100) UNIQUE NOT NULL,
    organization_id UUID NOT NULL REFERENCES organization(id) ON DELETE CASCADE,
    role_code VARCHAR(20) DEFAULT 'user',
    invited_by_id UUID REFERENCES user(id) ON DELETE SET NULL,
    is_used BOOLEAN DEFAULT FALSE,
    used_at TIMESTAMPTZ,
    expires_at TIMESTAMPTZ NOT NULL,
    message TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
)
```

---

## 2. Billing Module (`src/modules/billing/models.py`)

### Wallets Table
```sql
wallet (
    id UUID PRIMARY KEY,
    wallet_type VARCHAR(20) DEFAULT 'company',
    organization_id UUID REFERENCES organization(id) ON DELETE CASCADE,
    user_id UUID REFERENCES user(id) ON DELETE CASCADE,
    balance DECIMAL(18,2) DEFAULT 0.00,
    currency VARCHAR(3) DEFAULT 'TRY',
    is_active BOOLEAN DEFAULT TRUE,
    credit_limit DECIMAL(18,2),
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(organization_id, currency),
    UNIQUE(user_id, currency),
    CHECK (
        (wallet_type = 'company' AND organization_id IS NOT NULL AND user_id IS NULL)
        OR
        (wallet_type = 'personal' AND user_id IS NOT NULL)
    )
)
```

### Wallet Transactions Table
```sql
wallet_transaction (
    id UUID PRIMARY KEY,
    wallet_id UUID NOT NULL REFERENCES wallet(id) ON DELETE CASCADE,
    transaction_type VARCHAR(20) NOT NULL,
    amount DECIMAL(18,2) NOT NULL,
    balance_after DECIMAL(18,2) NOT NULL,
    status VARCHAR(20) DEFAULT 'completed',
    reference VARCHAR(100),
    description TEXT,
    metadata JSONB,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
)
-- Note: Renamed from 'transaction' to 'wallet_transaction' to avoid PostgreSQL reserved word conflicts
```

---
## 3. Compliance Module (`src/modules/compliance/models.py`)

### Consent Table
```sql
consent (
    id UUID PRIMARY KEY,
    user_id UUID NOT NULL REFERENCES user(id) ON DELETE CASCADE,
    organization_id UUID REFERENCES organization(id) ON DELETE CASCADE,
    consent_type VARCHAR(50) NOT NULL,
    version VARCHAR(20) NOT NULL,
    accepted_at TIMESTAMPTZ,
    revoked_at TIMESTAMPTZ,
    metadata JSONB,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
)
```

### Audit Logs Table
```sql
audit_log (
    id UUID PRIMARY KEY,
    organization_id UUID REFERENCES organization(id) ON DELETE CASCADE,
    actor_user_id UUID REFERENCES user(id) ON DELETE SET NULL,
    action VARCHAR(100) NOT NULL,
    entity_type VARCHAR(50) NOT NULL,
    entity_id UUID,
    payload_hash VARCHAR(64),
    payload JSONB,
    changes JSONB,
    ip_address VARCHAR(45),
    user_agent TEXT,
    request_id VARCHAR(36),
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
)
```

---

## 4. Energy Module (`src/modules/energy/models.py`)

### Recommendations Table
```sql
recommendation (
    id UUID PRIMARY KEY,
    asset_id UUID NOT NULL REFERENCES asset(id) ON DELETE CASCADE,
    target_device_id UUID REFERENCES device(id) ON DELETE SET NULL,
    reason VARCHAR(30) NOT NULL,
    expected_saving_try DECIMAL(12,2),
    expected_saving_kwh DECIMAL(12,4),
    status VARCHAR(20) DEFAULT 'created',
    risk_level VARCHAR(20) DEFAULT 'low',
    expires_at TIMESTAMPTZ,
    payload JSONB,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
)
-- Risk levels: low (timing/standby), medium (HVAC setpoint), high (automation/cut)
```

### Commands Table
```sql
command (
    id UUID PRIMARY KEY,
    recommendation_id UUID REFERENCES recommendation(id) ON DELETE SET NULL,
    gateway_id UUID NOT NULL REFERENCES gateway(id) ON DELETE CASCADE,
    device_id UUID NOT NULL REFERENCES device(id) ON DELETE CASCADE,
    action VARCHAR(30) NOT NULL,
    params JSONB,
    status VARCHAR(20) DEFAULT 'queued',
    idempotency_key VARCHAR(100) UNIQUE NOT NULL,
    sent_at TIMESTAMPTZ,
    acked_at TIMESTAMPTZ,
    finished_at TIMESTAMPTZ,
    error TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
)
```

### Command Proofs Table
```sql
command_proof (
    id UUID PRIMARY KEY,
    command_id UUID NOT NULL REFERENCES command(id) ON DELETE CASCADE,
    proof_type VARCHAR(30) NOT NULL,
    proof_payload JSONB NOT NULL,
    verified_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
)
```

### Reward Ledger Table
```sql
reward_ledger (
    id UUID PRIMARY KEY,
    user_id UUID NOT NULL REFERENCES user(id) ON DELETE CASCADE,
    asset_id UUID REFERENCES asset(id) ON DELETE SET NULL,
    event_type VARCHAR(30) NOT NULL,
    amount_awx INTEGER NOT NULL,
    expires_at TIMESTAMPTZ,
    reference_type VARCHAR(30),
    reference_id UUID,
    description TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(event_type, reference_type, reference_id)
)
```

### Streaks Table
```sql
streak (
    id UUID PRIMARY KEY,
    user_id UUID NOT NULL REFERENCES user(id) ON DELETE CASCADE,
    streak_type VARCHAR(30) NOT NULL,
    current_count INTEGER DEFAULT 0,
    longest_count INTEGER DEFAULT 0,
    last_date TIMESTAMPTZ,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(user_id, streak_type)
)
```

### Saving Verification Table
```sql
saving_verification (
    id UUID PRIMARY KEY,
    recommendation_id UUID NOT NULL UNIQUE REFERENCES recommendation(id) ON DELETE CASCADE,
    baseline_window_start TIMESTAMPTZ NOT NULL,
    baseline_window_end TIMESTAMPTZ NOT NULL,
    baseline_kwh DECIMAL(12,4) NOT NULL,
    compare_window_start TIMESTAMPTZ NOT NULL,
    compare_window_end TIMESTAMPTZ NOT NULL,
    compare_kwh DECIMAL(12,4) NOT NULL,
    saved_kwh DECIMAL(12,4) NOT NULL,
    saved_try DECIMAL(12,2) NOT NULL,
    confidence DECIMAL(5,2) NOT NULL,
    method VARCHAR(20) NOT NULL,
    verified_at TIMESTAMPTZ NOT NULL,
    verification_details JSONB,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
)
```

### Energy Price Table (EPİAŞ)
```sql
energy_price (
    id UUID PRIMARY KEY,
    timestamp TIMESTAMPTZ NOT NULL,
    market VARCHAR(20) NOT NULL,
    price_try_mwh DECIMAL(12,2) NOT NULL,
    -- GENERATED COLUMN: Auto-computed from price_try_mwh
    price_try_kwh DECIMAL(8,6) GENERATED ALWAYS AS (price_try_mwh / 1000) STORED,
    region VARCHAR(20) DEFAULT 'TR',
    source VARCHAR(50) NOT NULL,
    volume_mwh DECIMAL(14,2),
    metadata JSONB,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(timestamp, market, region)
)
-- Consider hypertable: SELECT create_hypertable('energy_price', 'timestamp');
-- NOTE: price_try_kwh is a generated column - do NOT insert/update it directly
```

### Tariff Profile Table
```sql
tariff_profile (
    id UUID PRIMARY KEY,
    organization_id UUID NOT NULL REFERENCES organization(id) ON DELETE CASCADE,
    name VARCHAR(100) NOT NULL,
    tariff_type VARCHAR(20) NOT NULL,
    rate_peak DECIMAL(8,6),
    rate_day DECIMAL(8,6),
    rate_night DECIMAL(8,6),
    rate_single DECIMAL(8,6),
    peak_hours JSONB,
    day_hours JSONB,
    night_hours JSONB,
    distribution_fee DECIMAL(8,6) DEFAULT 0,
    tax_rate DECIMAL(5,4) DEFAULT 0.20,
    demand_charge_try_kw DECIMAL(10,2),
    valid_from TIMESTAMPTZ NOT NULL,
    valid_to TIMESTAMPTZ,
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(organization_id, name)
)
```

### Tariff Assignment Table
```sql
tariff_assignment (
    id UUID PRIMARY KEY,
    tariff_profile_id UUID NOT NULL REFERENCES tariff_profile(id) ON DELETE CASCADE,
    asset_id UUID REFERENCES asset(id) ON DELETE CASCADE,
    zone_id UUID REFERENCES zone(id) ON DELETE CASCADE,
    device_id UUID REFERENCES device(id) ON DELETE CASCADE,
    priority INTEGER DEFAULT 10,
    valid_from TIMESTAMPTZ NOT NULL,
    valid_to TIMESTAMPTZ,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
)
-- Priority: device(30) > zone(20) > asset(10)
-- Constraint: Only ONE active assignment per target at any time

-- Partial unique indexes to prevent duplicate active assignments:
CREATE UNIQUE INDEX uq_tariff_assign_device_active 
    ON tariff_assignment (device_id, valid_from) 
    WHERE device_id IS NOT NULL AND valid_to IS NULL;

CREATE UNIQUE INDEX uq_tariff_assign_zone_active 
    ON tariff_assignment (zone_id, valid_from) 
    WHERE zone_id IS NOT NULL AND valid_to IS NULL;

CREATE UNIQUE INDEX uq_tariff_assign_asset_active 
    ON tariff_assignment (asset_id, valid_from) 
    WHERE asset_id IS NOT NULL AND valid_to IS NULL;
```

---

## 5. IoT Module (`src/modules/iot/models.py`)

### Gateways Table
```sql
gateway (
    id UUID PRIMARY KEY,
    organization_id UUID NOT NULL REFERENCES organization(id) ON DELETE CASCADE,
    name VARCHAR(255) NOT NULL,
    serial_number VARCHAR(100) NOT NULL,
    mac_address VARCHAR(17),
    identity_key VARCHAR(255) UNIQUE,
    asset_id UUID REFERENCES asset(id) ON DELETE SET NULL,
    mqtt_client_id VARCHAR(100) UNIQUE,
    ip_address VARCHAR(45),
    firmware_version VARCHAR(50),
    hardware_version VARCHAR(50),
    status VARCHAR(20) DEFAULT 'provisioning',
    last_seen_at TIMESTAMPTZ,
    health_status VARCHAR(20) DEFAULT 'unknown',
    last_data_at TIMESTAMPTZ,
    offline_since TIMESTAMPTZ,
    config JSONB,
    versions JSONB,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(organization_id, serial_number)
)
-- Health SLA: healthy/degraded/offline/unknown
```

### Devices Table
```sql
device (
    id UUID PRIMARY KEY,
    organization_id UUID NOT NULL REFERENCES organization(id) ON DELETE CASCADE,
    name VARCHAR(255) NOT NULL,
    device_id VARCHAR(100) NOT NULL,
    device_type VARCHAR(30) NOT NULL,
    asset_id UUID NOT NULL REFERENCES asset(id) ON DELETE CASCADE,
    zone_id UUID REFERENCES zone(id) ON DELETE SET NULL,
    gateway_id UUID REFERENCES gateway(id) ON DELETE SET NULL,
    external_id VARCHAR(255),
    manufacturer VARCHAR(100),
    model VARCHAR(100),
    firmware_version VARCHAR(50),
    safety_profile VARCHAR(20) DEFAULT 'normal',
    controllable BOOLEAN DEFAULT TRUE,
    status VARCHAR(20) DEFAULT 'provisioning',
    last_seen_at TIMESTAMPTZ,
    config JSONB,
    metadata JSONB,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(organization_id, device_id)
)
```

### Metric Definition Table
```sql
metric_definition (
    id UUID PRIMARY KEY,
    organization_id UUID NOT NULL REFERENCES organization(id) ON DELETE CASCADE,
    name VARCHAR(50) NOT NULL,
    display_name VARCHAR(100),
    unit VARCHAR(20) NOT NULL,
    device_type VARCHAR(30),
    canonical_name VARCHAR(50),
    min_value DECIMAL(18,6),
    max_value DECIMAL(18,6),
    description TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(organization_id, name)
)
```

### Telemetry Data Table (TimescaleDB Hypertable)
```sql
telemetry_data (
    id UUID PRIMARY KEY,
    timestamp TIMESTAMPTZ NOT NULL,
    device_id UUID NOT NULL REFERENCES device(id) ON DELETE CASCADE,
    organization_id UUID NOT NULL REFERENCES organization(id) ON DELETE CASCADE,
    metric_name VARCHAR(50) NOT NULL,
    metric_definition_id UUID REFERENCES metric_definition(id) ON DELETE SET NULL,
    value DECIMAL(18,6) NOT NULL,
    unit VARCHAR(20) NOT NULL,
    quality INTEGER DEFAULT 100,
    metadata JSONB,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
)
-- Convert to hypertable: SELECT create_hypertable('telemetry_data', 'timestamp');
-- Indexes: (organization_id, timestamp), (organization_id, device_id, timestamp)
```

### Gateway Pairing Codes Table
```sql
gateway_pairing_code (
    id UUID PRIMARY KEY,
    code VARCHAR(20) UNIQUE NOT NULL,
    gateway_id UUID REFERENCES gateway(id) ON DELETE SET NULL,
    expires_at TIMESTAMPTZ NOT NULL,
    used_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
)
```

### Device Aliases Table
```sql
device_alias (
    id UUID PRIMARY KEY,
    device_id UUID NOT NULL REFERENCES device(id) ON DELETE CASCADE,
    label VARCHAR(100) NOT NULL,
    created_by_user_id UUID REFERENCES user(id) ON DELETE SET NULL,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
)
```

### Device State Events Table
```sql
device_state_event (
    id UUID PRIMARY KEY,
    ts TIMESTAMPTZ NOT NULL,
    device_id UUID NOT NULL REFERENCES device(id) ON DELETE CASCADE,
    state_key VARCHAR(50) NOT NULL,
    state_value VARCHAR(255) NOT NULL,
    source VARCHAR(20) DEFAULT 'ha',
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
)
```

### Device Coverage Table (V2)
```sql
device_coverage (
    id UUID PRIMARY KEY,
    device_id UUID NOT NULL REFERENCES device(id) ON DELETE CASCADE,
    asset_id UUID REFERENCES asset(id) ON DELETE CASCADE,
    zone_id UUID REFERENCES zone(id) ON DELETE CASCADE,
    ratio DECIMAL(5,4) DEFAULT 1.0,
    coverage_type VARCHAR(20) DEFAULT 'primary',
    notes TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(device_id, asset_id, zone_id)
)
-- Coverage types: primary/secondary/shared
-- Enables: "Which devices cover this area?" and accurate reporting
```

---

## 6. Real Estate Module (`src/modules/real_estate/models.py`)

### Assets Table (Hierarchical)
```sql
asset (
    id UUID PRIMARY KEY,
    organization_id UUID NOT NULL REFERENCES organization(id) ON DELETE CASCADE,
    name VARCHAR(255) NOT NULL,
    code VARCHAR(100) NOT NULL,
    description TEXT,
    asset_type VARCHAR(20) NOT NULL,
    parent_id UUID REFERENCES asset(id) ON DELETE CASCADE,
    address TEXT,
    latitude DECIMAL(10,7),
    longitude DECIMAL(10,7),
    area_sqm DECIMAL(12,2),
    floor_number INTEGER,
    status VARCHAR(30) DEFAULT 'active',
    metadata JSONB,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(organization_id, code)
)
```

### Leases Table
```sql
lease (
    id UUID PRIMARY KEY,
    organization_id UUID NOT NULL REFERENCES organization(id) ON DELETE CASCADE,
    asset_id UUID NOT NULL REFERENCES asset(id) ON DELETE CASCADE,
    tenant_name VARCHAR(255) NOT NULL,
    tenant_email VARCHAR(255),
    tenant_phone VARCHAR(50),
    tenant_id_number VARCHAR(50),
    contract_number VARCHAR(100) UNIQUE,
    start_date DATE NOT NULL,
    end_date DATE NOT NULL,
    monthly_rent DECIMAL(12,2) NOT NULL,
    deposit_amount DECIMAL(12,2),
    currency VARCHAR(3) DEFAULT 'TRY',
    status VARCHAR(30) DEFAULT 'draft',
    signed_at TIMESTAMPTZ,
    terminated_at TIMESTAMPTZ,
    notes TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
)
```

### Zones Table
```sql
zone (
    id UUID PRIMARY KEY,
    asset_id UUID NOT NULL REFERENCES asset(id) ON DELETE CASCADE,
    name VARCHAR(100) NOT NULL,
    zone_type VARCHAR(30) DEFAULT 'room',
    description TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
)
```

### Asset Memberships Table
```sql
asset_membership (
    id UUID PRIMARY KEY,
    asset_id UUID NOT NULL REFERENCES asset(id) ON DELETE CASCADE,
    user_id UUID NOT NULL REFERENCES user(id) ON DELETE CASCADE,
    relation VARCHAR(30) NOT NULL,
    scopes TEXT[] DEFAULT '{}',
    revoked_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(asset_id, user_id, relation)
)
```

### Tenancies Table
```sql
tenancy (
    id UUID PRIMARY KEY,
    asset_id UUID NOT NULL REFERENCES asset(id) ON DELETE CASCADE,
    tenant_user_id UUID NOT NULL REFERENCES user(id) ON DELETE CASCADE,
    start_at TIMESTAMPTZ NOT NULL,
    end_at TIMESTAMPTZ,
    status VARCHAR(20) DEFAULT 'active',
    handover_mode VARCHAR(30),
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
)
```

### Handover Tokens Table
```sql
handover_token (
    id UUID PRIMARY KEY,
    asset_id UUID NOT NULL REFERENCES asset(id) ON DELETE CASCADE,
    token VARCHAR(100) UNIQUE NOT NULL,
    expires_at TIMESTAMPTZ NOT NULL,
    used_at TIMESTAMPTZ,
    used_by_user_id UUID REFERENCES user(id) ON DELETE SET NULL,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
)
```

---

## 7. Notifications Module (`src/modules/notifications/models.py`)

### Notifications Table
```sql
notification (
    id UUID PRIMARY KEY,
    user_id UUID NOT NULL REFERENCES user(id) ON DELETE CASCADE,
    organization_id UUID REFERENCES organization(id) ON DELETE CASCADE,
    type VARCHAR(20) DEFAULT 'info',
    priority VARCHAR(20) DEFAULT 'medium',
    title VARCHAR(255) NOT NULL,
    message TEXT NOT NULL,
    data JSONB,
    is_read BOOLEAN DEFAULT FALSE,
    read_at TIMESTAMPTZ,
    channels_sent JSONB,
    source_type VARCHAR(50),
    source_id UUID,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
)
```

### User FCM Tokens Table
```sql
user_fcm_token (
    id UUID PRIMARY KEY,
    user_id UUID NOT NULL REFERENCES user(id) ON DELETE CASCADE,
    token VARCHAR(500) UNIQUE NOT NULL,
    device_type VARCHAR(20) DEFAULT 'web',
    device_name VARCHAR(100),
    is_active BOOLEAN DEFAULT TRUE,
    last_used_at TIMESTAMPTZ,
    failed_count INTEGER DEFAULT 0,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
)
```

### Notification Preferences Table
```sql
notification_preference (
    id UUID PRIMARY KEY,
    user_id UUID NOT NULL REFERENCES user(id) ON DELETE CASCADE UNIQUE,
    push_enabled BOOLEAN DEFAULT TRUE,
    telegram_enabled BOOLEAN DEFAULT TRUE,
    email_enabled BOOLEAN DEFAULT FALSE,
    type_preferences JSONB,
    quiet_hours_enabled BOOLEAN DEFAULT FALSE,
    quiet_hours_start VARCHAR(5),
    quiet_hours_end VARCHAR(5),
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
)
```

---

## 8. Referral Module (`src/modules/referral/models.py`)

### Referral Campaign Table
```sql
referral_campaign (
    id UUID PRIMARY KEY,
    name VARCHAR(255) NOT NULL,
    slug VARCHAR(100) UNIQUE NOT NULL,
    description TEXT,
    is_active BOOLEAN DEFAULT TRUE,
    start_date TIMESTAMPTZ,
    end_date TIMESTAMPTZ,
    reward_type VARCHAR(50) DEFAULT 'balance',
    referrer_reward_amount DECIMAL(18,2) DEFAULT 0,
    referee_reward_amount DECIMAL(18,2) DEFAULT 0,
    rules JSONB,
    max_conversions INTEGER,
    max_per_referrer INTEGER,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
)
```

### Referral Conversion Table
```sql
referral_conversion (
    id UUID PRIMARY KEY,
    campaign_id UUID REFERENCES referral_campaign(id) ON DELETE SET NULL,
    referrer_user_id UUID NOT NULL REFERENCES user(id) ON DELETE CASCADE,
    referee_user_id UUID NOT NULL UNIQUE REFERENCES user(id) ON DELETE CASCADE,
    status VARCHAR(30) DEFAULT 'pending',
    reward_transaction_id UUID REFERENCES wallet_transaction(id) ON DELETE SET NULL,
    reward_ledger_id UUID REFERENCES reward_ledger(id) ON DELETE SET NULL,
    qualified_at TIMESTAMPTZ,
    paid_at TIMESTAMPTZ,
    metadata JSONB,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
)
```

---

## Key Enumerations

### Role Types
- `admin` - System administrator
- `tenant` - Organization manager  
- `user` - Regular user
- `device` - IoT device access

### Organization Types
- `villa`, `house`, `apartment`, `studio`
- `flat_1_1`, `flat_2_1`, `flat_3_1`, `flat_4_1`
- `office`, `factory`, `warehouse`, `farm`
- `greenhouse`, `shop`, `hotel`, `hospital`, `school`

### Asset Types
- `site`, `block`, `floor`, `unit`
- `villa`, `apartment`, `factory`, `greenhouse`
- `office`, `warehouse`, `common_area`, `meter`

### Device Types
- `smart_plug`, `energy_meter`, `water_meter`, `gas_meter`
- `temperature_sensor`, `humidity_sensor`, `motion_sensor`
- `door_sensor`, `relay`, `thermostat`, `hvac_controller`

### Module Types
- `core`, `asset_management`, `iot`, `telemetry`
- `energy`, `rewards`, `billing`, `compliance`
- `notifications`, `dashboard`

---

## Database Features

### Multi-Tenant Architecture
- All tenant-specific tables include `organization_id` 
- Row-level security through application logic
- Tenant isolation enforced at service layer

### Performance Optimizations
- Strategic indexes on foreign keys and query patterns
- JSONB fields for flexible metadata storage
- TimescaleDB for time-series telemetry data
- Lazy loading disabled on high-volume relationships

### Compliance & Security
- KVKK/GDPR consent tracking
- Comprehensive audit logging
- Data retention policies
- Secure token-based authentication

### Extensibility
- Module-based architecture
- JSONB for dynamic configuration
- Enum-based type safety
- Hierarchical asset structures

---

## Migration Notes

### TimescaleDB Setup
```sql
-- Convert telemetry_data to hypertable after table creation
SELECT create_hypertable('telemetry_data', 'timestamp');

-- Optional: Convert energy_price to hypertable
SELECT create_hypertable('energy_price', 'timestamp');
```

### Continuous Aggregates (Recommended)
```sql
-- Hourly aggregation for telemetry data
-- NOTE: Uses metric_name for backward compat. V2 should use metric_definition_id
CREATE MATERIALIZED VIEW telemetry_hourly
WITH (timescaledb.continuous) AS
SELECT
    time_bucket('1 hour', timestamp) AS bucket,
    device_id,
    organization_id,
    metric_name,
    AVG(value) AS avg_value,
    MIN(value) AS min_value,
    MAX(value) AS max_value,
    COUNT(*) AS sample_count
FROM telemetry_data
GROUP BY bucket, device_id, organization_id, metric_name;

-- Daily aggregation for reporting
-- IMPORTANT: Use standardized metric names from metric_definition.canonical_name
-- Example canonical names: energy_kwh, power_w, voltage_v, current_a
CREATE MATERIALIZED VIEW telemetry_daily
WITH (timescaledb.continuous) AS
SELECT
    time_bucket('1 day', timestamp) AS bucket,
    device_id,
    organization_id,
    metric_name,
    AVG(value) AS avg_value,
    MIN(value) AS min_value,
    MAX(value) AS max_value,
    -- Use canonical metric names (energy_kwh, not 'energy')
    SUM(CASE WHEN metric_name IN ('energy_kwh', 'energy') THEN value ELSE 0 END) AS total_energy_kwh,
    COUNT(*) AS sample_count
FROM telemetry_data
GROUP BY bucket, device_id, organization_id, metric_name;

-- V2 Alternative: Join with metric_definition for canonical aggregation
-- CREATE MATERIALIZED VIEW telemetry_daily_v2
-- WITH (timescaledb.continuous) AS
-- SELECT
--     time_bucket('1 day', t.timestamp) AS bucket,
--     t.device_id,
--     t.organization_id,
--     COALESCE(m.canonical_name, t.metric_name) AS canonical_metric,
--     AVG(t.value) AS avg_value,
--     SUM(CASE WHEN m.canonical_name = 'energy_kwh' THEN t.value ELSE 0 END) AS total_energy_kwh
-- FROM telemetry_data t
-- LEFT JOIN metric_definition m ON t.metric_definition_id = m.id
-- GROUP BY bucket, t.device_id, t.organization_id, canonical_metric;

-- Refresh policies
SELECT add_continuous_aggregate_policy('telemetry_hourly',
    start_offset => INTERVAL '3 hours',
    end_offset => INTERVAL '1 hour',
    schedule_interval => INTERVAL '1 hour');

SELECT add_continuous_aggregate_policy('telemetry_daily',
    start_offset => INTERVAL '3 days',
    end_offset => INTERVAL '1 day',
    schedule_interval => INTERVAL '1 day');
```

### Data Retention Policies
```sql
-- Raw telemetry: Keep 90 days (configurable per organization)
SELECT add_retention_policy('telemetry_data', INTERVAL '90 days');

-- Hourly aggregates: Keep 1 year
SELECT add_retention_policy('telemetry_hourly', INTERVAL '365 days');

-- Daily aggregates: Keep 5 years
SELECT add_retention_policy('telemetry_daily', INTERVAL '1825 days');

-- Energy prices: Keep 2 years
SELECT add_retention_policy('energy_price', INTERVAL '730 days');
```

### Index Strategy
- Foreign key indexes for join performance
- Composite indexes for common query patterns
- Unique constraints for data integrity
- Partial indexes where applicable

### Data Types
- UUID for primary keys and foreign keys
- TIMESTAMPTZ for all timestamps (UTC)
- DECIMAL for financial values
- JSONB for flexible metadata
- Arrays for permission lists
