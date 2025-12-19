"""
Awaxen Backend - Configuration Classes.

Flask application configuration using class-based approach.
Supports multiple environments: development, testing, production.
"""
import os
from typing import Optional


def _get_database_url() -> Optional[str]:
    """
    Get database URL from environment.
    
    Neon.tech/Render sometimes provides 'postgres://' but SQLAlchemy requires 'postgresql://'.
    This function handles the conversion automatically.
    """
    db_url = os.environ.get("DATABASE_URL")
    if db_url and db_url.startswith("postgres://"):
        db_url = db_url.replace("postgres://", "postgresql://", 1)
    return db_url


class Config:
    """Base configuration class with common settings."""
    
    # Flask
    SECRET_KEY = os.environ.get("SECRET_KEY", "dev-secret-key-change-in-production")
    
    # Database
    SQLALCHEMY_DATABASE_URI = _get_database_url()
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SQLALCHEMY_ENGINE_OPTIONS = {
        "pool_pre_ping": True,
        "pool_recycle": 300,
    }
    
    # Celery
    CELERY_BROKER_URL = os.environ.get("CELERY_BROKER_URL", "redis://localhost:6379/0")
    CELERY_RESULT_BACKEND = os.environ.get("CELERY_RESULT_BACKEND", "redis://localhost:6379/0")
    
    # MQTT
    MQTT_BROKER_URL = os.environ.get("MQTT_BROKER_URL")
    MQTT_BROKER_PORT = int(os.environ.get("MQTT_BROKER_PORT", "1883"))
    MQTT_USERNAME = os.environ.get("MQTT_USERNAME")
    MQTT_PASSWORD = os.environ.get("MQTT_PASSWORD")
    MQTT_SENSOR_TOPIC = os.environ.get("MQTT_SENSOR_TOPIC", "awaxen/sensors/#")
    MQTT_CLIENT_ID = os.environ.get("MQTT_CLIENT_ID", "awaxen-backend")
    MQTT_AUTO_START = os.environ.get("MQTT_AUTO_START", "true").lower() not in ("0", "false", "no", "off")
    
    # Telegram
    TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
    
    # Auth0
    AUTH0_DOMAIN = os.environ.get("AUTH0_DOMAIN", "dev-xxxxx.us.auth0.com")
    AUTH0_AUDIENCE = os.environ.get("AUTH0_AUDIENCE", "https://api.awaxen.com")
    
    # MinIO/S3
    MINIO_ENDPOINT = os.environ.get("MINIO_ENDPOINT", "localhost:9000")
    MINIO_ACCESS_KEY = os.environ.get("MINIO_ACCESS_KEY", "minioadmin")
    MINIO_SECRET_KEY = os.environ.get("MINIO_SECRET_KEY", "minioadmin123")
    MINIO_BUCKET = os.environ.get("MINIO_BUCKET", "awaxen-images")
    MINIO_SECURE = os.environ.get("MINIO_SECURE", "false").lower() in ("1", "true", "yes")
    
    # AI Detection
    AI_CONFIDENCE_THRESHOLD = float(os.environ.get("AI_CONFIDENCE_THRESHOLD", "0.40"))
    ENABLE_SAHI = os.environ.get("ENABLE_SAHI", "true").lower() in ("1", "true", "yes")
    
    # Encryption
    ENCRYPTION_KEY = os.environ.get("ENCRYPTION_KEY")


class DevelopmentConfig(Config):
    """Development environment configuration."""
    
    DEBUG = True
    TESTING = False
    
    # More verbose logging in development
    LOG_LEVEL = "DEBUG"
    
    # Disable MQTT auto-start in development by default
    MQTT_AUTO_START = os.environ.get("MQTT_AUTO_START", "false").lower() not in ("0", "false", "no", "off")


class TestingConfig(Config):
    """Testing environment configuration."""
    
    DEBUG = True
    TESTING = True
    
    # Use in-memory SQLite for tests
    SQLALCHEMY_DATABASE_URI = "sqlite:///:memory:"
    
    # Disable external services in tests
    MQTT_AUTO_START = False
    
    # Faster password hashing for tests
    BCRYPT_LOG_ROUNDS = 4


class ProductionConfig(Config):
    """Production environment configuration."""
    
    DEBUG = False
    TESTING = False
    
    # Stricter settings for production
    LOG_LEVEL = os.environ.get("LOG_LEVEL", "INFO")
    
    # Require DATABASE_URL in production
    @classmethod
    def validate(cls) -> None:
        """Validate required environment variables for production."""
        required_vars = [
            "DATABASE_URL",
            "SECRET_KEY",
            "AUTH0_DOMAIN",
            "AUTH0_AUDIENCE",
        ]
        missing = [var for var in required_vars if not os.environ.get(var)]
        if missing:
            raise ValueError(f"Missing required environment variables: {', '.join(missing)}")


# Configuration mapping
config_by_name = {
    "development": DevelopmentConfig,
    "testing": TestingConfig,
    "production": ProductionConfig,
    "default": DevelopmentConfig,
}


def get_config():
    """
    Get configuration class based on FLASK_ENV environment variable.
    
    Returns:
        Configuration class for the current environment.
    """
    env = os.environ.get("FLASK_ENV", "development").lower()
    return config_by_name.get(env, DevelopmentConfig)
