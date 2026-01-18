// AWAXEN Backend Database Schema
// Database: PostgreSQL + TimescaleDB

// ------------------------------------------
// 1. Authentication Module
// ------------------------------------------

TableGroup authentication {
  user
  organization
  role
  organization_user
  organization_module
  invitation
}

Table user {
  id uuid [pk]
  auth0_id varchar(100) [unique]
  email varchar(255) [not null, unique]
  hashed_password varchar(255)
  full_name varchar(255)
  first_name varchar(100)
  last_name varchar(100)
  phone varchar(50)
  telegram_username varchar(100)
  telegram_chat_id varchar(50)
  country varchar(100)
  city varchar(100)
  district varchar(100)
  address text
  postal_code varchar(20)
  notification_settings jsonb
  consent_settings jsonb
  kvkk_accepted boolean [default: false]
  kvkk_accepted_at timestamptz
  marketing_consent boolean [default: false]
  marketing_consent_at timestamptz
  onboarding_completed boolean [default: false]
  onboarding_step integer
  fcm_token varchar(500)
  is_active boolean [default: true]
  is_superuser boolean [default: false]
  is_verified boolean [default: false]
  status varchar(20) [default: 'active']
  // -- Referral Eklentileri --
  referral_code varchar(20) [unique, note: 'Kullanıcının paylaşacağı kod. Örn: AHMET123']
  referred_by_code varchar(20) [note: 'Kayıt olurken girdiği kod']
  last_login timestamptz
  last_login_ip varchar(45)
  last_login_user_agent varchar(500)
  mfa_enabled boolean [default: false]
  preferences jsonb
  created_at timestamptz [default: `now()`]
  updated_at timestamptz [default: `now()`]
}

Table organization {
  id uuid [pk]
  name varchar(255) [not null]
  slug varchar(100) [unique, not null]
  description text
  organization_type varchar(50)
  company_size integer
  email varchar(255)
  phone varchar(50)
  city varchar(100)
  district varchar(100)
  neighborhood varchar(100)
  street varchar(255)
  postal_code varchar(20)
  country varchar(100) [default: 'Türkiye']
  latitude decimal(10,7)
  longitude decimal(10,7)
  address text
  tax_number varchar(20)
  tax_office varchar(100)
  billing_email varchar(255)
  billing_address text
  tier varchar(20) [default: 'free']
  status varchar(20) [default: 'active']
  suspended_at timestamptz
  suspended_reason varchar(255)
  is_active boolean [default: true]
  settings jsonb
  created_at timestamptz [default: `now()`]
  updated_at timestamptz [default: `now()`]
}

Table role {
  id uuid [pk]
  name varchar(100) [not null]
  code varchar(50) [unique, not null]
  description text
  permissions text[] [default: '{}']
  is_system boolean [default: false]
  created_at timestamptz [default: `now()`]
  updated_at timestamptz [default: `now()`]
}

Table organization_user {
  id uuid [pk]
  user_id uuid [not null]
  organization_id uuid [not null]
  role_id uuid
  is_default boolean [default: false]
  joined_at timestamptz [not null]
  created_at timestamptz [default: `now()`]
  updated_at timestamptz [default: `now()`]

  indexes {
    (user_id, organization_id) [unique]
  }
}

Table organization_module {
  id uuid [pk]
  organization_id uuid [not null]
  module_code varchar(50) [not null]
  is_active boolean [default: true]
  settings jsonb
  activated_at timestamptz [not null]
  created_at timestamptz [default: `now()`]
  updated_at timestamptz [default: `now()`]

  indexes {
    (organization_id, module_code) [unique]
  }
}

Table invitation {
  id uuid [pk]
  email varchar(255) [not null]
  token varchar(100) [unique, not null]
  organization_id uuid [not null]
  role_code varchar(20) [default: 'user']
  invited_by_id uuid
  is_used boolean [default: false]
  used_at timestamptz
  expires_at timestamptz [not null]
  message text
  created_at timestamptz [default: `now()`]
  updated_at timestamptz [default: `now()`]
}

// ------------------------------------------
// 2. Billing Module
// ------------------------------------------

TableGroup billing {
  wallet
  wallet_transaction
}

