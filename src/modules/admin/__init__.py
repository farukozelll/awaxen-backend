"""
Admin Module - System Administration

Clean Code Structure:
├── router.py      → Ana router (alt router'ları birleştirir)
├── service.py     → İş mantığı (AdminService)
├── dependencies.py → Dependency injection
└── routes/        → Endpoint dosyaları
    ├── organizations.py
    ├── users.py
    ├── system.py
    └── billing.py
"""
from src.modules.admin.router import router

__all__ = ["router"]
