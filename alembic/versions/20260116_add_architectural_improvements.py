"""Add architectural improvements: telemetry denormalization, saving verification, pricing models

Revision ID: 20260116_arch_improvements
Revises: 20260111_add_invitation_table
Create Date: 2026-01-16

Changes:
A) TelemetryData: Add organization_id (denormalized) + new indexes
B) SavingVerification: New table for structured saving proof
C) EnergyPrice, TariffProfile, TariffAssignment: Pricing/tariff models
D) MetricDefinition: Standardized metric definitions + telemetry reference
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = '20260116_arch_improvements'
down_revision = '20260111_add_user_status_column'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # =========================================================================
    # D) METRIC DEFINITION TABLE
    # =========================================================================
    op.create_table(
        'metric_definition',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False, server_default=sa.text('gen_random_uuid()')),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.Column('organization_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('name', sa.String(50), nullable=False),
        sa.Column('display_name', sa.String(100), nullable=True),
        sa.Column('unit', sa.String(20), nullable=False),
        sa.Column('device_type', sa.String(30), nullable=True),
        sa.Column('canonical_name', sa.String(50), nullable=True),
        sa.Column('min_value', sa.Numeric(18, 6), nullable=True),
        sa.Column('max_value', sa.Numeric(18, 6), nullable=True),
        sa.Column('description', sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(['organization_id'], ['organization.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('organization_id', 'name', name='uq_metric_def_org_name'),
    )
    op.create_index('ix_metric_def_device_type', 'metric_definition', ['device_type'])
    op.create_index('ix_metric_definition_name', 'metric_definition', ['name'])
    op.create_index('ix_metric_definition_organization_id', 'metric_definition', ['organization_id'])

    # =========================================================================
    # A) TELEMETRY DATA - Add organization_id and metric_definition_id
    # =========================================================================
    # Add organization_id column (denormalized for performance)
    op.add_column(
        'telemetry_data',
        sa.Column(
            'organization_id',
            postgresql.UUID(as_uuid=True),
            nullable=True,  # Initially nullable for existing data
            comment='Denormalized from device for query performance'
        )
    )
    
    # Add metric_definition_id column (optional reference)
    op.add_column(
        'telemetry_data',
        sa.Column(
            'metric_definition_id',
            postgresql.UUID(as_uuid=True),
            nullable=True,
            comment='Optional reference to metric definition'
        )
    )
    
    # Backfill organization_id from device table
    op.execute("""
        UPDATE telemetry_data td
        SET organization_id = d.organization_id
        FROM device d
        WHERE td.device_id = d.id
        AND td.organization_id IS NULL
    """)
    
    # Make organization_id NOT NULL after backfill
    op.alter_column('telemetry_data', 'organization_id', nullable=False)
    
    # Add foreign key constraints
    op.create_foreign_key(
        'fk_telemetry_data_organization_id_organization',
        'telemetry_data', 'organization',
        ['organization_id'], ['id'],
        ondelete='CASCADE'
    )
    op.create_foreign_key(
        'fk_telemetry_data_metric_definition_id_metric_definition',
        'telemetry_data', 'metric_definition',
        ['metric_definition_id'], ['id'],
        ondelete='SET NULL'
    )
    
    # Create new indexes for tenant filtering
    op.create_index('ix_telemetry_org_time', 'telemetry_data', ['organization_id', 'timestamp'])
    op.create_index('ix_telemetry_org_device_time', 'telemetry_data', ['organization_id', 'device_id', 'timestamp'])
    op.create_index('ix_telemetry_data_metric_definition_id', 'telemetry_data', ['metric_definition_id'])

    # =========================================================================
    # B) SAVING VERIFICATION TABLE
    # =========================================================================
    op.create_table(
        'saving_verification',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False, server_default=sa.text('gen_random_uuid()')),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.Column('recommendation_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('baseline_window_start', sa.DateTime(timezone=True), nullable=False),
        sa.Column('baseline_window_end', sa.DateTime(timezone=True), nullable=False),
        sa.Column('baseline_kwh', sa.Numeric(12, 4), nullable=False),
        sa.Column('compare_window_start', sa.DateTime(timezone=True), nullable=False),
        sa.Column('compare_window_end', sa.DateTime(timezone=True), nullable=False),
        sa.Column('compare_kwh', sa.Numeric(12, 4), nullable=False),
        sa.Column('saved_kwh', sa.Numeric(12, 4), nullable=False),
        sa.Column('saved_try', sa.Numeric(12, 2), nullable=False),
        sa.Column('confidence', sa.Numeric(5, 2), nullable=False),
        sa.Column('method', sa.String(20), nullable=False),
        sa.Column('verified_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('verification_details', postgresql.JSONB(), nullable=True),
        sa.ForeignKeyConstraint(['recommendation_id'], ['recommendation.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('recommendation_id', name='uq_saving_verification_recommendation'),
    )
    op.create_index('idx_saving_verif_reco', 'saving_verification', ['recommendation_id'])
    op.create_index('idx_saving_verif_time', 'saving_verification', ['verified_at'])

    # =========================================================================
    # C) ENERGY PRICE TABLE
    # =========================================================================
    op.create_table(
        'energy_price',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False, server_default=sa.text('gen_random_uuid()')),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.Column('timestamp', sa.DateTime(timezone=True), nullable=False),
        sa.Column('market', sa.String(20), nullable=False),
        sa.Column('price_try_mwh', sa.Numeric(12, 2), nullable=False),
        sa.Column('price_try_kwh', sa.Numeric(8, 6), nullable=False),
        sa.Column('region', sa.String(20), nullable=False, server_default='TR'),
        sa.Column('source', sa.String(50), nullable=False),
        sa.Column('volume_mwh', sa.Numeric(14, 2), nullable=True),
        sa.Column('metadata', postgresql.JSONB(), nullable=True),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('timestamp', 'market', 'region', name='uq_price_ts_market_region'),
    )
    op.create_index('idx_price_time', 'energy_price', ['timestamp'])
    op.create_index('idx_price_market_time', 'energy_price', ['market', 'timestamp'])
    op.create_index('ix_energy_price_market', 'energy_price', ['market'])

    # =========================================================================
    # C) TARIFF PROFILE TABLE
    # =========================================================================
    op.create_table(
        'tariff_profile',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False, server_default=sa.text('gen_random_uuid()')),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.Column('organization_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('name', sa.String(100), nullable=False),
        sa.Column('tariff_type', sa.String(20), nullable=False),
        sa.Column('rate_peak', sa.Numeric(8, 6), nullable=True),
        sa.Column('rate_day', sa.Numeric(8, 6), nullable=True),
        sa.Column('rate_night', sa.Numeric(8, 6), nullable=True),
        sa.Column('rate_single', sa.Numeric(8, 6), nullable=True),
        sa.Column('peak_hours', postgresql.JSONB(), nullable=True),
        sa.Column('day_hours', postgresql.JSONB(), nullable=True),
        sa.Column('night_hours', postgresql.JSONB(), nullable=True),
        sa.Column('distribution_fee', sa.Numeric(8, 6), nullable=False, server_default='0'),
        sa.Column('tax_rate', sa.Numeric(5, 4), nullable=False, server_default='0.20'),
        sa.Column('demand_charge_try_kw', sa.Numeric(10, 2), nullable=True),
        sa.Column('valid_from', sa.DateTime(timezone=True), nullable=False),
        sa.Column('valid_to', sa.DateTime(timezone=True), nullable=True),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default='true'),
        sa.ForeignKeyConstraint(['organization_id'], ['organization.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('organization_id', 'name', name='uq_tariff_org_name'),
    )
    op.create_index('idx_tariff_org', 'tariff_profile', ['organization_id'])

    # =========================================================================
    # C) TARIFF ASSIGNMENT TABLE
    # =========================================================================
    op.create_table(
        'tariff_assignment',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False, server_default=sa.text('gen_random_uuid()')),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.Column('tariff_profile_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('asset_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('device_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('priority', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('valid_from', sa.DateTime(timezone=True), nullable=False),
        sa.Column('valid_to', sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(['tariff_profile_id'], ['tariff_profile.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['asset_id'], ['asset.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['device_id'], ['device.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('idx_tariff_assign_asset', 'tariff_assignment', ['asset_id'])
    op.create_index('idx_tariff_assign_device', 'tariff_assignment', ['device_id'])
    op.create_index('ix_tariff_assignment_tariff_profile_id', 'tariff_assignment', ['tariff_profile_id'])


def downgrade() -> None:
    # Drop tariff_assignment
    op.drop_index('ix_tariff_assignment_tariff_profile_id', table_name='tariff_assignment')
    op.drop_index('idx_tariff_assign_device', table_name='tariff_assignment')
    op.drop_index('idx_tariff_assign_asset', table_name='tariff_assignment')
    op.drop_table('tariff_assignment')

    # Drop tariff_profile
    op.drop_index('idx_tariff_org', table_name='tariff_profile')
    op.drop_table('tariff_profile')

    # Drop energy_price
    op.drop_index('ix_energy_price_market', table_name='energy_price')
    op.drop_index('idx_price_market_time', table_name='energy_price')
    op.drop_index('idx_price_time', table_name='energy_price')
    op.drop_table('energy_price')

    # Drop saving_verification
    op.drop_index('idx_saving_verif_time', table_name='saving_verification')
    op.drop_index('idx_saving_verif_reco', table_name='saving_verification')
    op.drop_table('saving_verification')

    # Remove telemetry_data columns and indexes
    op.drop_index('ix_telemetry_data_metric_definition_id', table_name='telemetry_data')
    op.drop_index('ix_telemetry_org_device_time', table_name='telemetry_data')
    op.drop_index('ix_telemetry_org_time', table_name='telemetry_data')
    op.drop_constraint('fk_telemetry_data_metric_definition_id_metric_definition', 'telemetry_data', type_='foreignkey')
    op.drop_constraint('fk_telemetry_data_organization_id_organization', 'telemetry_data', type_='foreignkey')
    op.drop_column('telemetry_data', 'metric_definition_id')
    op.drop_column('telemetry_data', 'organization_id')

    # Drop metric_definition
    op.drop_index('ix_metric_definition_organization_id', table_name='metric_definition')
    op.drop_index('ix_metric_definition_name', table_name='metric_definition')
    op.drop_index('ix_metric_def_device_type', table_name='metric_definition')
    op.drop_table('metric_definition')