Table wallet {
  id uuid [pk]
  wallet_type varchar(20) [default: 'company', note: 'check: company requires org_id, personal requires user_id']
  organization_id uuid
  user_id uuid
  balance decimal(18,2) [default: 0.00]
  currency varchar(3) [default: 'TRY']
  is_active boolean [default: true]
  credit_limit decimal(18,2)
  created_at timestamptz [default: `now()`]
  updated_at timestamptz [default: `now()`]

  indexes {
    (organization_id, currency) [unique]
    (user_id, currency) [unique]
  }
}

Table wallet_transaction {
  id uuid [pk]
  wallet_id uuid [not null]
  transaction_type varchar(20) [not null]
  amount decimal(18,2) [not null]
  balance_after decimal(18,2) [not null]
  status varchar(20) [default: 'completed']
  reference varchar(100)
  description text
  metadata jsonb
  created_at timestamptz [default: `now()`]
  updated_at timestamptz [default: `now()`]
}

// ------------------------------------------
// 3. Compliance Module
// ------------------------------------------

TableGroup compliance {
  consent
  audit_log
}

Table consent {
  id uuid [pk]
  user_id uuid [not null]
  organization_id uuid
  consent_type varchar(50) [not null]
  version varchar(20) [not null]
  accepted_at timestamptz
  revoked_at timestamptz
  metadata jsonb
  created_at timestamptz [default: `now()`]
  updated_at timestamptz [default: `now()`]
}

Table audit_log {
  id uuid [pk]
  organization_id uuid
  actor_user_id uuid
  action varchar(100) [not null]
  entity_type varchar(50) [not null]
  entity_id uuid
  payload_hash varchar(64)
  payload jsonb
  changes jsonb
  ip_address varchar(45)
  user_agent text
  request_id varchar(36)
  created_at timestamptz [default: `now()`]
  updated_at timestamptz [default: `now()`]
}

// ------------------------------------------
// 4. Energy Module
// ------------------------------------------

TableGroup energy {
  recommendation
  command
  command_proof
  reward_ledger
  streak
  saving_verification
  energy_price
  tariff_profile
  tariff_assignment
}

Table recommendation {
  id uuid [pk]
  asset_id uuid [not null]
  target_device_id uuid
  reason varchar(30) [not null]
  expected_saving_try decimal(12,2)
  expected_saving_kwh decimal(12,4)
  status varchar(20) [default: 'created']
  risk_level varchar(20) [default: 'low', note: 'low/medium/high - affects approval flow']
  expires_at timestamptz
  payload jsonb
  created_at timestamptz [default: `now()`]
  updated_at timestamptz [default: `now()`]
}

Table command {
  id uuid [pk]
  recommendation_id uuid
  gateway_id uuid [not null]
  device_id uuid [not null]
  action varchar(30) [not null]
  params jsonb
  status varchar(20) [default: 'queued']
  idempotency_key varchar(100) [unique, not null]
  sent_at timestamptz
  acked_at timestamptz
  finished_at timestamptz
  error text
  created_at timestamptz [default: `now()`]
  updated_at timestamptz [default: `now()`]
}

Table command_proof {
  id uuid [pk]
  command_id uuid [not null]
  proof_type varchar(30) [not null]
  proof_payload jsonb [not null]
  verified_at timestamptz
  created_at timestamptz [default: `now()`]
  updated_at timestamptz [default: `now()`]
}

Table reward_ledger {
  id uuid [pk]
  user_id uuid [not null]
  asset_id uuid
  event_type varchar(30) [not null]
  amount_awx integer [not null]
  expires_at timestamptz
  reference_type varchar(30)
  reference_id uuid
  description text
  created_at timestamptz [default: `now()`]
  updated_at timestamptz [default: `now()`]

  indexes {
    (event_type, reference_type, reference_id) [unique]
  }
}

Table streak {
  id uuid [pk]
  user_id uuid [not null]
  streak_type varchar(30) [not null]
  current_count integer [default: 0]
  longest_count integer [default: 0]
  last_date timestamptz
  created_at timestamptz [default: `now()`]
  updated_at timestamptz [default: `now()`]

  indexes {
    (user_id, streak_type) [unique]
  }
}

