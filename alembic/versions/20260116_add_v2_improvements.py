"""Add V2 architectural improvements

Revision ID: 20260116_v2_improvements
Revises: 20260116_referral
Create Date: 2026-01-16

Changes:
- Rename transaction -> wallet_transaction
- Add risk_level to recommendation
- Add zone_id to tariff_assignment
- Add health_status, last_data_at, offline_since to gateway
- Add device_coverage table
- Add tariff_assignment zone_id FK and constraint
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = '20260116_v2_improvements'
down_revision = '20260116_referral'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # =========================================================================
    # 1. RENAME transaction -> wallet_transaction
    # =========================================================================
    op.rename_table('transaction', 'wallet_transaction')
    
    # Update indexes (they keep old names, rename for clarity)
    # Note: PostgreSQL automatically renames constraints but not indexes
    
    # =========================================================================
    # 2. ADD risk_level TO recommendation
    # =========================================================================
    op.add_column(
        'recommendation',
        sa.Column(
            'risk_level',
            sa.String(20),
            nullable=False,
            server_default='low',
            comment='low/medium/high - affects user approval flow',
        )
    )
    
    # =========================================================================
    # 3. ADD zone_id TO tariff_assignment
    # =========================================================================
    op.add_column(
        'tariff_assignment',
        sa.Column(
            'zone_id',
            postgresql.UUID(as_uuid=True),
            nullable=True,
        )
    )
    op.create_foreign_key(
        'fk_tariff_assignment_zone',
        'tariff_assignment',
        'zone',
        ['zone_id'],
        ['id'],
        ondelete='CASCADE',
    )
    op.create_index('idx_tariff_assign_zone', 'tariff_assignment', ['zone_id'])
    
    # Update default priority from 0 to 10
    op.execute("UPDATE tariff_assignment SET priority = 10 WHERE priority = 0")
    
    # Add partial unique indexes to prevent duplicate active assignments
    # These use WHERE valid_to IS NULL to only apply to active assignments
    op.execute("""
        CREATE UNIQUE INDEX IF NOT EXISTS uq_tariff_assign_device_active 
        ON tariff_assignment (device_id, valid_from) 
        WHERE device_id IS NOT NULL AND valid_to IS NULL;
    """)
    op.execute("""
        CREATE UNIQUE INDEX IF NOT EXISTS uq_tariff_assign_zone_active 
        ON tariff_assignment (zone_id, valid_from) 
        WHERE zone_id IS NOT NULL AND valid_to IS NULL;
    """)
    op.execute("""
        CREATE UNIQUE INDEX IF NOT EXISTS uq_tariff_assign_asset_active 
        ON tariff_assignment (asset_id, valid_from) 
        WHERE asset_id IS NOT NULL AND valid_to IS NULL;
    """)
    
    # =========================================================================
    # 4. ADD health fields TO gateway
    # =========================================================================
    op.add_column(
        'gateway',
        sa.Column(
            'health_status',
            sa.String(20),
            nullable=False,
            server_default='unknown',
            comment='healthy/degraded/offline/unknown - for SLA monitoring',
        )
    )
    op.add_column(
        'gateway',
        sa.Column(
            'last_data_at',
            sa.DateTime(timezone=True),
            nullable=True,
            comment='Last telemetry data received timestamp',
        )
    )
    op.add_column(
        'gateway',
        sa.Column(
            'offline_since',
            sa.DateTime(timezone=True),
            nullable=True,
            comment='When gateway went offline (for SLA calculation)',
        )
    )
    
    # =========================================================================
    # 5. CREATE device_coverage TABLE
    # =========================================================================
    op.create_table(
        'device_coverage',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False, server_default=sa.text('gen_random_uuid()')),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.Column('device_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('asset_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('zone_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('ratio', sa.Numeric(5, 4), nullable=False, server_default='1.0'),
        sa.Column('coverage_type', sa.String(20), nullable=False, server_default='primary'),
        sa.Column('notes', sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(['device_id'], ['device.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['asset_id'], ['asset.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['zone_id'], ['zone.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('device_id', 'asset_id', 'zone_id', name='uq_device_coverage_target'),
    )
    op.create_index('idx_coverage_device', 'device_coverage', ['device_id'])
    op.create_index('idx_coverage_asset', 'device_coverage', ['asset_id'])
    op.create_index('idx_coverage_zone', 'device_coverage', ['zone_id'])
    
    # =========================================================================
    # 6. MAKE price_try_kwh A GENERATED COLUMN in energy_price
    # =========================================================================
    # Drop existing column and recreate as generated
    op.execute("""
        ALTER TABLE energy_price 
        DROP COLUMN IF EXISTS price_try_kwh;
    """)
    op.execute("""
        ALTER TABLE energy_price 
        ADD COLUMN price_try_kwh NUMERIC(8,6) 
        GENERATED ALWAYS AS (price_try_mwh / 1000) STORED;
    """)
    
    # =========================================================================
    # 7. UPDATE referral_conversion FK to wallet_transaction
    # =========================================================================
    # Drop old FK and create new one pointing to wallet_transaction
    op.drop_constraint('referral_conversion_reward_transaction_id_fkey', 'referral_conversion', type_='foreignkey')
    op.create_foreign_key(
        'fk_referral_conversion_wallet_transaction',
        'referral_conversion',
        'wallet_transaction',
        ['reward_transaction_id'],
        ['id'],
        ondelete='SET NULL',
    )


def downgrade() -> None:
    # Restore referral_conversion FK first (before renaming table)
    op.drop_constraint('fk_referral_conversion_wallet_transaction', 'referral_conversion', type_='foreignkey')
    
    # Rename wallet_transaction back to transaction
    op.rename_table('wallet_transaction', 'transaction')
    
    # Now create FK to restored transaction table
    op.create_foreign_key(
        'referral_conversion_reward_transaction_id_fkey',
        'referral_conversion',
        'transaction',
        ['reward_transaction_id'],
        ['id'],
        ondelete='SET NULL',
    )
    
    # Restore energy_price price_try_kwh as regular column
    op.execute("ALTER TABLE energy_price DROP COLUMN IF EXISTS price_try_kwh;")
    op.execute("ALTER TABLE energy_price ADD COLUMN price_try_kwh NUMERIC(8,6);")
    
    # Drop device_coverage
    op.drop_index('idx_coverage_zone', table_name='device_coverage')
    op.drop_index('idx_coverage_asset', table_name='device_coverage')
    op.drop_index('idx_coverage_device', table_name='device_coverage')
    op.drop_table('device_coverage')
    
    # Remove gateway health fields
    op.drop_column('gateway', 'offline_since')
    op.drop_column('gateway', 'last_data_at')
    op.drop_column('gateway', 'health_status')
    
    # Remove tariff_assignment unique indexes
    op.execute("DROP INDEX IF EXISTS uq_tariff_assign_device_active;")
    op.execute("DROP INDEX IF EXISTS uq_tariff_assign_zone_active;")
    op.execute("DROP INDEX IF EXISTS uq_tariff_assign_asset_active;")
    
    # Remove zone_id from tariff_assignment
    op.drop_index('idx_tariff_assign_zone', table_name='tariff_assignment')
    op.drop_constraint('fk_tariff_assignment_zone', 'tariff_assignment', type_='foreignkey')
    op.drop_column('tariff_assignment', 'zone_id')
    
    # Remove risk_level from recommendation
    op.drop_column('recommendation', 'risk_level')
