"""Fix roles - cleanup org_admin and set first user as admin

Revision ID: fix_roles_cleanup
Revises: 
Create Date: 2026-01-10

Bu migration:
1. org_admin rolünü tenant'a dönüştürür
2. İlk kullanıcıyı (faruk.ozelll@outlook.com) admin yapar
3. Sadece 4 rol kalır: admin, tenant, user, device
"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'fix_roles_cleanup'
down_revision = '20260110_modules'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 1. Admin rolünü oluştur veya güncelle
    # NOT: permissions ARRAY type, JSONB değil - PostgreSQL array syntax kullan
    op.execute("""
        INSERT INTO role (id, name, code, description, permissions, is_system, created_at, updated_at)
        VALUES (
            gen_random_uuid(),
            'Admin',
            'admin',
            'Sistem yöneticisi - tüm yetkiler',
            ARRAY['*'],
            true,
            NOW(),
            NOW()
        )
        ON CONFLICT (code) DO UPDATE SET
            name = 'Admin',
            description = 'Sistem yöneticisi - tüm yetkiler',
            permissions = ARRAY['*'],
            updated_at = NOW();
    """)
    
    # 2. Tenant rolünü oluştur veya güncelle
    op.execute("""
        INSERT INTO role (id, name, code, description, permissions, is_system, created_at, updated_at)
        VALUES (
            gen_random_uuid(),
            'Tenant',
            'tenant',
            'Organizasyon yöneticisi',
            ARRAY['org:read', 'org:update', 'user:create', 'user:read', 'user:update', 'asset:create', 'asset:read', 'asset:update', 'asset:delete', 'zone:create', 'zone:read', 'zone:update', 'zone:delete', 'device:create', 'device:read', 'device:update', 'device:delete', 'device:control', 'gateway:create', 'gateway:read', 'gateway:update', 'gateway:delete', 'telemetry:read', 'energy:read', 'recommendation:read', 'recommendation:approve', 'reward:read', 'ledger:read', 'billing:read'],
            true,
            NOW(),
            NOW()
        )
        ON CONFLICT (code) DO UPDATE SET
            name = 'Tenant',
            description = 'Organizasyon yöneticisi',
            updated_at = NOW();
    """)
    
    # 3. User rolünü oluştur veya güncelle
    op.execute("""
        INSERT INTO role (id, name, code, description, permissions, is_system, created_at, updated_at)
        VALUES (
            gen_random_uuid(),
            'User',
            'user',
            'Normal kullanıcı - salt okunur',
            ARRAY['org:read', 'user:read', 'asset:read', 'zone:read', 'device:read', 'telemetry:read', 'energy:read', 'recommendation:read', 'reward:read', 'ledger:read'],
            true,
            NOW(),
            NOW()
        )
        ON CONFLICT (code) DO UPDATE SET
            name = 'User',
            description = 'Normal kullanıcı - salt okunur',
            updated_at = NOW();
    """)
    
    # 4. Device rolünü oluştur veya güncelle
    op.execute("""
        INSERT INTO role (id, name, code, description, permissions, is_system, created_at, updated_at)
        VALUES (
            gen_random_uuid(),
            'Device',
            'device',
            'Cihaz/Telemetri erişimi',
            ARRAY['telemetry:read', 'telemetry:write', 'device:read'],
            true,
            NOW(),
            NOW()
        )
        ON CONFLICT (code) DO UPDATE SET
            name = 'Device',
            description = 'Cihaz/Telemetri erişimi',
            updated_at = NOW();
    """)
    
    # 5. org_admin rolündeki kullanıcıları tenant'a taşı
    op.execute("""
        UPDATE organization_user ou
        SET role_id = (SELECT id FROM role WHERE code = 'tenant')
        WHERE role_id IN (SELECT id FROM role WHERE code = 'org_admin');
    """)
    
    # 6. org_admin rolünü sil
    op.execute("""
        DELETE FROM role WHERE code = 'org_admin';
    """)
    
    # 7. İlk kullanıcıyı (faruk.ozelll@outlook.com) admin yap
    op.execute("""
        UPDATE organization_user ou
        SET role_id = (SELECT id FROM role WHERE code = 'admin')
        WHERE user_id = (SELECT id FROM "user" WHERE email = 'faruk.ozelll@outlook.com')
        AND is_default = true;
    """)
    
    # 8. Geçersiz rolleri temizle (admin, tenant, user, device dışındakileri sil)
    op.execute("""
        DELETE FROM role 
        WHERE code NOT IN ('admin', 'tenant', 'user', 'device');
    """)


def downgrade() -> None:
    # Downgrade: org_admin rolünü geri oluştur
    op.execute("""
        INSERT INTO role (id, name, code, description, permissions, is_system, created_at, updated_at)
        VALUES (
            gen_random_uuid(),
            'Organization Admin',
            'org_admin',
            'Organizasyon yöneticisi (eski)',
            '["*"]',
            true,
            NOW(),
            NOW()
        )
        ON CONFLICT (code) DO NOTHING;
    """)
