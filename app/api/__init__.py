"""
API Blueprints Package - v6.0 SaaS Architecture.

Tüm route modüllerini tek bir blueprint altında toplar.
"""
from flask import Blueprint

# Ana API Blueprint'i
api_bp = Blueprint('api', __name__, url_prefix='/api')

# ==========================================
# v6.0 SaaS Core Routes
# ==========================================
from .routes_organizations import organizations_bp
from .routes_integrations import integrations_bp
from .routes_automations import automations_bp
from .routes_dashboard import bp as dashboard_bp
from .routes_meta import meta_bp

# Blueprint'leri kaydet
api_bp.register_blueprint(organizations_bp)
api_bp.register_blueprint(integrations_bp)
api_bp.register_blueprint(automations_bp)
api_bp.register_blueprint(dashboard_bp, url_prefix="/dashboard")
api_bp.register_blueprint(meta_bp, url_prefix="/meta")

# ==========================================
# Mevcut Routes
# ==========================================
from . import routes_auth
from . import routes_gateways
from . import routes_devices
from . import routes_assets
from . import routes_telemetry
from . import routes_market
from . import routes_wallet
from . import routes_notifications
from . import routes_users
from . import routes_roles  # RBAC - Rol ve Yetki Yönetimi
from .routes_weather import weather_bp
from .routes_billing import billing_bp
from .routes_firmware import firmware_bp
from .routes_export import export_bp

# Weather Blueprint
api_bp.register_blueprint(weather_bp, url_prefix="/weather")

# Billing Blueprint
api_bp.register_blueprint(billing_bp, url_prefix="/billing")

# Firmware/OTA Blueprint
api_bp.register_blueprint(firmware_bp)

# Data Export Blueprint
api_bp.register_blueprint(export_bp)

# AI Detection Blueprint
from .routes_ai import ai_bp
api_bp.register_blueprint(ai_bp, url_prefix="/ai")