Table saving_verification {
  id uuid [pk]
  recommendation_id uuid [not null, unique]
  baseline_window_start timestamptz [not null]
  baseline_window_end timestamptz [not null]
  baseline_kwh decimal(12,4) [not null]
  compare_window_start timestamptz [not null]
  compare_window_end timestamptz [not null]
  compare_kwh decimal(12,4) [not null]
  saved_kwh decimal(12,4) [not null]
  saved_try decimal(12,2) [not null]
  confidence decimal(5,2) [not null]
  method varchar(20) [not null, note: 'baseline/peer/seasonal/predictive']
  verified_at timestamptz [not null]
  verification_details jsonb
  created_at timestamptz [default: `now()`]
  updated_at timestamptz [default: `now()`]
}

Table energy_price {
  id uuid [pk]
  timestamp timestamptz [not null, note: 'EPİAŞ price period']
  market varchar(20) [not null, note: 'epias_dam/epias_idm/epias_bpm/retail']
  price_try_mwh decimal(12,2) [not null]
  price_try_kwh decimal(8,6) [not null, note: 'Generated from price_try_mwh / 1000']
  region varchar(20) [default: 'TR']
  source varchar(50) [not null]
  volume_mwh decimal(14,2)
  metadata jsonb
  created_at timestamptz [default: `now()`]
  updated_at timestamptz [default: `now()`]

  indexes {
    (timestamp, market, region) [unique]
  }
}

Table tariff_profile {
  id uuid [pk]
  organization_id uuid [not null]
  name varchar(100) [not null]
  tariff_type varchar(20) [not null, note: 'single/two_period/three_period/custom']
  rate_peak decimal(8,6)
  rate_day decimal(8,6)
  rate_night decimal(8,6)
  rate_single decimal(8,6)
  peak_hours jsonb
  day_hours jsonb
  night_hours jsonb
  distribution_fee decimal(8,6) [default: 0]
  tax_rate decimal(5,4) [default: 0.20]
  demand_charge_try_kw decimal(10,2)
  valid_from timestamptz [not null]
  valid_to timestamptz
  is_active boolean [default: true]
  created_at timestamptz [default: `now()`]
  updated_at timestamptz [default: `now()`]

  indexes {
    (organization_id, name) [unique]
  }
}

Table tariff_assignment {
  id uuid [pk]
  tariff_profile_id uuid [not null]
  asset_id uuid
  zone_id uuid
  device_id uuid
  priority integer [default: 10, note: 'device(30) > zone(20) > asset(10)']
  valid_from timestamptz [not null]
  valid_to timestamptz
  created_at timestamptz [default: `now()`]
  updated_at timestamptz [default: `now()`]

  // Partial unique indexes for active assignments (WHERE valid_to IS NULL)
  // uq_tariff_assign_device_active, uq_tariff_assign_zone_active, uq_tariff_assign_asset_active
}

// ------------------------------------------
// 5. IoT Module
// ------------------------------------------

TableGroup iot {
  gateway
  device
  metric_definition
  telemetry_data
  gateway_pairing_code
  device_alias
  device_state_event
  device_coverage
}

Table gateway {
  id uuid [pk]
  organization_id uuid [not null]
  name varchar(255) [not null]
  serial_number varchar(100) [not null]
  mac_address varchar(17)
  identity_key varchar(255) [unique]
  asset_id uuid
  mqtt_client_id varchar(100) [unique]
  ip_address varchar(45)
  firmware_version varchar(50)
  hardware_version varchar(50)
  status varchar(20) [default: 'provisioning']
  last_seen_at timestamptz
  health_status varchar(20) [default: 'unknown', note: 'healthy/degraded/offline/unknown']
  last_data_at timestamptz [note: 'Last telemetry received']
  offline_since timestamptz [note: 'For SLA calculation']
  config jsonb
  versions jsonb
  created_at timestamptz [default: `now()`]
  updated_at timestamptz [default: `now()`]

  indexes {
    (organization_id, serial_number) [unique]
  }
}

Table device {
  id uuid [pk]
  organization_id uuid [not null]
  name varchar(255) [not null]
  device_id varchar(100) [not null]
  device_type varchar(30) [not null]
  asset_id uuid [not null]
  zone_id uuid
  gateway_id uuid
  external_id varchar(255)
  manufacturer varchar(100)
  model varchar(100)
  firmware_version varchar(50)
  safety_profile varchar(20) [default: 'normal']
  controllable boolean [default: true]
  status varchar(20) [default: 'provisioning']
  last_seen_at timestamptz
  config jsonb
  metadata jsonb
  created_at timestamptz [default: `now()`]
  updated_at timestamptz [default: `now()`]

  indexes {
    (organization_id, device_id) [unique]
  }
}

