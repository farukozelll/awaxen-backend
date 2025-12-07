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
from . import routes_roles  # RBAC - Rol ve Yetki Yönetimi
