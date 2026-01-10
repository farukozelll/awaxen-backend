"""
Awaxen Backend - Main Application Entry Point
Application Factory Pattern with ORJSONResponse for maximum performance.
"""
from contextlib import asynccontextmanager
from typing import AsyncGenerator

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.openapi.utils import get_openapi
from fastapi.responses import ORJSONResponse

from src.core.config import settings
from src.core.database import close_db, init_db
from src.core.exceptions import (
    AwaxenException,
    awaxen_exception_handler,
    generic_exception_handler,
    http_exception_handler,
)
from src.core.logging import configure_logging, get_logger

# Configure logging on module load
configure_logging()
logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """
    Application lifespan manager.
    Handles startup and shutdown events.
    """
    # Startup
    logger.info(
        "Starting Awaxen Backend",
        environment=settings.environment,
        debug=settings.debug,
    )
    
    # Initialize database (create tables if needed)
    if settings.run_db_init:
        await init_db()
        logger.info("Database initialized")
    
    yield
    
    # Shutdown
    logger.info("Shutting down Awaxen Backend")
    await close_db()


# OpenAPI Tags Metadata - Best Practice Gruplandırma
TAGS_METADATA = [
    # 🔐 AUTHENTICATION & USERS
    {"name": "Auth", "description": "🔐 **Kimlik Doğrulama** - Auth0 sync, roller ve yetkiler"},
    {"name": "Users", "description": "👤 **Kullanıcı Profili** - Profil yönetimi ve onboarding"},
    {"name": "Admin", "description": "👑 **Admin İşlemleri** - Organizasyon ve kullanıcı yönetimi"},
    # 🏠 REAL ESTATE & ASSETS
    {"name": "real-estate", "description": "🏠 **Gayrimenkul** - Asset, Zone ve Tenancy yönetimi"},
    # 📡 IOT & DEVICES
    {"name": "IoT", "description": "📡 **IoT Cihazlar** - Gateway pairing, cihaz keşfi ve kontrol"},
    # ⚡ ENERGY & CORE LOOP
    {"name": "Energy", "description": "⚡ **Enerji Yönetimi** - Recommendation, Command ve Core Loop"},
    {"name": "Market", "description": "📈 **Piyasa Verileri** - EPİAŞ elektrik fiyatları"},
    # 🏆 REWARDS & WALLET
    {"name": "Rewards", "description": "🏆 **AWX Puanlar** - Bakiye, ledger ve streak bilgileri"},
    {"name": "Wallet", "description": "💰 **Cüzdan** - AWX puan dağıtımı (internal)"},
    # 🔧 MAINTENANCE & BILLING
    {"name": "Maintenance", "description": "🔧 **Bakım** - Arıza bildirimi ve operatör marketplace"},
    {"name": "Billing", "description": "💳 **Faturalama** - Cüzdan ve işlem geçmişi"},
    # 📋 COMPLIANCE & NOTIFICATIONS
    {"name": "Compliance", "description": "📋 **KVKK/GDPR** - Onaylar ve denetim kayıtları"},
    {"name": "Notifications", "description": "🔔 **Bildirimler** - Push, Telegram, Email"},
    # 📊 ANALYTICS & SYSTEM
    {"name": "Dashboard", "description": "📊 **Dashboard** - Özet veriler ve analitikler"},
    {"name": "Integrations", "description": "🔗 **Entegrasyonlar** - EPİAŞ, OpenWeather, Telegram"},
    {"name": "SSE", "description": "📡 **Realtime** - Server-Sent Events"},
    {"name": "health", "description": "❤️ **Sağlık** - Sistem durumu ve metrikler"},
]

# API Description for Swagger
API_DESCRIPTION = """
# 🌞 Awaxen - Hibrit Enerji Yönetim Platformu

**Enterprise-grade PropTech + EnergyTech/IoT SaaS Backend**

---

## 🚀 Hızlı Başlangıç

### 1. Auth0 Token Al
```bash
curl -X POST "https://YOUR_AUTH0_DOMAIN/oauth/token" \\
  -H "Content-Type: application/json" \\
  -d '{"client_id": "...", "audience": "...", "grant_type": "client_credentials"}'
```

### 2. API'yi Kullan
```bash
curl -X GET "https://api.awaxen.com/api/v1/users/me" \\
  -H "Authorization: Bearer YOUR_TOKEN"
```

---

## 📋 API Akışları

### User Onboarding
1. `POST /auth/sync` → Auth0 kullanıcısını DB'ye senkronize et
2. `GET /users/me` → Profil ve onboarding durumu
3. `PATCH /users/me/onboarding` → Bilgileri tamamla

### Gateway Pairing
1. Gateway: `POST /iot/gateways/pairing-session` → Kod al
2. User: `POST /iot/devices/claim` → Kodu gir, gateway bağla
3. Gateway: `POST /iot/gateways/{id}/discovery` → Cihazları keşfet
4. User: `POST /iot/devices/{id}/configuration` → Zone ve safety profile ata

### Energy Core Loop (💸 The Money Maker)
1. `GET /market/epias/prices/current` → Fiyat kontrolü
2. `POST /energy/recommendations/calculate` → Recommendation oluştur
3. `POST /energy/recommendations/{id}/approve` → Onayla, command gönder
4. Gateway: `POST /energy/commands/{id}/execution-proof` → Kanıt gönder
5. Backend: AWX puan ver

---

## 🔐 Yetkilendirme

Tüm endpoint'ler JWT token gerektirir. Swagger'da sağ üstteki **Authorize** butonunu kullanın.

| Rol | Açıklama |
|-----|----------|
| `admin` | Sistem yöneticisi - tüm yetkiler |
| `tenant` | Organizasyon yöneticisi |
| `user` | Normal kullanıcı |
| `device` | IoT cihaz (telemetri) |
"""


