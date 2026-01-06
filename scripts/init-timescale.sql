-- TimescaleDB Initialization Script
-- Run after tables are created by Alembic

-- Enable TimescaleDB extension
CREATE EXTENSION IF NOT EXISTS timescaledb CASCADE;

-- Convert telemetry_data to hypertable
-- Note: Run this AFTER Alembic creates the table
-- SELECT create_hypertable('telemetry_data', 'timestamp', if_not_exists => TRUE);

-- Create compression policy (compress data older than 7 days)
-- SELECT add_compression_policy('telemetry_data', INTERVAL '7 days');

-- Create retention policy (drop data older than 1 year)
-- SELECT add_retention_policy('telemetry_data', INTERVAL '1 year');

-- Useful indexes for time-series queries
-- CREATE INDEX IF NOT EXISTS ix_telemetry_device_time_desc 
--     ON telemetry_data (device_id, timestamp DESC);

-- Continuous aggregate for hourly stats (optional)
-- CREATE MATERIALIZED VIEW telemetry_hourly
-- WITH (timescaledb.continuous) AS
-- SELECT
--     time_bucket('1 hour', timestamp) AS bucket,
--     device_id,
--     metric_name,
--     AVG(value) AS avg_value,
--     MIN(value) AS min_value,
--     MAX(value) AS max_value,
--     COUNT(*) AS count
-- FROM telemetry_data
-- GROUP BY bucket, device_id, metric_name;

-- Add refresh policy for continuous aggregate
-- SELECT add_continuous_aggregate_policy('telemetry_hourly',
--     start_offset => INTERVAL '3 hours',
--     end_offset => INTERVAL '1 hour',
--     schedule_interval => INTERVAL '1 hour');
