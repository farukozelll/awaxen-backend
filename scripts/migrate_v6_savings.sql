-- ============================================
-- Awaxen Backend v6.1 - Database Migration
-- New fields and tables for savings tracking
-- ============================================

-- Run this migration after deploying the new code
-- Execute with: psql -U $DB_USER -d $DB_NAME -f migrate_v6_savings.sql

BEGIN;

-- ==========================================
-- 1. Add new columns to user_settings
-- ==========================================
ALTER TABLE user_settings 
ADD COLUMN IF NOT EXISTS primary_color VARCHAR(20) DEFAULT '#3B82F6',
ADD COLUMN IF NOT EXISTS secondary_color VARCHAR(20) DEFAULT '#10B981';

COMMENT ON COLUMN user_settings.primary_color IS 'UI primary color (hex)';
COMMENT ON COLUMN user_settings.secondary_color IS 'UI secondary color (hex)';

-- ==========================================
-- 2. Add new columns to organizations
-- ==========================================
ALTER TABLE organizations 
ADD COLUMN IF NOT EXISTS electricity_price_kwh NUMERIC(10, 4) DEFAULT 2.5,
ADD COLUMN IF NOT EXISTS currency VARCHAR(10) DEFAULT 'TRY';

COMMENT ON COLUMN organizations.electricity_price_kwh IS 'Electricity price per kWh for savings calculation';
COMMENT ON COLUMN organizations.currency IS 'Currency code (TRY, USD, EUR)';

-- ==========================================
-- 3. Add power_rating_watt to smart_devices
-- ==========================================
ALTER TABLE smart_devices 
ADD COLUMN IF NOT EXISTS power_rating_watt INTEGER DEFAULT 0;

COMMENT ON COLUMN smart_devices.power_rating_watt IS 'Device power rating in Watts for savings calculation';

-- ==========================================
-- 4. Create energy_savings table
-- ==========================================
CREATE TABLE IF NOT EXISTS energy_savings (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    organization_id UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    device_id UUID REFERENCES smart_devices(id) ON DELETE SET NULL,
    automation_id UUID REFERENCES automations(id) ON DELETE SET NULL,
    
    date DATE NOT NULL,
    
    off_duration_minutes INTEGER DEFAULT 0,
    power_rating_watt INTEGER DEFAULT 0,
    energy_saved_kwh NUMERIC(10, 4) DEFAULT 0,
    money_saved NUMERIC(10, 2) DEFAULT 0,
    currency VARCHAR(10) DEFAULT 'TRY',
    
    source_type VARCHAR(50) DEFAULT 'automation',
    details JSONB DEFAULT '{}',
    
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Indexes for energy_savings
CREATE INDEX IF NOT EXISTS idx_savings_org_date ON energy_savings(organization_id, date);
CREATE INDEX IF NOT EXISTS idx_savings_org_device ON energy_savings(organization_id, device_id);
CREATE INDEX IF NOT EXISTS idx_savings_date ON energy_savings(date);

COMMENT ON TABLE energy_savings IS 'Energy savings records from automations and schedules';

-- ==========================================
-- 5. Create device_state_logs table
-- ==========================================
CREATE TABLE IF NOT EXISTS device_state_logs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    device_id UUID NOT NULL REFERENCES smart_devices(id) ON DELETE CASCADE,
    
    timestamp TIMESTAMP WITH TIME ZONE DEFAULT NOW() NOT NULL,
    state VARCHAR(20) NOT NULL,
    power_level INTEGER DEFAULT 100,
    
    triggered_by VARCHAR(50),
    automation_id UUID REFERENCES automations(id) ON DELETE SET NULL
);

-- Index for device_state_logs
CREATE INDEX IF NOT EXISTS idx_state_device_time ON device_state_logs(device_id, timestamp);

COMMENT ON TABLE device_state_logs IS 'Device state change logs for savings calculation';

-- ==========================================
-- 6. Create TimescaleDB hypertable for device_state_logs (optional)
-- ==========================================
-- Uncomment if you want time-series optimization for state logs
-- SELECT create_hypertable('device_state_logs', 'timestamp', if_not_exists => TRUE);

-- ==========================================
-- 7. Update existing devices with estimated power ratings
-- ==========================================
-- Set default power ratings based on device type
UPDATE smart_devices 
SET power_rating_watt = CASE 
    WHEN device_type = 'plug' THEN 2000
    WHEN device_type = 'switch' THEN 1000
    WHEN device_type = 'dimmer' THEN 500
    WHEN device_type = 'relay' THEN 1500
    WHEN device_type = 'light' THEN 60
    WHEN device_type = 'sensor' THEN 5
    ELSE 100
END
WHERE power_rating_watt = 0 OR power_rating_watt IS NULL;

COMMIT;

-- ==========================================
-- Verification queries
-- ==========================================
-- Run these to verify the migration:

-- Check user_settings columns
-- SELECT column_name, data_type, column_default 
-- FROM information_schema.columns 
-- WHERE table_name = 'user_settings' AND column_name IN ('primary_color', 'secondary_color');

-- Check organizations columns
-- SELECT column_name, data_type, column_default 
-- FROM information_schema.columns 
-- WHERE table_name = 'organizations' AND column_name IN ('electricity_price_kwh', 'currency');

-- Check smart_devices columns
-- SELECT column_name, data_type, column_default 
-- FROM information_schema.columns 
-- WHERE table_name = 'smart_devices' AND column_name = 'power_rating_watt';

-- Check new tables exist
-- SELECT table_name FROM information_schema.tables 
-- WHERE table_name IN ('energy_savings', 'device_state_logs');

SELECT 'Migration completed successfully!' as status;
