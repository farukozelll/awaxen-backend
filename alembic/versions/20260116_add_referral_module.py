"""Add referral module tables

Revision ID: 20260116_referral
Revises: 20260116_arch_improvements
Create Date: 2026-01-16

Changes:
- referral_campaign: Campaign definitions with reward rules
- referral_conversion: Tracking referrer/referee conversions
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = '20260116_referral'
down_revision = '20260116_arch_improvements'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # =========================================================================
    # REFERRAL CAMPAIGN TABLE
    # =========================================================================
    op.create_table(
        'referral_campaign',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False, server_default=sa.text('gen_random_uuid()')),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.Column('name', sa.String(255), nullable=False),
        sa.Column('slug', sa.String(100), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default='true'),
        sa.Column('start_date', sa.DateTime(timezone=True), nullable=True),
        sa.Column('end_date', sa.DateTime(timezone=True), nullable=True),
        sa.Column('reward_type', sa.String(50), nullable=False, server_default='balance'),
        sa.Column('referrer_reward_amount', sa.Numeric(18, 2), nullable=False, server_default='0'),
        sa.Column('referee_reward_amount', sa.Numeric(18, 2), nullable=False, server_default='0'),
        sa.Column('rules', postgresql.JSONB(), nullable=True),
        sa.Column('max_conversions', sa.Integer(), nullable=True),
        sa.Column('max_per_referrer', sa.Integer(), nullable=True),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('slug', name='uq_referral_campaign_slug'),
    )
    op.create_index('idx_campaign_active', 'referral_campaign', ['is_active'])
    op.create_index('idx_campaign_dates', 'referral_campaign', ['start_date', 'end_date'])

    # =========================================================================
    # REFERRAL CONVERSION TABLE
    # =========================================================================
    op.create_table(
        'referral_conversion',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False, server_default=sa.text('gen_random_uuid()')),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.Column('campaign_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('referrer_user_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('referee_user_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('status', sa.String(30), nullable=False, server_default='pending'),
        sa.Column('reward_transaction_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('reward_ledger_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('qualified_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('paid_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('metadata', postgresql.JSONB(), nullable=True),
        sa.ForeignKeyConstraint(['campaign_id'], ['referral_campaign.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['referrer_user_id'], ['user.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['referee_user_id'], ['user.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['reward_transaction_id'], ['transaction.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['reward_ledger_id'], ['reward_ledger.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('referee_user_id', name='uq_conversion_referee'),
    )
    op.create_index('idx_conversion_referrer_status', 'referral_conversion', ['referrer_user_id', 'status'])
    op.create_index('idx_conversion_campaign', 'referral_conversion', ['campaign_id'])
    op.create_index('ix_referral_conversion_referee_user_id', 'referral_conversion', ['referee_user_id'])


def downgrade() -> None:
    # Drop referral_conversion
    op.drop_index('ix_referral_conversion_referee_user_id', table_name='referral_conversion')
    op.drop_index('idx_conversion_campaign', table_name='referral_conversion')
    op.drop_index('idx_conversion_referrer_status', table_name='referral_conversion')
    op.drop_table('referral_conversion')

    # Drop referral_campaign
    op.drop_index('idx_campaign_dates', table_name='referral_campaign')
    op.drop_index('idx_campaign_active', table_name='referral_campaign')
    op.drop_table('referral_campaign')
