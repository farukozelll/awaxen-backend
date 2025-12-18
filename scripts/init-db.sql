-- ============================================
-- Awaxen Database Initialization Script
-- TimescaleDB + PostgreSQL
-- ============================================

-- Enable required extensions
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "pgcrypto";

-- TimescaleDB extension (if available)
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_available_extensions WHERE name = 'timescaledb') THEN
        CREATE EXTENSION IF NOT EXISTS timescaledb CASCADE;
        RAISE NOTICE 'TimescaleDB extension enabled';
    ELSE
        RAISE NOTICE 'TimescaleDB not available, using standard PostgreSQL';
    END IF;
END $$;

-- Create hypertable for device_telemetry after table creation
-- This will be run by Flask-Migrate, but we prepare the function here
CREATE OR REPLACE FUNCTION create_telemetry_hypertable()
RETURNS void AS $$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_available_extensions WHERE name = 'timescaledb') THEN
        IF EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name = 'device_telemetry') THEN
            PERFORM create_hypertable('device_telemetry', 'time', if_not_exists => TRUE);
            RAISE NOTICE 'Hypertable created for device_telemetry';
        END IF;
    END IF;
END;
$$ LANGUAGE plpgsql;

-- Performance indexes (will be created after tables exist)
-- These are suggestions for Flask-Migrate migrations

-- Index suggestions:
-- CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_devices_org_active ON smart_devices(organization_id, is_active);
-- CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_automations_org_active ON automations(organization_id, is_active);
-- CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_telemetry_device_time ON device_telemetry(device_id, time DESC);
-- CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_market_prices_time ON market_prices(time DESC);
-- CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_notifications_user_read ON notifications(user_id, is_read);

-- Grant permissions (adjust as needed)
-- GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA public TO awaxen_user;
-- GRANT ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA public TO awaxen_user;

RAISE NOTICE 'Awaxen database initialization complete';
