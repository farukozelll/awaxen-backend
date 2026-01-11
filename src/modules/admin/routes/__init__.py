"""
Admin Routes Package

Clean Code: Her dosya tek bir sorumluluk taşır.
- organizations.py: Organizasyon CRUD
- users.py: Kullanıcı yönetimi
- system.py: Sistem sağlığı ve loglar
- rewards.py: AWX Puan/Wallet yönetimi
"""
from src.modules.admin.routes.organizations import router as organizations_router
from src.modules.admin.routes.users import router as users_router
from src.modules.admin.routes.system import router as system_router
from src.modules.admin.routes.rewards import router as rewards_router

__all__ = [
    "organizations_router",
    "users_router", 
    "system_router",
    "rewards_router",
]
