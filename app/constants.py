"""
Awaxen Backend - Sabit Değerler ve Konfigürasyon.

Tüm magic number'lar ve hardcoded değerler burada tanımlanır.
"""
from enum import Enum


# ==========================================
# API SABITLERI
# ==========================================

# Pagination
DEFAULT_PAGE_SIZE = 20
MAX_PAGE_SIZE = 100
MIN_PAGE_SIZE = 1

# API Timeout (saniye)
API_TIMEOUT_SHORT = 10
API_TIMEOUT_DEFAULT = 30
API_TIMEOUT_LONG = 60

# Rate Limiting
RATE_LIMIT_PER_MINUTE = 60
RATE_LIMIT_PER_HOUR = 1000


# ==========================================
# CACHE SABITLERI
# ==========================================

# Cache TTL (saniye)
CACHE_TTL_SHORT = 60  # 1 dakika
CACHE_TTL_DEFAULT = 300  # 5 dakika
CACHE_TTL_LONG = 900  # 15 dakika
CACHE_TTL_HOUR = 3600  # 1 saat

# Weather cache
WEATHER_CACHE_TIMEOUT = 900  # 15 dakika
WEATHER_FORECAST_CACHE_TIMEOUT = 3600  # 1 saat
WEATHER_GEOCODE_CACHE_TIMEOUT = 86400  # 24 saat

# OpenWeather API
OPENWEATHER_BASE_URL = "https://api.openweathermap.org/data/2.5"
OPENWEATHER_GEO_URL = "https://api.openweathermap.org/geo/1.0"
WEATHER_DATA_RETENTION_DAYS = 30  # Eski hava durumu verilerini temizle


# ==========================================
# WALLET / GAMIFICATION SABITLERI
# ==========================================

# Streak hesaplama
STREAK_MAX_DAYS = 365

# XP sistemi
XP_PER_AWX = 10  # Her 1 AWX = 10 XP

# Seviye formülü: level^2 * LEVEL_XP_MULTIPLIER
LEVEL_XP_MULTIPLIER = 100

# Leaderboard
LEADERBOARD_MAX_LIMIT = 50
LEADERBOARD_DEFAULT_LIMIT = 10


# ==========================================
# OTOMASYON SABITLERI
# ==========================================

# Otomasyon öncelik aralığı
AUTOMATION_DEFAULT_PRIORITY = 100
AUTOMATION_PRIORITY_STEP = 10

# Celery task aralıkları (saniye)
AUTOMATION_CHECK_INTERVAL = 60  # Her dakika
INTEGRATION_SYNC_INTERVAL = 3600  # Her saat
PRICE_FETCH_INTERVAL = 3600  # Her saat


# ==========================================
# MQTT SABITLERI
# ==========================================

MQTT_MAX_RETRIES = 5
MQTT_RETRY_DELAY = 2.0  # saniye
MQTT_KEEPALIVE = 60
MQTT_CLIENT_ID_MAX_LENGTH = 23  # MQTT spec limit


# ==========================================
# EPİAŞ SABITLERI
# ==========================================

EPIAS_TGT_EXPIRY_SECONDS = 7000  # ~2 saat, biraz erken yenile
EPIAS_RETRY_COUNT = 2
EPIAS_TIMEZONE_OFFSET = "+03:00"


# ==========================================
# SHELLY SABITLERI
# ==========================================

SHELLY_API_TIMEOUT = 30
SHELLY_DEFAULT_CHANNEL = 0


# ==========================================
# DAVET SİSTEMİ
# ==========================================

INVITE_DEFAULT_EXPIRY_DAYS = 7
INVITE_MIN_EXPIRY_DAYS = 1
INVITE_TOKEN_LENGTH = 32


# ==========================================
# VERİ SAKLAMA
# ==========================================

# Eski verileri temizleme (gün)
PRICE_DATA_RETENTION_DAYS = 90
TELEMETRY_DATA_RETENTION_DAYS = 30
AUDIT_LOG_RETENTION_DAYS = 365


# ==========================================
# HTTP STATUS CODES (Okunabilirlik için)
# ==========================================

class HttpStatus:
    """HTTP durum kodları."""
    OK = 200
    CREATED = 201
    NO_CONTENT = 204
    BAD_REQUEST = 400
    UNAUTHORIZED = 401
    FORBIDDEN = 403
    NOT_FOUND = 404
    CONFLICT = 409
    UNPROCESSABLE_ENTITY = 422
    TOO_MANY_REQUESTS = 429
    INTERNAL_SERVER_ERROR = 500
    SERVICE_UNAVAILABLE = 503


# ==========================================
# ERROR CODES
# ==========================================

class ErrorCode:
    """Standart hata kodları."""
    # Auth
    MISSING_TOKEN = "missing_token"
    INVALID_TOKEN = "invalid_token"
    TOKEN_EXPIRED = "token_expired"
    INVALID_AUDIENCE = "invalid_audience"
    INVALID_ISSUER = "invalid_issuer"
    USER_NOT_FOUND = "user_not_found"
    USER_NOT_IN_DB = "user_not_in_db"
    
    # Authorization
    FORBIDDEN = "forbidden"
    INSUFFICIENT_PERMISSIONS = "insufficient_permissions"
    
    # Validation
    VALIDATION_ERROR = "validation_error"
    INVALID_INPUT = "invalid_input"
    MISSING_FIELD = "missing_field"
    INVALID_FORMAT = "invalid_format"
    
    # Resource
    RESOURCE_NOT_FOUND = "resource_not_found"
    RESOURCE_ALREADY_EXISTS = "resource_already_exists"
    RESOURCE_CONFLICT = "resource_conflict"
    
    # Database
    DATABASE_ERROR = "database_error"
    TRANSACTION_FAILED = "transaction_failed"
    
    # Server
    INTERNAL_SERVER_ERROR = "internal_server_error"
    
    # External Services
    EXTERNAL_SERVICE_ERROR = "external_service_error"
    INTEGRATION_ERROR = "integration_error"
    API_ERROR = "api_error"
    
    # Rate Limiting
    RATE_LIMIT_EXCEEDED = "rate_limit_exceeded"


# ==========================================
# VARSAYILAN DEĞERLER
# ==========================================

DEFAULT_TIMEZONE = "Europe/Istanbul"
DEFAULT_CURRENCY = "TRY"
DEFAULT_LANGUAGE = "tr"
DEFAULT_THEME = "system"

# Organizasyon
DEFAULT_ORGANIZATION_TYPE = "home"
DEFAULT_SUBSCRIPTION_PLAN = "free"
DEFAULT_SUBSCRIPTION_STATUS = "active"

# Cihaz
DEFAULT_DEVICE_STATUS = "offline"
DEFAULT_DEVICE_TYPE = "relay"

# Rol
DEFAULT_USER_ROLE = "viewer"
ADMIN_ROLES = ("super_admin", "admin")
SYSTEM_ROLES = ("super_admin", "admin", "operator", "viewer")
