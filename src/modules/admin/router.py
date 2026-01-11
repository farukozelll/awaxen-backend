"""
Admin Module - Main Router

Clean Code: Bu dosya sadece alt router'ları birleştirir.
Hiçbir endpoint burada tanımlanmaz.

Yapı:
- routes/organizations.py → Organizasyon CRUD
- routes/users.py → Kullanıcı yönetimi
- routes/system.py → Sistem sağlığı
- routes/rewards.py → AWX Puan/Wallet yönetimi
"""
from fastapi import APIRouter

from src.modules.admin.routes import (
    organizations_router,
    users_router,
    system_router,
    rewards_router,
)

# Ana Admin Router - Prefix /admin
router = APIRouter(prefix="/admin")

# Alt router'ları birleştir
router.include_router(organizations_router)
router.include_router(users_router)
router.include_router(system_router)
router.include_router(rewards_router)
