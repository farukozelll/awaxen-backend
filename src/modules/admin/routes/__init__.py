"""
Admin Routes Package

Clean Code: Her dosya tek bir sorumluluk taşır.

Tag Numaraları:
- 10. 👑 Admin - Organizations (organizations.py)
- 11. 👑 Admin - Users (users.py)
- 12. 👑 Admin - System (system.py)
- 13. 👑 Admin - Audit (compliance/router.py)
- 14. 👑 Admin - Rewards (rewards.py)
"""
from src.modules.admin.routes.organizations import router as organizations_router
from src.modules.admin.routes.rewards import router as rewards_router
from src.modules.admin.routes.system import router as system_router
from src.modules.admin.routes.users import router as users_router

__all__ = [
    "organizations_router",
    "rewards_router",
    "system_router",
    "users_router",
]
