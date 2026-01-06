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


# OpenAPI Tags Metadata
TAGS_METADATA = [
    {
        "name": "Auth",
        "description": """
**🔐 Kimlik Doğrulama ve Kullanıcı Yönetimi**

Auth0 entegrasyonu ile JWT tabanlı kimlik doğrulama.

## Akış
1. Frontend, Auth0'dan token alır
2. `/api/v1/auth/sync` ile kullanıcıyı Postgres'e senkronize eder
3. `/api/v1/auth/me` ile kullanıcı bilgilerini alır

## Roller
| Rol | Açıklama |
|-----|----------|
| `admin` | Platform yöneticisi |
| `owner` | Mülk sahibi |
| `tenant` | Kiracı |
| `agent` | Emlak danışmanı |
| `operator` | Bakım operatörü |
        """,
    },
    {
        "name": "Organizations",
        "description": """
**🏢 Organizasyon (Tenant) Yönetimi**

Multi-tenant yapı için organizasyon işlemleri.
Her kullanıcı bir veya daha fazla organizasyona ait olabilir.

## Özellikler
- Organizasyon oluşturma/güncelleme
- Üye yönetimi
- Rol atama
        """,
    },
    {
        "name": "real-estate",
        "description": """
**🏠 Gayrimenkul Yönetimi**

Mülk yaşam döngüsü yönetimi.

## Hiyerarşi
```
Organization
└── Asset (Villa, Apartment, Factory...)
    ├── Zone (Salon, Mutfak, Yatak Odası...)
    ├── Gateway (CM5 cihazı)
    │   └── Device (Sensör, Röle, Sayaç...)
    └── Tenancy (Kiracı geçmişi)
```

## Özellikler
- **Asset**: Mülk CRUD işlemleri
- **Zone**: Oda/alan tanımları
- **Tenancy**: Kiracı yaşam döngüsü
- **Handover**: Dijital devir teslim (QR kod ile)
        """,
    },
    {
        "name": "iot",
        "description": """
**📡 IoT Cihaz Yönetimi**

Gateway ve cihaz yönetimi, telemetri verileri.

## Cihaz Tipleri
| Tip | Açıklama |
|-----|----------|
| `smart_plug` | Akıllı priz |
| `energy_meter` | Enerji sayacı |
| `temperature_sensor` | Sıcaklık sensörü |
| `relay` | Röle |
| `thermostat` | Termostat |

## Gateway Pairing
1. Gateway açılır, ekranda kod görünür
2. Kullanıcı kodu uygulamaya girer
3. Gateway organizasyona bağlanır

## Güvenlik Profilleri
- `critical`: Asla otomatik kontrol edilmez
- `high`: Sadece onay ile kontrol
- `normal`: Otomatik kontrol edilebilir
        """,
    },
    {
        "name": "Energy",
        "description": """
**⚡ Enerji Yönetimi - Core Loop**

EPİAŞ fiyat bazlı enerji tasarruf sistemi.

## Core Loop
```
EPİAŞ Fiyat Yüksek
    ↓
Recommendation Oluştur
    ↓
Kullanıcıya Bildir (Push/Telegram)
    ↓
Kullanıcı Onaylar
    ↓
Command Gateway'e Gönder
    ↓
Gateway Cihazı Kontrol Eder
    ↓
Proof Topla (state_changed, power_drop)
    ↓
AWX Puan Ver
```

## Recommendation Status
| Status | Açıklama |
|--------|----------|
| `created` | Yeni oluşturuldu |
| `notified` | Kullanıcıya bildirildi |
| `approved` | Onaylandı |
| `deferred` | Ertelendi |
| `rejected` | Reddedildi |
        """,
    },
    {
        "name": "Rewards",
        "description": """
**🏆 AWX Puan Sistemi**

Enerji tasarrufu için ödül sistemi.

## Puan Kazanma
| Eylem | AWX |
|-------|-----|
| Tasarruf aksiyonu | 10-50 |
| Günlük giriş | 5 |
| Streak bonusu | 20 |
| Bakım işi tamamlama | 30 |

## Streak Sistemi
Ardışık günlerde tasarruf yapan kullanıcılar bonus kazanır.
        """,
    },
    {
        "name": "Maintenance",
        "description": """
**🔧 Bakım & Marketplace**

Arıza bildirimi ve operatör yönetimi.

## Akış
```
Alarm Oluşur (cihaz arızası, anomali)
    ↓
Job Oluştur
    ↓
Operatörler Teklif Verir
    ↓
Ev Sahibi Teklif Seçer
    ↓
Operatör İşi Tamamlar
    ↓
Proof Yükler (QR, fotoğraf)
    ↓
Ödeme & Değerlendirme
```

## Alarm Seviyeleri
| Seviye | Açıklama |
|--------|----------|
| `low` | Bilgilendirme |
| `medium` | Dikkat gerekli |
| `high` | Acil müdahale |
| `critical` | Kritik arıza |
        """,
    },
    {
        "name": "Compliance",
        "description": """
**📋 KVKK/GDPR Uyumluluk**

Kullanıcı onayları ve denetim kayıtları.

## Consent Tipleri
| Tip | Açıklama |
|-----|----------|
| `location` | Konum verisi |
| `device_control` | Cihaz kontrolü |
| `notifications` | Bildirimler |
| `telegram` | Telegram entegrasyonu |
| `data_processing` | Veri işleme |

## Audit Log
Tüm kritik işlemler kayıt altına alınır:
- Cihaz kontrolü
- Handover işlemleri
- Yetki değişiklikleri
        """,
    },
    {
        "name": "Admin",
        "description": """
**👑 Admin İşlemleri**

Platform yönetimi için admin endpoint'leri.
Sadece `admin` rolüne sahip kullanıcılar erişebilir.
        """,
    },
    {
        "name": "Billing",
        "description": """
**💳 Faturalama ve Cüzdan**

AWX cüzdan yönetimi ve işlem geçmişi.

## İşlem Tipleri
| Tip | Açıklama |
|-----|----------|
| `credit` | Para yükleme |
| `debit` | Harcama |
| `reward` | Ödül kazanımı |
| `refund` | İade |
        """,
    },
    {
        "name": "Integrations",
        "description": """
**🔗 Dış Entegrasyonlar**

## EPİAŞ
Türkiye elektrik piyasası fiyatları.
- Saatlik fiyatlar
- Maliyet hesaplama

## OpenWeather
Hava durumu verileri.
- Anlık sıcaklık
- 5 günlük tahmin

## Telegram
Bot bildirimleri.
- Tasarruf önerileri
- Alarm bildirimleri
        """,
    },
    {
        "name": "Dashboard",
        "description": """
**📊 Dashboard & Analytics**

Özet veriler ve analitikler.

## Metrikler
- Toplam tasarruf (TRY, kWh)
- Aktif cihaz sayısı
- Gateway durumları
- Son alarmlar
        """,
    },
    {
        "name": "Notifications",
        "description": """
**🔔 Bildirim Yönetimi**

Multi-channel bildirim sistemi.

## Kanallar
| Kanal | Açıklama |
|-------|----------|
| `in_app` | Uygulama içi |
| `push` | Firebase Push |
| `telegram` | Telegram bot |
| `email` | E-posta |

## Öncelikler
- `low`: Bilgilendirme
- `normal`: Standart
- `high`: Önemli
- `urgent`: Acil
        """,
    },
    {
        "name": "SSE",
        "description": """
**📡 Server-Sent Events (Realtime)**

Gerçek zamanlı güncellemeler için SSE endpoint'leri.

## Kullanım
```javascript
const eventSource = new EventSource('/api/v1/sse/dashboard');
eventSource.onmessage = (event) => {
    const data = JSON.parse(event.data);
    console.log('Update:', data);
};
```

## Event Tipleri
- `device_state`: Cihaz durumu değişti
- `recommendation`: Yeni tasarruf önerisi
- `alarm`: Yeni alarm
- `command_result`: Komut sonucu
        """,
    },
    {
        "name": "Health",
        "description": """
**❤️ Sağlık Kontrolü**

Sistem durumu ve metrikler.

## Endpoint'ler
- `GET /health` - Basit sağlık kontrolü
- `GET /health/ready` - Hazırlık durumu
- `GET /metrics` - Prometheus metrikleri
        """,
    },
]


