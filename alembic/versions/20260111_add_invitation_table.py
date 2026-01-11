"""Add invitation table for user invitations

Revision ID: 20260111_invitation
Revises: 20260111_user_status
Create Date: 2026-01-11

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID


# revision identifiers, used by Alembic.
revision: str = '20260111_invitation'
down_revision: Union[str, None] = '20260111_user_status'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'invitation',
        sa.Column('id', UUID(as_uuid=True), primary_key=True),
        sa.Column('email', sa.String(255), nullable=False, index=True),
        sa.Column('token', sa.String(100), nullable=False, unique=True, index=True),
        sa.Column('organization_id', UUID(as_uuid=True), sa.ForeignKey('organization.id', ondelete='CASCADE'), nullable=False, index=True),
        sa.Column('role_code', sa.String(20), nullable=False, server_default='user'),
        sa.Column('invited_by_id', UUID(as_uuid=True), sa.ForeignKey('user.id', ondelete='SET NULL'), nullable=True),
        sa.Column('is_used', sa.Boolean(), nullable=False, server_default='false'),
        sa.Column('used_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('expires_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('message', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now(), onupdate=sa.func.now()),
    )


def downgrade() -> None:
    op.drop_table('invitation')