def create_application() -> FastAPI:
    """
    Application factory function.
    Creates and configures the FastAPI application.
    
    TRICK: Use ORJSONResponse as default for 10x faster JSON serialization.
    """
    app = FastAPI(
        # === METADATA (Kimlik Kartı) ===
        title="Awaxen API",
        summary="Hibrit Enerji Yönetim Platformu - PropTech + EnergyTech/IoT SaaS",
        description=API_DESCRIPTION,
        version=settings.app_version,
        
        # === OPENAPI CONFIG ===
        openapi_url="/openapi.json",
        openapi_tags=TAGS_METADATA,
        
        # === DOCS CONFIG ===
        docs_url="/docs",
        redoc_url="/redoc",
        swagger_ui_parameters={
            "defaultModelsExpandDepth": -1,  # Şemaları varsayılan kapalı tut
            "docExpansion": "list",  # Endpoint'leri liste olarak göster
            "filter": True,  # Arama filtresi aktif
            "showExtensions": True,
            "showCommonExtensions": True,
            "syntaxHighlight.theme": "monokai",
            "tryItOutEnabled": True,  # "Try it out" varsayılan açık
            "persistAuthorization": True,  # Token'u hatırla
        },
        
        # === CONTACT & LICENSE ===
        contact={
            "name": "Awaxen Team",
            "url": "https://awaxen.com",
            "email": "api@awaxen.com",
        },
        license_info={
            "name": "Proprietary",
            "url": "https://awaxen.com/terms",
        },
        terms_of_service="https://awaxen.com/terms",
        
        # === PERFORMANCE ===
        default_response_class=ORJSONResponse,
        debug=settings.debug,
        lifespan=lifespan,
    )
    
    # === CUSTOM OPENAPI SCHEMA ===
    def custom_openapi():
        if app.openapi_schema:
            return app.openapi_schema
        
        openapi_schema = get_openapi(
            title=app.title,
            version=app.version,
            summary=app.summary,
            description=app.description,
            routes=app.routes,
            tags=TAGS_METADATA,
        )
        
        # === SECURITY SCHEME (Swagger Authorize Butonu) ===
        openapi_schema["components"]["securitySchemes"] = {
            "BearerAuth": {
                "type": "http",
                "scheme": "bearer",
                "bearerFormat": "JWT",
                "description": """
**Auth0 JWT Token**

Token almak için:
1. Auth0 Dashboard'dan token al
2. Veya frontend üzerinden `getAccessTokenSilently()` kullan

```
Authorization: Bearer eyJhbGciOiJSUzI1NiIs...
```
                """,
            },
            "OAuth2": {
                "type": "oauth2",
                "flows": {
                    "authorizationCode": {
                        "authorizationUrl": f"https://{settings.auth0_domain}/authorize",
                        "tokenUrl": f"https://{settings.auth0_domain}/oauth/token",
                        "scopes": {
                            "openid": "OpenID Connect",
                            "profile": "Kullanıcı profili",
                            "email": "E-posta adresi",
                        },
                    }
                },
            },
        }
        
        # Global security (tüm endpoint'ler için)
        openapi_schema["security"] = [{"BearerAuth": []}]
        
        # Server bilgisi - Development modunda localhost önce gelsin
        if settings.debug:
            openapi_schema["servers"] = [
                {
                    "url": "/",
                    "description": "💻 Current Server (Relative)",
                },
                {
                    "url": "http://localhost:8000",
                    "description": "💻 Local Development",
                },
            ]
        else:
            openapi_schema["servers"] = [
                {
                    "url": "https://api.awaxen.com",
                    "description": "🌐 Production Server",
                },
                {
                    "url": "https://staging-api.awaxen.com",
                    "description": "🧪 Staging Server",
                },
            ]
        
        # External docs
        openapi_schema["externalDocs"] = {
            "description": "📚 Tam Dokümantasyon",
            "url": "https://docs.awaxen.com",
        }
        
        app.openapi_schema = openapi_schema
        return app.openapi_schema
    
    app.openapi = custom_openapi
    
    # Initialize Sentry
    try:
        from src.core.sentry import init_sentry
        init_sentry()
    except ImportError:
        logger.warning("Sentry SDK not installed, skipping initialization")
    
    # Add Prometheus metrics middleware
    if settings.prometheus_enabled:
        try:
            from src.core.metrics import MetricsMiddleware
            app.add_middleware(MetricsMiddleware)
        except ImportError:
            logger.warning("prometheus_client not installed, skipping metrics")
    
    # Register exception handlers
    app.add_exception_handler(AwaxenException, awaxen_exception_handler)
    app.add_exception_handler(HTTPException, http_exception_handler)
    app.add_exception_handler(Exception, generic_exception_handler)
    
    # CORS middleware - Allow all origins in development, specific origins in production
    cors_origins = settings.cors_origins_list
    
    # Always include common development origins
    default_origins = [
        "http://localhost:3000",
        "http://localhost:3005",
        "http://localhost:8000",
        "http://localhost:8080",
        "https://localhost:3000",
        "https://localhost:3005",
        "https://localhost:8000",
        "http://127.0.0.1:3000",
        "http://127.0.0.1:3005",
        "http://127.0.0.1:8000",
        "https://127.0.0.1:8000",
        "https://awaxen.com",
        "https://www.awaxen.com",
        "https://app.awaxen.com",
        "https://api.awaxen.com",
    ]
    
    # Merge configured origins with defaults
    all_origins = list(set(cors_origins + default_origins))
    
    app.add_middleware(
        CORSMiddleware,
        allow_origins=all_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
        expose_headers=["*"],
    )
    
    logger.info("CORS configured", origins=all_origins)
    
    # Include routers from modules
    _include_routers(app)
    
    # Health check endpoint
    @app.get("/health", tags=["health"], response_class=ORJSONResponse)
    async def health_check() -> dict[str, str]:
        """Health check endpoint."""
        return {"status": "healthy", "service": "awaxen-backend"}
    
    @app.get("/", tags=["root"], response_class=ORJSONResponse)
    async def root() -> dict[str, str]:
        """Root endpoint."""
        return {
            "service": "Awaxen Backend",
            "version": "0.1.0",
            "docs": "/docs" if settings.debug else "disabled",
        }
    
    return app