# =============================================================================
# OPENAPI DESCRIPTION - Swagger Üst Kısım Açıklaması
# =============================================================================
API_DESCRIPTION = """
# 🌞 Awaxen - Hibrit Enerji Yönetim Platformu

**Enterprise-grade PropTech + EnergyTech/IoT SaaS Backend**

---

## 🏗️ Sistem Mimarisi

```
┌─────────────────┐     ┌─────────────────┐     ┌─────────────────┐
│       │     │    Web App PWA  │     │   Admin Panel   │
│  │     │    React.js   │     │    Next.js    │
└────────┬────────┘     └────────┬────────┘  
        │                        │                    
        └────────────┬───────────┴────────────┘
                     │
        ┌────────────┴────────────┐
        │      🔐 Auth0 (JWT)       │
        └────────────┬────────────┘
                     │
        ┌────────────┴────────────┐
        │   🚀 Awaxen Backend      │
        │      (FastAPI)         │
        └───┬───────┬───────┬────┘
            │       │       │
    ┌───────┴─┐ ┌───┴───┐ ┌─┴───────┐
    │PostgreSQL│ │ Redis │ │  MQTT     │
    │TimescaleDB│ │(Cache)│ │(Mosquitto)│
    └──────────┘ └───────┘ └────┬─────┘
                              │
                    ┌─────────┴─────────┐
                    │  📡 IoT Gateway    │
                    │  (Raspberry Pi CM5)│
                    └─────────┬─────────┘
                              │
              ┌─────────┬─────┴────┬─────────┐
              │         │           │         │
          ┌───┴───┐ ┌───┴───┐ ┌───┴───┐ ┌───┴───┐
          │ Shelly │ │ Meter │ │Thermos.│ │ Sensor │
          └────────┘ └───────┘ └────────┘ └────────┘
```

---

## 🔢 API Versiyonlama

| Versiyon | Prefix | Durum |
|----------|--------|-------|
| **v1** | `/api/v1/` | ✅ Aktif |
| v2 | `/api/v2/` | 🚧 Planlanıyor |

> ⚠️ **Önemli:** Tüm endpoint'ler `/api/v1/` prefix'i ile başlar. Versiyonsuz istekler `404 Not Found` döner.

```bash
# ✅ Doğru
curl https://api.awaxen.com/api/v1/auth/me

# ❌ Yanlış
curl https://api.awaxen.com/auth/me
```

---

## � Kimlik Doğrulama (Authentication)

Tüm API endpoint'leri **JWT Bearer token** gerektirir. Token'lar [Auth0](https://auth0.com) üzerinden alınır.

### Token Alma
```typescript
// Frontend (React/Next.js)
import { useAuth0 } from '@auth0/auth0-react';

const { getAccessTokenSilently } = useAuth0();
const token = await getAccessTokenSilently();
```

### API İsteği
```bash
curl -X GET "https://api.awaxen.com/api/v1/auth/me" \
  -H "Authorization: Bearer eyJhbGciOiJSUzI1NiIsInR5cCI6IkpXVCJ9..."
```

### Hata Kodları
| Kod | Açıklama |
|-----|----------|
| `401` | Token eksik veya geçersiz |
| `403` | Yetki yetersiz |
| `422` | Validasyon hatası |

---

## 📊 API Grupları

| Grup | Prefix | Açıklama |
|------|--------|----------|
| **Auth** | `/api/v1/auth` | Kullanıcı kimlik doğrulama |
| **Real Estate** | `/api/v1/real-estate` | Mülk yönetimi (Asset, Zone, Tenancy) |
| **IoT** | `/api/v1/iot` | Gateway ve cihaz yönetimi |
| **Energy** | `/api/v1/energy` | Enerji tasarruf önerileri |
| **Rewards** | `/api/v1/rewards` | AWX puan sistemi |
| **Maintenance** | `/api/v1/maintenance` | Bakım işleri ve marketplace |
| **Compliance** | `/api/v1/compliance` | KVKK/GDPR uyumluluk |
| **Billing** | `/api/v1/billing` | Cüzdan ve işlemler |
| **Dashboard** | `/api/v1/dashboard` | Analitik ve özet |
| **Notifications** | `/api/v1/notifications` | Bildirim yönetimi |
| **Integrations** | `/api/v1/integrations` | Dış servisler (EPİAŞ, Hava) |
| **SSE** | `/api/v1/sse` | Realtime event stream |

---

## 🚀 Rate Limiting

| Endpoint Tipi | Limit | Pencere |
|---------------|-------|--------|
| Standard | 100 | /dakika |
| AI/ML | 10 | /dakika |
| SSE | 5 | /bağlantı |

Aşıldığında `429 Too Many Requests` döner.

---

## 📝 Pagination

Tüm liste endpoint'leri pagination destekler:

```bash
GET /api/v1/real-estate/assets?page=1&page_size=20
```

| Parametre | Tip | Default | Max | Açıklama |
|-----------|-----|---------|-----|----------|
| `page` | int | 1 | - | Sayfa numarası |
| `page_size` | int | 20 | 100 | Sayfa başına kayıt |

### Response Format
```json
{
  "items": [...],
  "total": 150,
  "page": 1,
  "page_size": 20,
  "pages": 8
}
```

---

## ⚠️ Hata Formatı (Error Response)

Tüm hatalar RFC 7807 uyumlu JSON formatında döner:

```json
{
  "error": {
    "code": "NOT_FOUND",
    "message": "Asset with identifier 'abc123' not found",
    "details": {
      "resource": "Asset",
      "identifier": "abc123"
    },
    "request_id": "req_abc123xyz",
    "timestamp": "2024-01-15T10:30:00Z",
    "path": "/api/v1/real-estate/assets/abc123",
    "method": "GET"
  }
}
```

---

## 🔗 Yararlı Linkler

- 📖 [API Dokümantasyonu](https://api.awaxen.com/docs)
- 📚 [ReDoc](https://api.awaxen.com/redoc)
- 💻 [GitHub](https://github.com/farukozelll/awaxen-backend)
- 🌐 [Website](https://awaxen.com)
- 📧 [Destek](mailto:support@awaxen.com)
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
    from src.modules.marketplace.router import router as marketplace_router
    from src.modules.sse.router import router as sse_router
    from src.core.metrics import router as metrics_router
    
    api_v1_prefix = settings.api_v1_str  # /api/v1
    
    # Register routers ONLY with versioned prefix
    routers = [
        (auth_router, "auth"),
        (dashboard_router, "dashboard"),
        (notifications_router, "notifications"),
        (real_estate_router, "real-estate"),
        (iot_router, "iot"),
        (billing_router, "billing"),
        (integrations_router, "integrations"),
        (compliance_router, "compliance"),
        (audit_router, "admin"),
        (energy_router, "energy"),
        (rewards_router, "rewards"),
        (marketplace_router, "maintenance"),
        (sse_router, "sse"),
    ]
    
    for router, name in routers:
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
