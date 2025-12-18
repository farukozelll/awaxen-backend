-- Varsayılan Abonelik Planları
INSERT INTO subscription_plans (id, code, name, description, price_monthly, price_yearly, currency, max_devices, max_users, max_automations, max_integrations, features, is_active, sort_order, created_at, updated_at)
VALUES 
(gen_random_uuid(), 'free', 'Free', 'Başlangıç için ücretsiz plan', 0, 0, 'TRY', 3, 1, 5, 1, '{"basic_dashboard": true}', true, 0, NOW(), NOW()),
(gen_random_uuid(), 'starter', 'Starter', 'Küçük evler için ideal', 49, 490, 'TRY', 10, 2, 20, 3, '{"basic_dashboard": true, "email_alerts": true, "history_7d": true}', true, 1, NOW(), NOW()),
(gen_random_uuid(), 'pro', 'Pro', 'Gelişmiş özellikler ve analitik', 149, 1490, 'TRY', 50, 5, 100, 10, '{"basic_dashboard": true, "advanced_analytics": true, "email_alerts": true, "telegram_alerts": true, "history_30d": true, "api_access": true}', true, 2, NOW(), NOW()),
(gen_random_uuid(), 'enterprise', 'Enterprise', 'Fabrikalar ve büyük işletmeler için', 499, 4990, 'TRY', 500, 50, 1000, 50, '{"basic_dashboard": true, "advanced_analytics": true, "email_alerts": true, "telegram_alerts": true, "sms_alerts": true, "history_unlimited": true, "api_access": true, "white_label": true, "dedicated_support": true}', true, 3, NOW(), NOW())
ON CONFLICT (code) DO UPDATE SET
    name = EXCLUDED.name,
    description = EXCLUDED.description,
    price_monthly = EXCLUDED.price_monthly,
    price_yearly = EXCLUDED.price_yearly,
    max_devices = EXCLUDED.max_devices,
    max_users = EXCLUDED.max_users,
    max_automations = EXCLUDED.max_automations,
    max_integrations = EXCLUDED.max_integrations,
    features = EXCLUDED.features,
    updated_at = NOW();
