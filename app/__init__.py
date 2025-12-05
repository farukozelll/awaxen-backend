import os
from typing import Optional

from flask import Flask
from flask_cors import CORS
from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate
from flasgger import Swagger
from flask_socketio import SocketIO

db = SQLAlchemy()
migrate = Migrate()
socketio = SocketIO(cors_allowed_origins="*")


def _env_flag(value: Optional[str], default: bool = True) -> bool:
    if value is None:
        return default
    return value.lower() not in {"0", "false", "no", "off"}


def create_app():
    app = Flask(__name__)
    CORS(
        app,
        resources={r"/*": {"origins": "*"}},
        supports_credentials=True,
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
        SQLALCHEMY_DATABASE_URI=os.getenv("DATABASE_URL"),
        SQLALCHEMY_TRACK_MODIFICATIONS=False,
        SWAGGER={
            "title": "Awaxen Industrial API",
            "uiversion": 3,
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
        MQTT_BROKER_URL=os.getenv("MQTT_BROKER_URL"),
        MQTT_BROKER_PORT=int(os.getenv("MQTT_BROKER_PORT", "1883")),
        MQTT_USERNAME=os.getenv("MQTT_USERNAME"),
        MQTT_PASSWORD=os.getenv("MQTT_PASSWORD"),
        MQTT_SENSOR_TOPIC=os.getenv("MQTT_SENSOR_TOPIC", "awaxen/sensors/#"),
        MQTT_CLIENT_ID=os.getenv("MQTT_CLIENT_ID", "awaxen-backend"),
        MQTT_AUTO_START=_env_flag(os.getenv("MQTT_AUTO_START", "true")),
    )

    db.init_app(app)
    migrate.init_app(app, db)
    socketio.init_app(app, cors_allowed_origins="*")
    Swagger(app)

    # Modelleri içeri aktar ve tabloları oluştur
    from .models import User, Site, Device, Node, Telemetry, Command, SensorData  # noqa: F401

    with app.app_context():
        db.create_all()
        print("Tablolar kontrol edildi ve oluşturuldu.")
        _seed_initial_data()

    # Rotaları kaydet (Modüler Blueprint yapısı)
    from .api import api_bp
    app.register_blueprint(api_bp)
    
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


def _seed_initial_data() -> None:
    """Development convenience: populate sample user/site/device data once."""

    from .models import User, Site, Device, Node, Telemetry

    existing_user = User.query.filter_by(auth0_id="google-oauth2|114543030408234531565").first()
    if existing_user:
        return

    user = User(
        auth0_id="google-oauth2|114543030408234531565",
        email="awaxenofficial@gmail.com",
        full_name="Awaxen Official",
        role="admin",
    )
    db.session.add(user)
    db.session.flush()

    site = Site(name="Kayseri VPP Sahası", city="Kayseri", location="38.72, 35.48", owner=user)
    db.session.add(site)
    db.session.flush()

    device = Device(
        site=site,
        serial_number="AWX-CORE-0001",
        name="Core Lite Pano",
        is_online=True,
    )
    db.session.add(device)
    db.session.flush()

    node_inverter = Node(
        device=device,
        name="Solar Inverter",
        node_type="INVERTER",
        configuration={"protocol": "modbus", "address": 1},
    )
    node_pump = Node(
        device=device,
        name="Serpme Pompa",
        node_type="ACTUATOR",
        configuration={"type": "gpio", "pin": 17},
    )
    db.session.add_all([node_inverter, node_pump])
    db.session.flush()

    sample_telemetry = [
        Telemetry(node_id=node_inverter.id, key="active_power", value=3250.0),
        Telemetry(node_id=node_inverter.id, key="dc_voltage", value=820.5),
        Telemetry(node_id=node_pump.id, key="flow_rate", value=12.4),
    ]
    db.session.add_all(sample_telemetry)
    db.session.commit()
