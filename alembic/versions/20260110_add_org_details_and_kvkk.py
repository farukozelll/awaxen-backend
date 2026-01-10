"""Add organization details and KVKK fields

Organization modeline:
- organization_type (villa, apartment, factory, vb.)
- company_size
- Detaylı adres: city, district, neighborhood, street, postal_code, country
- Koordinatlar: latitude, longitude

User modeline:
- kvkk_accepted, kvkk_accepted_at
- marketing_consent, marketing_consent_at

Revision ID: 20260110_org_kvkk
Revises: 20260110_wallet_type
Create Date: 2026-01-10
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '20260110_org_kvkk'
down_revision: Union[str, None] = '20260110_wallet_type'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ===== Organization tablosuna yeni alanlar ekle =====
    
    # Organization type
    op.add_column(
        'organization',
        sa.Column('organization_type', sa.String(50), nullable=True,
                  comment='villa, house, apartment, flat_1_1, factory, etc.')
    )
    
    # Company size
    op.add_column(
        'organization',
        sa.Column('company_size', sa.Integer(), nullable=True, default=0,
                  comment='Çalışan sayısı veya m2 büyüklüğü')
    )
    
    # Detaylı adres alanları
    op.add_column(
        'organization',
        sa.Column('city', sa.String(100), nullable=True,
                  comment='Şehir (İstanbul, Ankara, vb.)')
    )
    op.add_column(
        'organization',
        sa.Column('district', sa.String(100), nullable=True,
                  comment='İlçe (Kadıköy, Çankaya, vb.)')
    )
    op.add_column(
        'organization',
        sa.Column('neighborhood', sa.String(100), nullable=True,
                  comment='Mahalle')
    )
    op.add_column(
        'organization',
        sa.Column('street', sa.String(255), nullable=True,
                  comment='Sokak/Cadde ve kapı no')
    )
    op.add_column(
        'organization',
        sa.Column('postal_code', sa.String(20), nullable=True,
                  comment='Posta kodu')
    )
    op.add_column(
        'organization',
        sa.Column('country', sa.String(100), nullable=False, server_default='Türkiye')
    )
    
    # Koordinatlar
    op.add_column(
        'organization',
        sa.Column('latitude', sa.Float(), nullable=True,
                  comment='Enlem koordinatı')
    )
    op.add_column(
        'organization',
        sa.Column('longitude', sa.Float(), nullable=True,
                  comment='Boylam koordinatı')
    )
    
    # ===== User tablosuna KVKK alanları ekle =====
    
    op.add_column(
        'user',
        sa.Column('kvkk_accepted', sa.Boolean(), nullable=False, server_default='false',
                  comment='KVKK aydınlatma metni onayı')
    )
    op.add_column(
        'user',
        sa.Column('kvkk_accepted_at', sa.DateTime(timezone=True), nullable=True,
                  comment='KVKK onay tarihi')
    )
    op.add_column(
        'user',
        sa.Column('marketing_consent', sa.Boolean(), nullable=False, server_default='false',
                  comment='Pazarlama iletişimi onayı')
    )
    op.add_column(
        'user',
        sa.Column('marketing_consent_at', sa.DateTime(timezone=True), nullable=True,
                  comment='Pazarlama onay tarihi')
    )


def downgrade() -> None:
    # User KVKK alanlarını kaldır
    op.drop_column('user', 'marketing_consent_at')
    op.drop_column('user', 'marketing_consent')
    op.drop_column('user', 'kvkk_accepted_at')
    op.drop_column('user', 'kvkk_accepted')
    
    # Organization alanlarını kaldır
    op.drop_column('organization', 'longitude')
    op.drop_column('organization', 'latitude')
    op.drop_column('organization', 'country')
    op.drop_column('organization', 'postal_code')
    op.drop_column('organization', 'street')
    op.drop_column('organization', 'neighborhood')
    op.drop_column('organization', 'district')
    op.drop_column('organization', 'city')
    op.drop_column('organization', 'company_size')
    op.drop_column('organization', 'organization_type')
