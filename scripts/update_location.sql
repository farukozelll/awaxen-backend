-- Update organizations with default Istanbul location
UPDATE organizations 
SET location = '{"latitude": 41.0082, "longitude": 28.9784, "city": "Istanbul", "country": "TR"}'::jsonb 
WHERE location IS NULL OR location = '{}'::jsonb;