def _include_routers(app: FastAPI) -> None:
    """
    Include all module routers.
    Each module has its own router with its own prefix.
    
    API Versioning: Only /api/v1/... is supported.
    Unversioned requests to /api/... will receive 404.
    """
    from src.modules.auth.router import router as auth_router
    from src.modules.auth.router import users_router
    from src.modules.auth.router import admin_router
    from src.modules.billing.router import router as billing_router
    from src.modules.iot.router import router as iot_router
    from src.modules.real_estate.router import router as real_estate_router
    from src.modules.integrations.router import router as integrations_router
    from src.modules.dashboard.router import router as dashboard_router
    from src.modules.notifications.router import router as notifications_router
    from src.modules.compliance.router import router as compliance_router
    from src.modules.compliance.router import audit_router
    from src.modules.energy.router import router as energy_router
    from src.modules.energy.router import rewards_router
    from src.modules.energy.router import epias_router
    from src.modules.energy.router import wallet_router
    from src.modules.marketplace.router import router as marketplace_router
    from src.modules.sse.router import router as sse_router
    from src.core.metrics import router as metrics_router
    
    api_v1_prefix = settings.api_v1_str  # /api/v1
    
    # Register routers ONLY with versioned prefix
    # NOT: Router'lar kendi içinde prefix tanımlı (örn: /auth, /users)
    # Bu yüzden sadece api_v1_prefix ekliyoruz, name kullanılmıyor
    routers = [
        auth_router,      # /api/v1/auth/*
        users_router,     # /api/v1/users/*
        admin_router,     # /api/v1/admin/*
        dashboard_router,
        notifications_router,
        real_estate_router,
        iot_router,
        billing_router,
        integrations_router,
        compliance_router,
        audit_router,     # /api/v1/audit/* - EKLENDİ!
        energy_router,
        rewards_router,
        wallet_router,
        epias_router,
        marketplace_router,
        sse_router,
    ]
    
    for router in routers:
        app.include_router(router, prefix=api_v1_prefix)
    
    # Metrics router at root level (no prefix)
    if settings.prometheus_enabled:
        app.include_router(metrics_router)
    
    logger.info(
        "Routers registered",
        modules=[
            "auth", "dashboard", "notifications", "real_estate", "iot", 
            "billing", "integrations", "compliance", "energy", "rewards", 
            "maintenance", "sse", "metrics"
        ],
        api_version="v1",
        api_prefix=api_v1_prefix,
    )


# Create application instance
app = create_application()


if __name__ == "__main__":
    import uvicorn
    
    uvicorn.run(
        "src.main:app",
        host="0.0.0.0",
        port=8000,
        reload=settings.debug,
        log_level="debug" if settings.debug else "info",
    )
