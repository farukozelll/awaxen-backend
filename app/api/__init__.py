"""
API Blueprints Package.

Tüm route modüllerini tek bir blueprint altında toplar.
"""
from flask import Blueprint

# Ana API Blueprint'i
api_bp = Blueprint('api', __name__, url_prefix='/api')

# Alt modülleri import et (Blueprint'e route'ları ekler)
from . import routes_general
from . import routes_auth
from . import routes_sites
from . import routes_devices
from . import routes_nodes
from . import routes_assets
from . import routes_telemetry
from . import routes_commands
from . import routes_enums
from . import routes_tariffs
from . import routes_market
from . import routes_vpp
from . import routes_discovery
