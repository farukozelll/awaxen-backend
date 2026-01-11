"""
Admin Module - System Administration
Separated from Auth for clean domain boundaries.

This module handles:
- Organization lifecycle (create, suspend, delete, transfer ownership)
- User management (global search, ban, revoke sessions)
- System health and status
- Role and permission management
"""
from src.modules.admin.router import router

__all__ = ["router"]
