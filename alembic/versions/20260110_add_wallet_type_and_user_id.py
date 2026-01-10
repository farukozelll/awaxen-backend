"""Add wallet_type and user_id to wallet table

Revision ID: 20260110_wallet_type
Revises: 75790e51fe08
Create Date: 2026-01-10

Wallet Türleri:
- COMPANY: Organizasyon cüzdanı (TL/USD - Fatura ödemeleri)
- PERSONAL: Kullanıcı cüzdanı (AWX Puan - Ödül/Motivasyon)
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '20260110_wallet_type'
down_revision: Union[str, None] = '20260110_notifications'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Add wallet_type column with default 'company'
    op.add_column(
        'wallet',
        sa.Column(
            'wallet_type',
            sa.String(20),
            nullable=False,
            server_default='company',
            comment='company=Organizasyon, personal=Kullanıcı'
        )
    )
    
    # 2. Add user_id column (nullable for existing COMPANY wallets)
    op.add_column(
        'wallet',
        sa.Column(
            'user_id',
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey('user.id', ondelete='CASCADE'),
            nullable=True
        )
    )
    
    # 3. Create indexes
    op.create_index('ix_wallet_user', 'wallet', ['user_id'])
    op.create_index('ix_wallet_type', 'wallet', ['wallet_type'])
    
    # 4. Create unique constraint for user wallets
    op.create_unique_constraint(
        'uq_wallet_user_currency',
        'wallet',
        ['user_id', 'currency']
    )
    
    # 5. Add check constraint for wallet owner validation
    op.execute("""
        ALTER TABLE wallet ADD CONSTRAINT ck_wallet_owner CHECK (
            (wallet_type = 'company' AND organization_id IS NOT NULL AND user_id IS NULL)
            OR
            (wallet_type = 'personal' AND user_id IS NOT NULL)
        )
    """)
    
    # 6. Update existing wallets to have wallet_type = 'company'
    op.execute("UPDATE wallet SET wallet_type = 'company' WHERE wallet_type IS NULL OR wallet_type = ''")


def downgrade() -> None:
    # Remove check constraint
    op.execute("ALTER TABLE wallet DROP CONSTRAINT IF EXISTS ck_wallet_owner")
    
    # Remove unique constraint
    op.drop_constraint('uq_wallet_user_currency', 'wallet', type_='unique')
    
    # Remove indexes
    op.drop_index('ix_wallet_type', table_name='wallet')
    op.drop_index('ix_wallet_user', table_name='wallet')
    
    # Remove columns
    op.drop_column('wallet', 'user_id')
    op.drop_column('wallet', 'wallet_type')
