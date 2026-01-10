"""Add notification tables

Revision ID: 20260110_notifications
Revises: fix_roles_cleanup
Create Date: 2026-01-10

Tables:
- notification: In-app bildirimler
- user_fcm_token: FCM push token'ları
- notification_preference: Kullanıcı bildirim tercihleri
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = '20260110_notifications'
down_revision: Union[str, None] = 'fix_roles_cleanup'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # === NOTIFICATION TABLE ===
    op.create_table('notification',
        sa.Column('id', sa.UUID(), server_default=sa.text('gen_random_uuid()'), nullable=False),
        sa.Column('user_id', sa.UUID(), nullable=False),
        sa.Column('organization_id', sa.UUID(), nullable=True),
        sa.Column('type', sa.String(20), nullable=False, server_default='info'),
        sa.Column('priority', sa.String(20), nullable=False, server_default='medium'),
        sa.Column('title', sa.String(255), nullable=False),
        sa.Column('message', sa.Text(), nullable=False),
        sa.Column('data', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column('is_read', sa.Boolean(), nullable=False, server_default='false'),
        sa.Column('read_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('channels_sent', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column('source_type', sa.String(50), nullable=True),
        sa.Column('source_id', sa.UUID(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['user_id'], ['user.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['organization_id'], ['organization.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('idx_notification_user_read', 'notification', ['user_id', 'is_read', 'created_at'], unique=False)
    op.create_index('idx_notification_user_type', 'notification', ['user_id', 'type'], unique=False)
    op.create_index('ix_notification_user_id', 'notification', ['user_id'], unique=False)
    op.create_index('ix_notification_organization_id', 'notification', ['organization_id'], unique=False)
    
    # === USER FCM TOKEN TABLE ===
    op.create_table('user_fcm_token',
        sa.Column('id', sa.UUID(), server_default=sa.text('gen_random_uuid()'), nullable=False),
        sa.Column('user_id', sa.UUID(), nullable=False),
        sa.Column('token', sa.String(500), nullable=False),
        sa.Column('device_type', sa.String(20), nullable=True),
        sa.Column('device_name', sa.String(100), nullable=True),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default='true'),
        sa.Column('last_used_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['user_id'], ['user.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('token', name='uq_fcm_token')
    )
    op.create_index('ix_user_fcm_token_user_id', 'user_fcm_token', ['user_id'], unique=False)
    
    # === NOTIFICATION PREFERENCE TABLE ===
    op.create_table('notification_preference',
        sa.Column('id', sa.UUID(), server_default=sa.text('gen_random_uuid()'), nullable=False),
        sa.Column('user_id', sa.UUID(), nullable=False),
        sa.Column('push_enabled', sa.Boolean(), nullable=False, server_default='true'),
        sa.Column('telegram_enabled', sa.Boolean(), nullable=False, server_default='false'),
        sa.Column('email_enabled', sa.Boolean(), nullable=False, server_default='true'),
        sa.Column('in_app_enabled', sa.Boolean(), nullable=False, server_default='true'),
        sa.Column('quiet_hours_enabled', sa.Boolean(), nullable=False, server_default='false'),
        sa.Column('quiet_hours_start', sa.String(5), nullable=True),
        sa.Column('quiet_hours_end', sa.String(5), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['user_id'], ['user.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('user_id', name='uq_notification_preference_user')
    )


def downgrade() -> None:
    op.drop_table('notification_preference')
    op.drop_table('user_fcm_token')
    op.drop_index('ix_notification_organization_id', table_name='notification')
    op.drop_index('ix_notification_user_id', table_name='notification')
    op.drop_index('idx_notification_user_type', table_name='notification')
    op.drop_index('idx_notification_user_read', table_name='notification')
    op.drop_table('notification')
