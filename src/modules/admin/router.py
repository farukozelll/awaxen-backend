"""
Admin Module - Main Router

Clean Code: Bu dosya sadece alt router'ları birleştirir.
Hiçbir endpoint burada tanımlanmaz.

Swagger Tag Numaraları:
- 10. 👑 Admin - Organizations
- 11. 👑 Admin - Users
- 12. 👑 Admin - System
- 13. 👑 Admin - Audit (compliance modülünde)
- 14. 👑 Admin - Rewards
"""
from fastapi import APIRouter

from src.modules.admin.routes import (
    organizations_router,
    rewards_router,
    system_router,
    users_router,
)

# Ana Admin Router - Prefix /admin
router = APIRouter(prefix="/admin")

# Alt router'ları birleştir
router.include_router(organizations_router)
router.include_router(users_router)
router.include_router(system_router)
router.include_router(rewards_router)
