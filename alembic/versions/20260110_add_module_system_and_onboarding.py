"""Add module system and user onboarding fields

Revision ID: 20260110_modules
Revises: 20260106_core
Create Date: 2026-01-10

New tables:
- organization_module: Organizasyona atanmış modüller

Modified tables:
- user: Onboarding alanları (first_name, last_name, address, notification_settings, consent_settings, onboarding_completed, fcm_token)
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = '20260110_modules'
down_revision: Union[str, None] = '20260106_core'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # === ORGANIZATION MODULE TABLE ===
    op.create_table('organization_module',
        sa.Column('id', sa.UUID(), server_default=sa.text('gen_random_uuid()'), nullable=False),
        sa.Column('organization_id', sa.UUID(), nullable=False),
        sa.Column('module_code', sa.String(50), nullable=False, comment='ModuleType enum value'),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default='true'),
        sa.Column('settings', postgresql.JSONB(), nullable=True),
        sa.Column('activated_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('CURRENT_TIMESTAMP'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('CURRENT_TIMESTAMP'), nullable=False),
        sa.ForeignKeyConstraint(['organization_id'], ['organization.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('organization_id', 'module_code', name='uq_org_module')
    )
    op.create_index('idx_org_module_org', 'organization_module', ['organization_id'])
    op.create_index('idx_org_module_code', 'organization_module', ['module_code'])
    
    # === USER TABLE MODIFICATIONS - Onboarding Fields ===
    
    # Kişisel bilgiler
    op.add_column('user', sa.Column('first_name', sa.String(100), nullable=True))
    op.add_column('user', sa.Column('last_name', sa.String(100), nullable=True))
    
    # Adres bilgileri
    op.add_column('user', sa.Column('country', sa.String(100), nullable=True))
    op.add_column('user', sa.Column('city', sa.String(100), nullable=True, comment='İl'))
    op.add_column('user', sa.Column('district', sa.String(100), nullable=True, comment='İlçe'))
    op.add_column('user', sa.Column('address', sa.Text(), nullable=True))
    op.add_column('user', sa.Column('postal_code', sa.String(20), nullable=True))
    
    # Bildirim ayarları
    op.add_column('user', sa.Column('notification_settings', postgresql.JSONB(), nullable=True,
        comment='push_enabled, email_enabled, telegram_enabled, sms_enabled'))
    
    # KVKK/GDPR onayları
    op.add_column('user', sa.Column('consent_settings', postgresql.JSONB(), nullable=True,
        comment='location, device_control, notifications, data_processing, marketing'))
    
    # Onboarding durumu
    op.add_column('user', sa.Column('onboarding_completed', sa.Boolean(), nullable=False, server_default='false'))
    op.add_column('user', sa.Column('onboarding_step', sa.Integer(), nullable=True, comment='Current onboarding step'))
    
    # Firebase Push Token
    op.add_column('user', sa.Column('fcm_token', sa.String(500), nullable=True))


def downgrade() -> None:
    # === USER TABLE - Remove onboarding fields ===
    op.drop_column('user', 'fcm_token')
    op.drop_column('user', 'onboarding_step')
    op.drop_column('user', 'onboarding_completed')
    op.drop_column('user', 'consent_settings')
    op.drop_column('user', 'notification_settings')
    op.drop_column('user', 'postal_code')
    op.drop_column('user', 'address')
    op.drop_column('user', 'district')
    op.drop_column('user', 'city')
    op.drop_column('user', 'country')
    op.drop_column('user', 'last_name')
    op.drop_column('user', 'first_name')
    
    # === ORGANIZATION MODULE TABLE ===
    op.drop_index('idx_org_module_code', table_name='organization_module')
    op.drop_index('idx_org_module_org', table_name='organization_module')
    op.drop_table('organization_module')
