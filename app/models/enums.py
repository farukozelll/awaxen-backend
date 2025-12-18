"""
Awaxen Models - Enum Tanımları.

Tüm model enum'ları burada tanımlanır.
"""
from enum import Enum


class OrganizationType(str, Enum):
    """Organizasyon tipi - SaaS tenant türü."""
    HOME = "home"                # Ev kullanıcısı (B2C)
    AGRICULTURE = "agriculture"  # Tarım işletmesi
    INDUSTRIAL = "industrial"    # Endüstriyel tesis
    COMMERCIAL = "commercial"    # Ticari bina


class DeviceStatus(str, Enum):
    """Cihaz durumu."""
    ONLINE = "ONLINE"
    OFFLINE = "OFFLINE"
    ERROR = "ERROR"


class IntegrationProvider(str, Enum):
    """Bulut entegrasyon sağlayıcıları."""
    SHELLY = "shelly"
    TESLA = "tesla"
    TAPO = "tapo"
    TUYA = "tuya"
    HUAWEI_FUSIONSOLAR = "huawei_fusionsolar"
    SUNGROW = "sungrow"


class SubscriptionStatus(str, Enum):
    """Abonelik durumu."""
    ACTIVE = "active"
    TRIAL = "trial"
    SUSPENDED = "suspended"
    CANCELLED = "cancelled"


class NotificationStatus(str, Enum):
    """Bildirim durumu."""
    PENDING = "pending"
    SENT = "sent"
    FAILED = "failed"
    READ = "read"


class AssetType(str, Enum):
    """Varlık tipi."""
    HVAC = "hvac"              # Klima/Isıtma
    EV_CHARGER = "ev_charger"  # Elektrikli araç şarjı
    WATER_HEATER = "water_heater"  # Su ısıtıcı
    HEATER = "heater"          # Isıtıcı
    APPLIANCE = "appliance"    # Ev aleti
    LIGHTING = "lighting"      # Aydınlatma
    OTHER = "other"


class TransactionType(str, Enum):
    """Cüzdan işlem tipi."""
    REWARD = "reward"
    PENALTY = "penalty"
    WITHDRAWAL = "withdrawal"
    BONUS = "bonus"
    REFERRAL = "referral"


class TransactionCategory(str, Enum):
    """Cüzdan işlem kategorisi."""
    ENERGY_SAVING = "energy_saving"
    AUTOMATION = "automation"
    CHALLENGE = "challenge"
    MANUAL = "manual"


class TriggerType(str, Enum):
    """Otomasyon tetikleyici tipi."""
    PRICE = "price"
    TIME_RANGE = "time_range"
    SENSOR = "sensor"
    ALWAYS = "always"


class ActionType(str, Enum):
    """Otomasyon aksiyon tipi."""
    TURN_ON = "turn_on"
    TURN_OFF = "turn_off"
    TOGGLE = "toggle"
    SET_POWER = "set_power"
    CUSTOM = "custom"


class NotificationType(str, Enum):
    """Bildirim tipi."""
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    SUCCESS = "success"
    PRICE_ALERT = "price_alert"
    DEVICE_ALERT = "device_alert"
    AUTOMATION = "automation"


class NotificationChannel(str, Enum):
    """Bildirim kanalı."""
    IN_APP = "in_app"
    TELEGRAM = "telegram"
    EMAIL = "email"
    PUSH = "push"
    SMS = "sms"
