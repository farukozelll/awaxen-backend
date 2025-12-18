"""
Awaxen Backend - Flask Application Factory.

Best practices:
- Environment validation
- Structured logging
- Celery integration
- Modular architecture
"""
import os
import logging
from typing import List, Optional, Union

from flask import Flask
from flask_cors import CORS
from flasgger import Swagger

from .extensions import db, migrate, socketio, celery, init_celery
from .version import APP_VERSION
from .constants import DEFAULT_TIMEZONE

# Logging configuration
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger(__name__)


def _get_required_env(key: str) -> str:
    """Zorunlu environment variable'ı al, yoksa hata fırlat."""
    value = os.getenv(key)
    if not value:
        raise ValueError(f"Missing required environment variable: {key}")
    return value


def _get_env(key: str, default: str = None) -> Optional[str]:
    """Opsiyonel environment variable'ı al."""
    return os.getenv(key, default)


def _env_flag(value: Optional[str], default: bool = True) -> bool:
    """Environment variable'ı boolean'a çevir."""
    if value is None:
        return default
    return value.lower() not in {"0", "false", "no", "off"}


def _parse_cors_origins(value: Optional[str]) -> Union[str, List[str]]:
    """
    CORS_ORIGINS env değerini listeye dönüştür.

    Örnekler:
        "*" -> "*"
        "http://localhost:3005" -> ["http://localhost:3005"]
        "http://localhost:3005,https://app.awaxen.com" -> [...]
    """
    if not value:
        return "*"

    value = value.strip()
    if value == "*":
        return "*"

    origins = [origin.strip() for origin in value.split(",") if origin.strip()]
    return origins or "*"


def _validate_environment() -> None:
    """Kritik environment variable'ları kontrol et."""
    required_vars = ["DATABASE_URL"]
    missing = [var for var in required_vars if not os.getenv(var)]
    
    if missing:
        logger.warning(f"Missing environment variables: {', '.join(missing)}")
        # Development'ta hata fırlatma, sadece uyar
        if os.getenv("FLASK_ENV") == "production":
            raise ValueError(f"Missing required environment variables: {', '.join(missing)}")


def create_app() -> Flask:
    """
    Flask application factory.
    
    Returns:
        Configured Flask application
    """
    # Environment validation
    _validate_environment()
    
    app = Flask(__name__)
    
    # CORS configuration - tüm API endpoint'leri için
    cors_origins = _parse_cors_origins(os.getenv("CORS_ORIGINS", "*"))
    CORS(
        app,
        resources={
            r"/api/*": {"origins": cors_origins},
            r"/webhooks/*": {"origins": cors_origins},
            r"/health": {"origins": "*"},
            r"/": {"origins": "*"},
        },
        supports_credentials=True,
        allow_headers=[
            "Content-Type",
            "Authorization",
            "X-Auth0-Id",
            "X-Auth0-Email",
            "X-Auth0-Name",
            "X-Auth0-Role",
            "X-Requested-With",
            "Accept",
            "Origin",
        ],
        methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
        expose_headers=["Content-Type", "Authorization"],
        max_age=86400,  # Preflight cache 24 saat
    )

    # Application configuration
    app.config.update(
        # Database
        SQLALCHEMY_DATABASE_URI=os.getenv("DATABASE_URL"),
        SQLALCHEMY_TRACK_MODIFICATIONS=False,
        SQLALCHEMY_ENGINE_OPTIONS={
            "pool_pre_ping": True,
            "pool_recycle": 300,
        },
        
        # Celery
        CELERY_BROKER_URL=os.getenv("CELERY_BROKER_URL", "redis://localhost:6379/0"),
        CELERY_RESULT_BACKEND=os.getenv("CELERY_RESULT_BACKEND", "redis://localhost:6379/0"),
        
        # Swagger
        SWAGGER={
            "title": "Awaxen IoT Platform API",
            "version": APP_VERSION,
            "uiversion": 3,
            "description": "Hibrit Enerji Yönetim Platformu - SaaS Backend",
            "securityDefinitions": {
                "bearerAuth": {
                    "type": "apiKey",
                    "name": "Authorization",
                    "in": "header",
                    "description": "Bearer <JWT> formatında token giriniz",
                }
            },
            "security": [{"bearerAuth": []}],
        },
        
        # MQTT
        MQTT_BROKER_URL=os.getenv("MQTT_BROKER_URL"),
        MQTT_BROKER_PORT=int(os.getenv("MQTT_BROKER_PORT", "1883")),
        MQTT_USERNAME=os.getenv("MQTT_USERNAME"),
        MQTT_PASSWORD=os.getenv("MQTT_PASSWORD"),
        MQTT_SENSOR_TOPIC=os.getenv("MQTT_SENSOR_TOPIC", "awaxen/sensors/#"),
        MQTT_CLIENT_ID=os.getenv("MQTT_CLIENT_ID", "awaxen-backend"),
        MQTT_AUTO_START=_env_flag(os.getenv("MQTT_AUTO_START", "true")),
        
        # Telegram Bot
        TELEGRAM_BOT_TOKEN=os.getenv("TELEGRAM_BOT_TOKEN"),
        
        # CORS
        CORS_ALLOWED_ORIGINS=cors_origins,
        
        # App
        APP_VERSION=APP_VERSION,
    )

    # Initialize extensions
    db.init_app(app)
    migrate.init_app(app, db)
    socketio.init_app(app, cors_allowed_origins="*")
    Swagger(app)
    
    # Initialize Celery with app context
    init_celery(app, celery)
    logger.info("Celery initialized with Flask app context")

    # Import models (from new modular structure)
    from .models import (  # noqa: F401
        Role, Permission,
        Organization, User, Gateway, Integration,
        SmartDevice, SmartAsset, DeviceTelemetry,
        MarketPrice, Automation, AutomationLog, Notification,
        VppRule, Wallet, WalletTransaction, AuditLog,
    )

    # Create tables and seed data
    with app.app_context():
        db.create_all()
        logger.info("Database tables checked/created")
        
        # Seed default roles and permissions
        try:
            if Role.query.count() == 0:
                Role.seed_default_roles()
                logger.info("Default roles and permissions seeded")
        except Exception as e:
            logger.warning(f"Role seed error (normal on first run): {e}")

    # Register blueprints
    from .api import api_bp
    from .api.routes_webhooks import bp as webhook_bp
    app.register_blueprint(api_bp)
    app.register_blueprint(webhook_bp, url_prefix="/webhooks")
    logger.info("API blueprints registered")
    
    # Health check endpoint
    @app.route('/')
    def home():
        return {
            "status": "healthy",
            "service": "Awaxen Backend",
            "version": APP_VERSION
        }
    
    @app.route('/health')
    def health_check():
        """Health check endpoint for Docker/K8s."""
        return {
            "status": "healthy",
            "version": APP_VERSION,
            "database": "connected" if db.engine else "disconnected"
        }

    # Register Socket.IO event handlers
    from . import realtime  # noqa: F401

    # Initialize MQTT client
    if app.config.get("MQTT_AUTO_START", True):
        werkzeug_main = os.environ.get("WERKZEUG_RUN_MAIN")
        if werkzeug_main is None or werkzeug_main == "true":
            from .mqtt_client import init_mqtt_client
            init_mqtt_client(app)
            logger.info("MQTT client initialized")

    logger.info(f"Awaxen Backend v{APP_VERSION} started successfully")
    return app
