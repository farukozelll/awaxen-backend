"""Add user status column

Revision ID: 20260111_user_status
Revises: 20260110_wallet_type
Create Date: 2026-01-11

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '20260111_user_status'
down_revision: Union[str, None] = '20260110_org_kvkk'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add status column to user table
    op.add_column('user', sa.Column('status', sa.String(20), nullable=False, server_default='active'))
    
    # Add login tracking columns to user table
    op.add_column('user', sa.Column('last_login_ip', sa.String(45), nullable=True))
    op.add_column('user', sa.Column('last_login_user_agent', sa.String(500), nullable=True))
    
    # Add MFA and preferences columns to user table
    op.add_column('user', sa.Column('mfa_enabled', sa.Boolean(), nullable=False, server_default='false'))
    op.add_column('user', sa.Column('preferences', sa.JSON(), nullable=True))
    
    # Add status column to organization table
    op.add_column('organization', sa.Column('status', sa.String(20), nullable=False, server_default='active'))


def downgrade() -> None:
    op.drop_column('user', 'status')
    op.drop_column('user', 'last_login_ip')
    op.drop_column('user', 'last_login_user_agent')
    op.drop_column('user', 'mfa_enabled')
    op.drop_column('user', 'preferences')
    op.drop_column('organization', 'status')
