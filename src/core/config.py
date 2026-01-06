"""
Core Configuration Module
Uses pydantic-settings for environment variable management.
All secrets loaded from .env file - NEVER hardcode secrets.
"""
from functools import lru_cache

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # Application
    project_name: str = "Awaxen"
    environment: str = Field(default="development", description="development | staging | production")
    debug: bool = Field(default=True, alias="FLASK_DEBUG")
    api_v1_str: str = "/api/v1"

    # Database - PostgreSQL + TimescaleDB (supports both formats)
    database_url: str = Field(
        default="postgresql+asyncpg://awaxen_user:awaxen_secret_password@db:5432/awaxen_core",
        description="Full database URL (takes precedence)",
    )
    db_host: str = Field(default="db", description="Database host")
    db_port: int = Field(default=5432, description="Database port")
    db_name: str = Field(default="awaxen_core", description="Database name")
    db_user: str = Field(default="awaxen_user", description="Database user")
    db_password: str = Field(default="awaxen_secret_password", description="Database password")
    db_pool_size: int = Field(default=20, description="SQLAlchemy connection pool size")
    db_max_overflow: int = Field(default=10, description="Max overflow connections")
    db_echo: bool = Field(default=False, description="Echo SQL queries")

    # Redis
    redis_url: str = Field(default="redis://redis:6379/0", description="Redis connection URL")

    # MQTT - IoT (Shelly devices)
    mqtt_broker_url: str = Field(default="mqtt", alias="MQTT_BROKER_URL", description="MQTT Broker hostname")
    mqtt_broker_port: int = Field(default=1883, description="MQTT Broker port")
    mqtt_username: str = Field(default="awaxen_admin", description="MQTT username")
    mqtt_password: str = Field(default="", description="MQTT password")
    mqtt_client_id: str = Field(default="awaxen-backend", description="MQTT Client ID")
    mqtt_sensor_topic: str = Field(default="awaxen/sensors/#", description="MQTT sensor topic pattern")

    # MinIO - S3 Compatible Storage
    minio_endpoint: str = Field(default="minio:9000", description="MinIO endpoint")
    minio_access_key: str = Field(default="minioadmin", description="MinIO access key")
    minio_secret_key: str = Field(default="minioadmin", description="MinIO secret key")
    minio_bucket_name: str = Field(default="awaxen", description="Default bucket name")
    minio_secure: bool = Field(default=False, description="Use HTTPS for MinIO")

    # Security
    secret_key: str = Field(default="CHANGE_ME_IN_PRODUCTION", description="JWT/Flask Secret Key")
    algorithm: str = Field(default="HS256", description="JWT Algorithm")
    access_token_expire_minutes: int = Field(default=60 * 24, description="Token expiry in minutes")
    encryption_key: str = Field(default="", description="Fernet key for encrypting sensitive data (API keys)")

    # Auth0
    auth0_domain: str = Field(default="", description="Auth0 domain")
    auth0_audience: str = Field(default="", description="Auth0 API audience")
    auth0_client_id: str = Field(default="", description="Auth0 client ID")

    # CORS
    cors_origins: str = Field(default="http://localhost:3005", description="Allowed CORS origins")
    backend_cors_origins: str = Field(default="", description="CORS origins as comma-separated string")

    # Superuser
    first_superuser_email: str | None = None
    first_superuser_password: str | None = None
    run_db_init: bool = False

    # Celery
    celery_broker_url: str = Field(default="redis://redis:6379/0", description="Celery broker URL")
    celery_result_backend: str = Field(default="redis://redis:6379/0", description="Celery result backend")

    # Telemetry Batch Settings
    telemetry_batch_size: int = Field(default=100, description="Batch size for telemetry inserts")
    telemetry_flush_interval: float = Field(default=5.0, description="Flush interval in seconds")

    # External APIs
    openweather_api_key: str = Field(default="", description="OpenWeather API key")

    # EPİAŞ (Turkish Energy Market)
    epias_username: str = Field(default="", description="EPİAŞ username")
    epias_password: str = Field(default="", description="EPİAŞ password")

    # Telegram Bot
    telegram_bot_token: str = Field(default="", description="Telegram bot token for notifications")
    telegram_bot_username: str = Field(default="AwaxenBot", description="Telegram bot username")
    
    # Firebase Cloud Messaging (FCM)
    firebase_credentials_path: str = Field(default="", description="Path to Firebase service account JSON")
    firebase_project_id: str = Field(default="", description="Firebase project ID")
    firebase_vapid_key: str = Field(default="", description="Firebase VAPID key for web push")

    # Sentry (Error Tracking)
    sentry_dsn: str = Field(default="", description="Sentry DSN for error tracking")
    sentry_traces_sample_rate: float = Field(default=0.1, description="Sentry traces sample rate")

    # Prometheus
    prometheus_enabled: bool = Field(default=True, description="Enable Prometheus metrics")

    # Application Version
    app_version: str = Field(default="1.0.0", description="Application version")

    # Rate Limiting
    rate_limit_requests_per_minute: int = Field(default=100, description="Rate limit per minute")
    rate_limit_ai_requests_per_minute: int = Field(default=10, description="AI endpoint rate limit")

    # PostGIS
    postgis_enabled: bool = Field(default=False, description="Enable PostGIS for geo-spatial queries")

    # PgAdmin
    pgadmin_default_email: str = Field(default="admin@awaxen.com", description="PgAdmin email")
    pgadmin_default_password: str = Field(default="admin", description="PgAdmin password")

    @property
    def cors_origins_list(self) -> list[str]:
        """Parse CORS origins from backend_cors_origins or cors_origins."""
        origins = self.backend_cors_origins or self.cors_origins
        if origins:
            return [o.strip() for o in origins.split(",") if o.strip()]
        return []

    @property
    def async_database_url(self) -> str:
        """Build async database URL from components or use direct URL."""
        if "neon.tech" in self.database_url or "postgresql+asyncpg" in self.database_url:
            # Use direct URL for Neon or already formatted URLs
            url = self.database_url
            if not url.startswith("postgresql+asyncpg"):
                url = url.replace("postgresql://", "postgresql+asyncpg://")
            return url
        # Build from components
        return f"postgresql+asyncpg://{self.db_user}:{self.db_password}@{self.db_host}:{self.db_port}/{self.db_name}"

    @property
    def sync_database_url(self) -> str:
        """Sync database URL for Alembic."""
        return self.async_database_url.replace("+asyncpg", "")


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
