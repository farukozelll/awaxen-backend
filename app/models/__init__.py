"""
Awaxen Models Package.

Tüm SQLAlchemy modelleri bu paketten import edilir.
Geriye uyumluluk için eski app.models import'ları çalışmaya devam eder.
"""
from app.models.base import TimestampMixin, SoftDeleteMixin
from app.models.rbac import Permission, Role, role_permissions
from app.models.organization import Organization
from app.models.user import User, UserSettings, UserInvite
from app.models.gateway import Gateway
from app.models.integration import Integration
from app.models.device import SmartDevice, SmartAsset, DeviceTelemetry
from app.models.automation import Automation, AutomationLog, VppRule
from app.models.market import MarketPrice
from app.models.wallet import Wallet, WalletTransaction
from app.models.notification import Notification
from app.models.audit import AuditLog
from app.models.weather import WeatherData, WeatherForecast
from app.models.billing import SubscriptionPlan, Subscription, Invoice, PaymentMethod
from app.models.firmware import Firmware, FirmwareUpdate
from app.models.export import DataExport
from app.models.ai_analysis import AIAnalysisTask, AIDetection, AITaskStatus, DefectType
from app.models.enums import (
    OrganizationType,
    DeviceStatus,
    IntegrationProvider,
    SubscriptionStatus,
    NotificationStatus,
    AssetType,
)

__all__ = [
    # Mixins
    "TimestampMixin",
    "SoftDeleteMixin",
    # Enums
    "OrganizationType",
    "DeviceStatus",
    "IntegrationProvider",
    "SubscriptionStatus",
    "NotificationStatus",
    "AssetType",
    # RBAC
    "Permission",
    "Role",
    "role_permissions",
    # Core
    "Organization",
    "User",
    "UserSettings",
    "UserInvite",
    # Connectivity
    "Gateway",
    "Integration",
    # Devices
    "SmartDevice",
    "SmartAsset",
    "DeviceTelemetry",
    # Automation
    "Automation",
    "AutomationLog",
    "VppRule",
    # Market
    "MarketPrice",
    # Wallet
    "Wallet",
    "WalletTransaction",
    # Notification
    "Notification",
    # Audit
    "AuditLog",
    # Weather
    "WeatherData",
    "WeatherForecast",
    # Billing
    "SubscriptionPlan",
    "Subscription",
    "Invoice",
    "PaymentMethod",
    # Firmware
    "Firmware",
    "FirmwareUpdate",
    # Export
    "DataExport",
    # AI Analysis
    "AIAnalysisTask",
    "AIDetection",
    "AITaskStatus",
    "DefectType",
]
