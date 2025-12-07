import os
from typing import List, Optional, Union

from flask import Flask
from flask_cors import CORS
from flasgger import Swagger

# Extensions'dan import et (circular import önleme)
from .extensions import db, migrate, socketio, celery, init_celery
from .version import APP_VERSION


def _env_flag(value: Optional[str], default: bool = True) -> bool:
    if value is None:
        return default
    return value.lower() not in {"0", "false", "no", "off"}


def _parse_cors_origins(value: Optional[str]) -> Union[str, List[str]]:
    """
    Kullanıcıdan gelen CORS_ORIGINS env değerini listeye dönüştür.

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


def create_app():
    app = Flask(__name__)

    cors_origins = _parse_cors_origins(os.getenv("CORS_ORIGINS", "http://localhost:3005"))
    CORS(
        app,
        resources={r"/api/*": {"origins": cors_origins}},
        supports_credentials=cors_origins != "*",
        allow_headers=[
            "Content-Type",
            "Authorization",
            "X-Auth0-Id",
            "X-Auth0-Email",
            "X-Auth0-Name",
            "X-Auth0-Role",
        ],
    )

    app.config.update(
        # Database
        SQLALCHEMY_DATABASE_URI=os.getenv("DATABASE_URL"),
        SQLALCHEMY_TRACK_MODIFICATIONS=False,
        
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
    )

    app.config["APP_VERSION"] = APP_VERSION

    db.init_app(app)
    migrate.init_app(app, db)
    socketio.init_app(app, cors_allowed_origins="*")
    Swagger(app)

    # Modelleri içeri aktar ve tabloları oluştur
    from .models import (  # noqa: F401
        # v6.0 RBAC
        Role, Permission,
        # v6.0 SaaS Core
        Organization, User, Gateway, Integration,
        # v6.0 Devices & Assets
        SmartDevice, SmartAsset, DeviceTelemetry,
        # v6.0 Automation & Economy
        MarketPrice, Automation, AutomationLog, Notification,
        # VPP
        VppRule,
    )

    with app.app_context():
        db.create_all()
        print("v6.0 Tablolar kontrol edildi ve oluşturuldu.")
        
        # Varsayılan rolleri ve yetkileri oluştur (yoksa)
        try:
            if Role.query.count() == 0:
                Role.seed_default_roles()
                print("Varsayılan roller ve yetkiler oluşturuldu.")
        except Exception as e:
            print(f"Rol seed hatası (ilk çalıştırmada normal): {e}")

    # Rotaları kaydet (Modüler Blueprint yapısı)
    from .api import api_bp
    from .api.routes_webhooks import bp as webhook_bp
    app.register_blueprint(api_bp)
    app.register_blueprint(webhook_bp, url_prefix="/webhooks")
    
    # Ana sayfa için basit route (api prefix'siz)
    @app.route('/')
    def home():
        return "Awaxen Industrial Backend Hazır!"

    # Socket event handler'larını kaydet
    from . import realtime  # noqa: F401

    # MQTT client'ı başlat
    # Werkzeug reloader aktifse sadece child process'te (WERKZEUG_RUN_MAIN=true) başlat
    # Reloader kapalıysa veya production'da direkt başlat
    if app.config.get("MQTT_AUTO_START", True):
        import os as _os
        werkzeug_main = _os.environ.get("WERKZEUG_RUN_MAIN")
        # Reloader yoksa (werkzeug_main is None) veya reloader child process'teysek başlat
        if werkzeug_main is None or werkzeug_main == "true":
            from .mqtt_client import init_mqtt_client
            init_mqtt_client(app)

    return app
