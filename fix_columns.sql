-- User table columns
ALTER TABLE "user" ADD COLUMN IF NOT EXISTS last_login_ip VARCHAR(45);
ALTER TABLE "user" ADD COLUMN IF NOT EXISTS last_login_user_agent VARCHAR(500);
ALTER TABLE "user" ADD COLUMN IF NOT EXISTS mfa_enabled BOOLEAN DEFAULT false NOT NULL;
ALTER TABLE "user" ADD COLUMN IF NOT EXISTS preferences JSONB;

-- Organization table columns
ALTER TABLE "organization" ADD COLUMN IF NOT EXISTS tax_number VARCHAR(20);
ALTER TABLE "organization" ADD COLUMN IF NOT EXISTS tax_office VARCHAR(100);
ALTER TABLE "organization" ADD COLUMN IF NOT EXISTS billing_email VARCHAR(255);
ALTER TABLE "organization" ADD COLUMN IF NOT EXISTS billing_address TEXT;
ALTER TABLE "organization" ADD COLUMN IF NOT EXISTS tier VARCHAR(20) DEFAULT 'free' NOT NULL;
ALTER TABLE "organization" ADD COLUMN IF NOT EXISTS suspended_at TIMESTAMP WITH TIME ZONE;
ALTER TABLE "organization" ADD COLUMN IF NOT EXISTS suspended_reason TEXT;