Table metric_definition {
  id uuid [pk]
  organization_id uuid [not null]
  name varchar(50) [not null]
  display_name varchar(100)
  unit varchar(20) [not null]
  device_type varchar(30)
  canonical_name varchar(50)
  min_value decimal(18,6)
  max_value decimal(18,6)
  description text
  created_at timestamptz [default: `now()`]
  updated_at timestamptz [default: `now()`]

  indexes {
    (organization_id, name) [unique]
  }
}

Table telemetry_data {
  id uuid [pk]
  timestamp timestamptz [not null, note: 'Hypertable partition key']
  device_id uuid [not null]
  organization_id uuid [not null, note: 'Denormalized for query performance']
  metric_name varchar(50) [not null]
  metric_definition_id uuid [note: 'Optional reference to metric_definition']
  value decimal(18,6) [not null]
  unit varchar(20) [not null]
  quality integer [default: 100]
  metadata jsonb
  created_at timestamptz [default: `now()`]
  updated_at timestamptz [default: `now()`]

  indexes {
    (organization_id, timestamp)
    (organization_id, device_id, timestamp)
  }
}

Table gateway_pairing_code {
  id uuid [pk]
  code varchar(20) [unique, not null]
  gateway_id uuid
  expires_at timestamptz [not null]
  used_at timestamptz
  created_at timestamptz [default: `now()`]
  updated_at timestamptz [default: `now()`]
}

Table device_alias {
  id uuid [pk]
  device_id uuid [not null]
  label varchar(100) [not null]
  created_by_user_id uuid
  created_at timestamptz [default: `now()`]
  updated_at timestamptz [default: `now()`]
}

Table device_state_event {
  id uuid [pk]
  ts timestamptz [not null]
  device_id uuid [not null]
  state_key varchar(50) [not null]
  state_value varchar(255) [not null]
  source varchar(20) [default: 'ha']
  created_at timestamptz [default: `now()`]
  updated_at timestamptz [default: `now()`]
}

Table device_coverage {
  id uuid [pk]
  device_id uuid [not null]
  asset_id uuid
  zone_id uuid
  ratio decimal(5,4) [default: 1.0, note: 'Coverage ratio: 1.0 = full']
  coverage_type varchar(20) [default: 'primary', note: 'primary/secondary/shared']
  notes text
  created_at timestamptz [default: `now()`]
  updated_at timestamptz [default: `now()`]

  indexes {
    (device_id, asset_id, zone_id) [unique]
  }
}

// ------------------------------------------
// 6. Real Estate Module
// ------------------------------------------

TableGroup real_estate {
  asset
  lease
  zone
  asset_membership
  tenancy
  handover_token
}

Table asset {
  id uuid [pk]
  organization_id uuid [not null]
  name varchar(255) [not null]
  code varchar(100) [not null]
  description text
  asset_type varchar(20) [not null]
  parent_id uuid
  address text
  latitude decimal(10,7)
  longitude decimal(10,7)
  area_sqm decimal(12,2)
  floor_number integer
  status varchar(30) [default: 'active']
  metadata jsonb
  created_at timestamptz [default: `now()`]
  updated_at timestamptz [default: `now()`]

  indexes {
    (organization_id, code) [unique]
  }
}

Table lease {
  id uuid [pk]
  organization_id uuid [not null]
  asset_id uuid [not null]
  tenant_name varchar(255) [not null]
  tenant_email varchar(255)
  tenant_phone varchar(50)
  tenant_id_number varchar(50)
  contract_number varchar(100) [unique]
  start_date date [not null]
  end_date date [not null]
  monthly_rent decimal(12,2) [not null]
  deposit_amount decimal(12,2)
  currency varchar(3) [default: 'TRY']
  status varchar(30) [default: 'draft']
  signed_at timestamptz
  terminated_at timestamptz
  notes text
  created_at timestamptz [default: `now()`]
  updated_at timestamptz [default: `now()`]
}

Table zone {
  id uuid [pk]
  asset_id uuid [not null]
  name varchar(100) [not null]
  zone_type varchar(30) [default: 'room']
  description text
  created_at timestamptz [default: `now()`]
  updated_at timestamptz [default: `now()`]
}

