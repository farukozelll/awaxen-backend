"""Add Awaxen core tables - Zone, Tenancy, Handover, Energy, Marketplace

Revision ID: 20260106_core
Revises: 75790e51fe08
Create Date: 2026-01-06

New tables:
- consent (KVKK/GDPR)
- audit_log
- zone
- asset_membership
- tenancy
- handover_token
- gateway_pairing_code
- device_alias
- device_state_event
- recommendation
- command
- command_proof
- reward_ledger
- streak
- alarm
- job
- job_offer
- job_proof

Modified tables:
- gateway: add identity_key, versions
- device: add zone_id, external_id, safety_profile, controllable
- asset: add new asset types
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = '20260106_core'
down_revision: Union[str, None] = '75790e51fe08'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # === COMPLIANCE MODULE ===
    
    # consent table
    op.create_table('consent',
        sa.Column('id', sa.UUID(), server_default=sa.text('gen_random_uuid()'), nullable=False),
        sa.Column('user_id', sa.UUID(), nullable=False),
        sa.Column('organization_id', sa.UUID(), nullable=True),
        sa.Column('consent_type', sa.String(50), nullable=False),
        sa.Column('version', sa.String(20), nullable=False),
        sa.Column('accepted_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('revoked_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('metadata', postgresql.JSONB(), nullable=True, server_default='{}'),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('CURRENT_TIMESTAMP'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('CURRENT_TIMESTAMP'), nullable=False),
        sa.ForeignKeyConstraint(['user_id'], ['user.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['organization_id'], ['organization.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('idx_consent_user', 'consent', ['user_id'])
    op.create_index('idx_consent_user_type', 'consent', ['user_id', 'consent_type'])
    op.create_index('idx_consent_org', 'consent', ['organization_id'])
    
    # audit_log table
    op.create_table('audit_log',
        sa.Column('id', sa.UUID(), server_default=sa.text('gen_random_uuid()'), nullable=False),
        sa.Column('organization_id', sa.UUID(), nullable=True),
        sa.Column('actor_user_id', sa.UUID(), nullable=True),
        sa.Column('action', sa.String(100), nullable=False),
        sa.Column('entity_type', sa.String(50), nullable=False),
        sa.Column('entity_id', sa.UUID(), nullable=True),
        sa.Column('payload_hash', sa.String(64), nullable=True),
        sa.Column('payload', postgresql.JSONB(), nullable=True, server_default='{}'),
        sa.Column('ip_address', sa.String(45), nullable=True),
        sa.Column('user_agent', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('CURRENT_TIMESTAMP'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('CURRENT_TIMESTAMP'), nullable=False),
        sa.ForeignKeyConstraint(['organization_id'], ['organization.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['actor_user_id'], ['user.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('idx_audit_org_time', 'audit_log', ['organization_id', 'created_at'])
    op.create_index('idx_audit_actor', 'audit_log', ['actor_user_id'])
    op.create_index('idx_audit_entity', 'audit_log', ['entity_type', 'entity_id'])
    op.create_index('idx_audit_action', 'audit_log', ['action'])
    
    # === REAL ESTATE MODULE ADDITIONS ===
    
    # zone table
    op.create_table('zone',
        sa.Column('id', sa.UUID(), server_default=sa.text('gen_random_uuid()'), nullable=False),
        sa.Column('asset_id', sa.UUID(), nullable=False),
        sa.Column('name', sa.String(100), nullable=False),
        sa.Column('zone_type', sa.String(30), nullable=False, server_default='room'),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('CURRENT_TIMESTAMP'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('CURRENT_TIMESTAMP'), nullable=False),
        sa.ForeignKeyConstraint(['asset_id'], ['asset.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('idx_zone_asset', 'zone', ['asset_id'])
    
    # asset_membership table
    op.create_table('asset_membership',
        sa.Column('id', sa.UUID(), server_default=sa.text('gen_random_uuid()'), nullable=False),
        sa.Column('asset_id', sa.UUID(), nullable=False),
        sa.Column('user_id', sa.UUID(), nullable=False),
        sa.Column('relation', sa.String(30), nullable=False),
        sa.Column('scopes', postgresql.ARRAY(sa.String()), nullable=False, server_default='{}'),
        sa.Column('revoked_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('CURRENT_TIMESTAMP'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('CURRENT_TIMESTAMP'), nullable=False),
        sa.ForeignKeyConstraint(['asset_id'], ['asset.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['user_id'], ['user.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('asset_id', 'user_id', 'relation', name='uq_asset_membership')
    )
    op.create_index('idx_asset_membership_asset', 'asset_membership', ['asset_id'])
    op.create_index('idx_asset_membership_user', 'asset_membership', ['user_id'])
    
    # tenancy table
    op.create_table('tenancy',
        sa.Column('id', sa.UUID(), server_default=sa.text('gen_random_uuid()'), nullable=False),
        sa.Column('asset_id', sa.UUID(), nullable=False),
        sa.Column('tenant_user_id', sa.UUID(), nullable=False),
        sa.Column('start_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('end_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('status', sa.String(20), nullable=False, server_default='active'),
        sa.Column('handover_mode', sa.String(30), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('CURRENT_TIMESTAMP'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('CURRENT_TIMESTAMP'), nullable=False),
        sa.ForeignKeyConstraint(['asset_id'], ['asset.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['tenant_user_id'], ['user.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('idx_tenancy_asset', 'tenancy', ['asset_id'])
    op.create_index('idx_tenancy_tenant', 'tenancy', ['tenant_user_id'])
    op.create_index('idx_tenancy_status', 'tenancy', ['status'])
    
    # handover_token table
    op.create_table('handover_token',
        sa.Column('id', sa.UUID(), server_default=sa.text('gen_random_uuid()'), nullable=False),
        sa.Column('asset_id', sa.UUID(), nullable=False),
        sa.Column('token', sa.String(100), nullable=False, unique=True),
        sa.Column('expires_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('used_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('used_by_user_id', sa.UUID(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('CURRENT_TIMESTAMP'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('CURRENT_TIMESTAMP'), nullable=False),
        sa.ForeignKeyConstraint(['asset_id'], ['asset.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['used_by_user_id'], ['user.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('idx_handover_asset', 'handover_token', ['asset_id'])
    op.create_index('idx_handover_token', 'handover_token', ['token'])
    
    # === IOT MODULE ADDITIONS ===
    
    # Add columns to gateway
    op.add_column('gateway', sa.Column('identity_key', sa.String(255), nullable=True, unique=True))
    op.add_column('gateway', sa.Column('versions', postgresql.JSONB(), nullable=True, server_default='{}'))
    
    # Add columns to device
    op.add_column('device', sa.Column('zone_id', sa.UUID(), nullable=True))
    op.add_column('device', sa.Column('external_id', sa.String(255), nullable=True))
    op.add_column('device', sa.Column('safety_profile', sa.String(20), nullable=False, server_default='normal'))
    op.add_column('device', sa.Column('controllable', sa.Boolean(), nullable=False, server_default='true'))
    op.create_foreign_key('fk_device_zone_id_zone', 'device', 'zone', ['zone_id'], ['id'], ondelete='SET NULL')
    op.create_index('idx_device_zone', 'device', ['zone_id'])
    
    # gateway_pairing_code table
    op.create_table('gateway_pairing_code',
        sa.Column('id', sa.UUID(), server_default=sa.text('gen_random_uuid()'), nullable=False),
        sa.Column('code', sa.String(20), nullable=False, unique=True),
        sa.Column('gateway_id', sa.UUID(), nullable=True),
        sa.Column('expires_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('used_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('CURRENT_TIMESTAMP'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('CURRENT_TIMESTAMP'), nullable=False),
        sa.ForeignKeyConstraint(['gateway_id'], ['gateway.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('idx_pairing_code', 'gateway_pairing_code', ['code'])
    op.create_index('idx_pairing_expires', 'gateway_pairing_code', ['expires_at'])
    
    # device_alias table
    op.create_table('device_alias',
        sa.Column('id', sa.UUID(), server_default=sa.text('gen_random_uuid()'), nullable=False),
        sa.Column('device_id', sa.UUID(), nullable=False),
        sa.Column('label', sa.String(100), nullable=False),
        sa.Column('created_by_user_id', sa.UUID(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('CURRENT_TIMESTAMP'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('CURRENT_TIMESTAMP'), nullable=False),
        sa.ForeignKeyConstraint(['device_id'], ['device.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['created_by_user_id'], ['user.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('idx_device_alias_device', 'device_alias', ['device_id'])
    
    # device_state_event table
    op.create_table('device_state_event',
        sa.Column('id', sa.UUID(), server_default=sa.text('gen_random_uuid()'), nullable=False),
        sa.Column('ts', sa.DateTime(timezone=True), nullable=False),
        sa.Column('device_id', sa.UUID(), nullable=False),
        sa.Column('state_key', sa.String(50), nullable=False),
        sa.Column('state_value', sa.String(255), nullable=False),
        sa.Column('source', sa.String(20), nullable=False, server_default='ha'),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('CURRENT_TIMESTAMP'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('CURRENT_TIMESTAMP'), nullable=False),
        sa.ForeignKeyConstraint(['device_id'], ['device.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('idx_state_device_ts', 'device_state_event', ['device_id', 'ts'])
    
    # === ENERGY MODULE ===
    
    # recommendation table
    op.create_table('recommendation',
        sa.Column('id', sa.UUID(), server_default=sa.text('gen_random_uuid()'), nullable=False),
        sa.Column('asset_id', sa.UUID(), nullable=False),
        sa.Column('target_device_id', sa.UUID(), nullable=True),
        sa.Column('reason', sa.String(30), nullable=False),
        sa.Column('expected_saving_try', sa.Numeric(12, 2), nullable=True),
        sa.Column('expected_saving_kwh', sa.Numeric(12, 4), nullable=True),
        sa.Column('status', sa.String(20), nullable=False, server_default='created'),
        sa.Column('expires_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('payload', postgresql.JSONB(), nullable=True, server_default='{}'),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('CURRENT_TIMESTAMP'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('CURRENT_TIMESTAMP'), nullable=False),
        sa.ForeignKeyConstraint(['asset_id'], ['asset.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['target_device_id'], ['device.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('idx_reco_asset_time', 'recommendation', ['asset_id', 'created_at'])
    op.create_index('idx_reco_status', 'recommendation', ['status'])
    op.create_index('idx_reco_expires', 'recommendation', ['expires_at'])
    
    # command table
    op.create_table('command',
        sa.Column('id', sa.UUID(), server_default=sa.text('gen_random_uuid()'), nullable=False),
        sa.Column('recommendation_id', sa.UUID(), nullable=True),
        sa.Column('gateway_id', sa.UUID(), nullable=False),
        sa.Column('device_id', sa.UUID(), nullable=False),
        sa.Column('action', sa.String(30), nullable=False),
        sa.Column('params', postgresql.JSONB(), nullable=True, server_default='{}'),
        sa.Column('status', sa.String(20), nullable=False, server_default='queued'),
        sa.Column('idempotency_key', sa.String(100), nullable=False, unique=True),
        sa.Column('sent_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('acked_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('finished_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('error', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('CURRENT_TIMESTAMP'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('CURRENT_TIMESTAMP'), nullable=False),
        sa.ForeignKeyConstraint(['recommendation_id'], ['recommendation.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['gateway_id'], ['gateway.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['device_id'], ['device.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('idx_command_gateway_time', 'command', ['gateway_id', 'created_at'])
    op.create_index('idx_command_status', 'command', ['status'])
    
    # command_proof table
    op.create_table('command_proof',
        sa.Column('id', sa.UUID(), server_default=sa.text('gen_random_uuid()'), nullable=False),
        sa.Column('command_id', sa.UUID(), nullable=False),
        sa.Column('proof_type', sa.String(30), nullable=False),
        sa.Column('proof_payload', postgresql.JSONB(), nullable=False),
        sa.Column('verified_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('CURRENT_TIMESTAMP'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('CURRENT_TIMESTAMP'), nullable=False),
        sa.ForeignKeyConstraint(['command_id'], ['command.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('idx_proof_command', 'command_proof', ['command_id'])
    
    # reward_ledger table
    op.create_table('reward_ledger',
        sa.Column('id', sa.UUID(), server_default=sa.text('gen_random_uuid()'), nullable=False),
        sa.Column('user_id', sa.UUID(), nullable=False),
        sa.Column('asset_id', sa.UUID(), nullable=True),
        sa.Column('event_type', sa.String(30), nullable=False),
        sa.Column('amount_awx', sa.Integer(), nullable=False),
        sa.Column('expires_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('reference_type', sa.String(30), nullable=True),
        sa.Column('reference_id', sa.UUID(), nullable=True),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('CURRENT_TIMESTAMP'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('CURRENT_TIMESTAMP'), nullable=False),
        sa.ForeignKeyConstraint(['user_id'], ['user.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['asset_id'], ['asset.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('event_type', 'reference_type', 'reference_id', name='uq_reward_event_ref')
    )
    op.create_index('idx_ledger_user_time', 'reward_ledger', ['user_id', 'created_at'])
    op.create_index('idx_ledger_asset', 'reward_ledger', ['asset_id'])
    
    # streak table
    op.create_table('streak',
        sa.Column('id', sa.UUID(), server_default=sa.text('gen_random_uuid()'), nullable=False),
        sa.Column('user_id', sa.UUID(), nullable=False),
        sa.Column('streak_type', sa.String(30), nullable=False),
        sa.Column('current_count', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('longest_count', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('last_date', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('CURRENT_TIMESTAMP'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('CURRENT_TIMESTAMP'), nullable=False),
        sa.ForeignKeyConstraint(['user_id'], ['user.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('user_id', 'streak_type', name='uq_user_streak')
    )
    op.create_index('idx_streak_user', 'streak', ['user_id'])
    
    # === MARKETPLACE MODULE ===
    
    # alarm table
    op.create_table('alarm',
        sa.Column('id', sa.UUID(), server_default=sa.text('gen_random_uuid()'), nullable=False),
        sa.Column('asset_id', sa.UUID(), nullable=False),
        sa.Column('device_id', sa.UUID(), nullable=True),
        sa.Column('severity', sa.String(20), nullable=False),
        sa.Column('message', sa.Text(), nullable=False),
        sa.Column('status', sa.String(20), nullable=False, server_default='open'),
        sa.Column('metadata', postgresql.JSONB(), nullable=True, server_default='{}'),
        sa.Column('acknowledged_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('acknowledged_by_user_id', sa.UUID(), nullable=True),
        sa.Column('closed_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('CURRENT_TIMESTAMP'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('CURRENT_TIMESTAMP'), nullable=False),
        sa.ForeignKeyConstraint(['asset_id'], ['asset.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['device_id'], ['device.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['acknowledged_by_user_id'], ['user.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('idx_alarm_asset', 'alarm', ['asset_id'])
    op.create_index('idx_alarm_status', 'alarm', ['status'])
    op.create_index('idx_alarm_severity', 'alarm', ['severity'])
    
    # job table
    op.create_table('job',
        sa.Column('id', sa.UUID(), server_default=sa.text('gen_random_uuid()'), nullable=False),
        sa.Column('asset_id', sa.UUID(), nullable=False),
        sa.Column('created_by_user_id', sa.UUID(), nullable=True),
        sa.Column('alarm_id', sa.UUID(), nullable=True),
        sa.Column('category', sa.String(30), nullable=False),
        sa.Column('title', sa.String(255), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('urgency', sa.String(20), nullable=False, server_default='normal'),
        sa.Column('status', sa.String(20), nullable=False, server_default='open'),
        sa.Column('assigned_operator_id', sa.UUID(), nullable=True),
        sa.Column('assigned_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('completed_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('rating', sa.Integer(), nullable=True),
        sa.Column('rating_comment', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('CURRENT_TIMESTAMP'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('CURRENT_TIMESTAMP'), nullable=False),
        sa.ForeignKeyConstraint(['asset_id'], ['asset.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['created_by_user_id'], ['user.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['alarm_id'], ['alarm.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['assigned_operator_id'], ['user.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('idx_job_asset', 'job', ['asset_id'])
    op.create_index('idx_job_status', 'job', ['status'])
    op.create_index('idx_job_category', 'job', ['category'])
    
    # job_offer table
    op.create_table('job_offer',
        sa.Column('id', sa.UUID(), server_default=sa.text('gen_random_uuid()'), nullable=False),
        sa.Column('job_id', sa.UUID(), nullable=False),
        sa.Column('operator_user_id', sa.UUID(), nullable=False),
        sa.Column('price_estimate', sa.Numeric(12, 2), nullable=True),
        sa.Column('currency', sa.String(3), nullable=False, server_default='TRY'),
        sa.Column('eta_minutes', sa.Integer(), nullable=True),
        sa.Column('message', sa.Text(), nullable=True),
        sa.Column('status', sa.String(20), nullable=False, server_default='offered'),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('CURRENT_TIMESTAMP'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('CURRENT_TIMESTAMP'), nullable=False),
        sa.ForeignKeyConstraint(['job_id'], ['job.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['operator_user_id'], ['user.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('idx_offer_job', 'job_offer', ['job_id'])
    op.create_index('idx_offer_operator', 'job_offer', ['operator_user_id'])
    op.create_index('idx_offer_status', 'job_offer', ['status'])
    
    # job_proof table
    op.create_table('job_proof',
        sa.Column('id', sa.UUID(), server_default=sa.text('gen_random_uuid()'), nullable=False),
        sa.Column('job_id', sa.UUID(), nullable=False),
        sa.Column('proof_type', sa.String(30), nullable=False),
        sa.Column('proof_payload', postgresql.JSONB(), nullable=False),
        sa.Column('uploaded_by_user_id', sa.UUID(), nullable=True),
        sa.Column('verified_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('CURRENT_TIMESTAMP'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('CURRENT_TIMESTAMP'), nullable=False),
        sa.ForeignKeyConstraint(['job_id'], ['job.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['uploaded_by_user_id'], ['user.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('idx_job_proof_job', 'job_proof', ['job_id'])


def downgrade() -> None:
    # Drop marketplace tables
    op.drop_table('job_proof')
    op.drop_table('job_offer')
    op.drop_table('job')
    op.drop_table('alarm')
    
    # Drop energy tables
    op.drop_table('streak')
    op.drop_table('reward_ledger')
    op.drop_table('command_proof')
    op.drop_table('command')
    op.drop_table('recommendation')
    
    # Drop IoT additions
    op.drop_table('device_state_event')
    op.drop_table('device_alias')
    op.drop_table('gateway_pairing_code')
    
    # Remove device columns
    op.drop_constraint('fk_device_zone_id_zone', 'device', type_='foreignkey')
    op.drop_index('idx_device_zone', 'device')
    op.drop_column('device', 'controllable')
    op.drop_column('device', 'safety_profile')
    op.drop_column('device', 'external_id')
    op.drop_column('device', 'zone_id')
    
    # Remove gateway columns
    op.drop_column('gateway', 'versions')
    op.drop_column('gateway', 'identity_key')
    
    # Drop real estate additions
    op.drop_table('handover_token')
    op.drop_table('tenancy')
    op.drop_table('asset_membership')
    op.drop_table('zone')
    
    # Drop compliance tables
    op.drop_table('audit_log')
    op.drop_table('consent')