Table asset_membership {
  id uuid [pk]
  asset_id uuid [not null]
  user_id uuid [not null]
  relation varchar(30) [not null]
  scopes "text[]" [default: '{}']
  revoked_at timestamptz
  created_at timestamptz [default: `now()`]
  updated_at timestamptz [default: `now()`]

  indexes {
    (asset_id, user_id, relation) [unique]
  }
}

Table tenancy {
  id uuid [pk]
  asset_id uuid [not null]
  tenant_user_id uuid [not null]
  start_at timestamptz [not null]
  end_at timestamptz
  status varchar(20) [default: 'active']
  handover_mode varchar(30)
  created_at timestamptz [default: `now()`]
  updated_at timestamptz [default: `now()`]
}

Table handover_token {
  id uuid [pk]
  asset_id uuid [not null]
  token varchar(100) [unique, not null]
  expires_at timestamptz [not null]
  used_at timestamptz
  used_by_user_id uuid
  created_at timestamptz [default: `now()`]
  updated_at timestamptz [default: `now()`]
}

// ------------------------------------------
// 7. Notifications Module
// ------------------------------------------

TableGroup notifications {
  notification
  user_fcm_token
  notification_preference
}

Table notification {
  id uuid [pk]
  user_id uuid [not null]
  organization_id uuid
  type varchar(20) [default: 'info']
  priority varchar(20) [default: 'medium']
  title varchar(255) [not null]
  message text [not null]
  data jsonb
  is_read boolean [default: false]
  read_at timestamptz
  channels_sent jsonb
  source_type varchar(50)
  source_id uuid
  created_at timestamptz [default: `now()`]
  updated_at timestamptz [default: `now()`]
}

Table user_fcm_token {
  id uuid [pk]
  user_id uuid [not null]
  token varchar(500) [unique, not null]
  device_type varchar(20) [default: 'web']
  device_name varchar(100)
  is_active boolean [default: true]
  last_used_at timestamptz
  failed_count integer [default: 0]
  created_at timestamptz [default: `now()`]
  updated_at timestamptz [default: `now()`]
}

Table notification_preference {
  id uuid [pk]
  user_id uuid [not null, unique]
  push_enabled boolean [default: true]
  telegram_enabled boolean [default: true]
  email_enabled boolean [default: false]
  type_preferences jsonb
  quiet_hours_enabled boolean [default: false]
  quiet_hours_start varchar(5)
  quiet_hours_end varchar(5)
  created_at timestamptz [default: `now()`]
  updated_at timestamptz [default: `now()`]
}

// ------------------------------------------
// 8. Referral Module (NEW)
// ------------------------------------------

TableGroup referral {
  referral_campaign
  referral_conversion
}

Table referral_campaign {
  id uuid [pk]
  name varchar(255) [not null, note: 'Örn: Standart Davet, Yaz Kampanyası']
  slug varchar(100) [unique, not null]
  description text
  max_conversions integer
  max_per_referrer integer
  is_active boolean [default: true]
  start_date timestamptz
  end_date timestamptz
  reward_type varchar(50) [default: 'balance', note: 'balance (TL), awx_point (Puan), discount (İndirim)']
  referrer_reward_amount decimal(18,2) [default: 0, note: 'Davet edene verilecek miktar']
  referee_reward_amount decimal(18,2) [default: 0, note: 'Davet edilene verilecek miktar']
  rules jsonb [note: 'Min harcama limiti, vb. kurallar']
  created_at timestamptz [default: `now()`]
  updated_at timestamptz [default: `now()`]
}

Table referral_conversion {
  id uuid [pk]
  campaign_id uuid [not null]
  referrer_user_id uuid [not null, note: 'Davet eden']
  referee_user_id uuid [not null, unique, note: 'Davet edilen (yeni üye)']
  status varchar(30) [default: 'pending', note: 'pending, qualified, paid, fraud, expired']
  
  // Ödül Takibi
  reward_transaction_id uuid [note: 'Wallet transaction ID referansı (Eğer para ise)']
  reward_ledger_id uuid [note: 'Reward ledger ID referansı (Eğer AWX puan ise)']
  
  metadata jsonb [note: 'IP eşleşmesi, cihaz bilgisi vb. güvenlik logları']
  created_at timestamptz [default: `now()`]
  updated_at timestamptz [default: `now()`] // Ödülün verildiği tarih
  
  indexes {
    (referrer_user_id, status)
  }
}
// ------------------------------------------
// Relationships
// ------------------------------------------

// Auth
Ref: organization_user.user_id > user.id [delete: cascade]
Ref: organization_user.organization_id > organization.id [delete: cascade]
Ref: organization_user.role_id > role.id [delete: set null]

Ref: organization_module.organization_id > organization.id [delete: cascade]

Ref: invitation.organization_id > organization.id [delete: cascade]
Ref: invitation.invited_by_id > user.id [delete: set null]

// Billing
Ref: wallet.organization_id > organization.id [delete: cascade]
Ref: wallet.user_id > user.id [delete: cascade]
Ref: wallet_transaction.wallet_id > wallet.id [delete: cascade]

// Compliance
Ref: consent.user_id > user.id [delete: cascade]
Ref: consent.organization_id > organization.id [delete: cascade]
Ref: audit_log.organization_id > organization.id [delete: cascade]
Ref: audit_log.actor_user_id > user.id [delete: set null]

// Energy
Ref: recommendation.asset_id > asset.id [delete: cascade]
Ref: recommendation.target_device_id > device.id [delete: set null]
Ref: command.recommendation_id > recommendation.id [delete: set null]
Ref: command.gateway_id > gateway.id [delete: cascade]
Ref: command.device_id > device.id [delete: cascade]
Ref: command_proof.command_id > command.id [delete: cascade]
Ref: reward_ledger.user_id > user.id [delete: cascade]
Ref: reward_ledger.asset_id > asset.id [delete: set null]
Ref: streak.user_id > user.id [delete: cascade]
Ref: saving_verification.recommendation_id > recommendation.id [delete: cascade]
Ref: tariff_profile.organization_id > organization.id [delete: cascade]
Ref: tariff_assignment.tariff_profile_id > tariff_profile.id [delete: cascade]
Ref: tariff_assignment.asset_id > asset.id [delete: cascade]
Ref: tariff_assignment.device_id > device.id [delete: cascade]
Ref: metric_definition.organization_id > organization.id [delete: cascade]
Ref: telemetry_data.device_id > device.id [delete: cascade]
Ref: telemetry_data.organization_id > organization.id [delete: cascade]
Ref: telemetry_data.metric_definition_id > metric_definition.id [delete: set null]

// IoT
Ref: gateway.organization_id > organization.id [delete: cascade]
Ref: gateway.asset_id > asset.id [delete: set null]

Ref: device.organization_id > organization.id [delete: cascade]
Ref: device.asset_id > asset.id [delete: cascade]
Ref: device.zone_id > zone.id [delete: set null]
Ref: device.gateway_id > gateway.id [delete: set null]

Ref: gateway_pairing_code.gateway_id > gateway.id [delete: set null]
Ref: device_alias.device_id > device.id [delete: cascade]
Ref: device_alias.created_by_user_id > user.id [delete: set null]
Ref: device_state_event.device_id > device.id [delete: cascade]

// Real Estate
Ref: asset.organization_id > organization.id [delete: cascade]
Ref: asset.parent_id > asset.id [delete: cascade]

Ref: lease.organization_id > organization.id [delete: cascade]
Ref: lease.asset_id > asset.id [delete: cascade]

Ref: zone.asset_id > asset.id [delete: cascade]

Ref: asset_membership.asset_id > asset.id [delete: cascade]
Ref: asset_membership.user_id > user.id [delete: cascade]

Ref: tenancy.asset_id > asset.id [delete: cascade]
Ref: tenancy.tenant_user_id > user.id [delete: cascade]

Ref: handover_token.asset_id > asset.id [delete: cascade]
Ref: handover_token.used_by_user_id > user.id [delete: set null]

// Notifications
Ref: notification.user_id > user.id [delete: cascade]
Ref: notification.organization_id > organization.id [delete: cascade]
Ref: user_fcm_token.user_id > user.id [delete: cascade]
Ref: notification_preference.user_id > user.id [delete: cascade] // One-to-one



// Referral Module Relationships
Ref: referral_conversion.campaign_id > referral_campaign.id [delete: set null]
Ref: referral_conversion.referrer_user_id > user.id [delete: cascade]
Ref: referral_conversion.referee_user_id > user.id [delete: cascade]

// Ödül bağlantıları (Opsiyonel One-to-One mantığı)
Ref: referral_conversion.reward_transaction_id > wallet_transaction.id
Ref: referral_conversion.reward_ledger_id > reward_ledger.id