"""
Awaxen Backend - Main Application Entry Point
Application Factory Pattern with ORJSONResponse for maximum performance.
"""
from contextlib import asynccontextmanager
from typing import AsyncGenerator

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
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


def create_application() -> FastAPI:
    """
    Application factory function.
    Creates and configures the FastAPI application.
    
    TRICK: Use ORJSONResponse as default for 10x faster JSON serialization.
    """
    app = FastAPI(
        title=settings.project_name,
        description="""
# 🌞 Awaxen Hibrit Enerji Yönetim Platformu

**Enterprise-grade IoT & Energy Management SaaS Backend**

## 🔢 API Versiyonlama

**Tüm endpoint'ler `/api/v1/` prefix'i ile başlar.**

```
✅ Doğru:   https://api.awaxen.com/api/v1/auth/me
❌ Yanlış:  https://api.awaxen.com/api/auth/me
❌ Yanlış:  https://api.awaxen.com/auth/me
```

> ⚠️ Versiyonsuz istekler `404 Not Found` döner.

## 🔑 Authentication (Kimlik Doğrulama)

Tüm API endpoint'leri JWT Bearer token gerektirir. Token'lar Auth0'dan alınır.

```
Authorization: Bearer <your_jwt_token>
```

## 📊 API Grupları

| Grup | Prefix | Açıklama |
|------|--------|----------|
| **Auth** | `/api/v1/auth` | Kimlik doğrulama ve kullanıcı yönetimi |
| **Dashboard** | `/api/v1/dashboard` | Özet ve analitik verileri |
| **Notifications** | `/api/v1/notifications` | Bildirim yönetimi (Push, Telegram) |
| **IoT** | `/api/v1/iot` | IoT cihaz CRUD işlemleri |
| **Billing** | `/api/v1/billing` | Cüzdan ve işlem geçmişi |
| **Integrations** | `/api/v1/integrations` | EPİAŞ, hava durumu |
| **Real Estate** | `/api/v1/real-estate` | Gayrimenkul yönetimi |

## 🚀 Rate Limiting
- Standard: 100 req/min
- AI Endpoints: 10 req/min

## 📝 Pagination
Tüm liste endpoint'leri pagination destekler:
- `page`: Sayfa numarası (default: 1)
- `pageSize`: Sayfa başına kayıt (default: 20, max: 100)

## 🔗 Frontend Entegrasyonu
```typescript
const API_BASE = "https://api.awaxen.com/api/v1";

// Auth0 ile giriş yap
const token = await auth0.getAccessTokenSilently();

// Kullanıcıyı senkronize et
await fetch(`${API_BASE}/auth/sync`, {
  method: "POST",
  headers: { "Authorization": `Bearer ${token}` },
  body: JSON.stringify({ auth0_id, email, name, role })
});

// Profil bilgilerini al
const profile = await fetch(`${API_BASE}/auth/me`, {
  headers: { "Authorization": `Bearer ${token}` }
});
```
        """,
        version="1.0.0",
        debug=settings.debug,
        lifespan=lifespan,
        default_response_class=ORJSONResponse,
        docs_url="/docs",
        redoc_url="/redoc",
        openapi_url="/openapi.json",
        openapi_tags=TAGS_METADATA,
        contact={
            "name": "Awaxen Team",
            "email": "team@awaxen.com",
            "url": "https://awaxen.com",
        },
        license_info={
            "name": "MIT",
            "url": "https://opensource.org/licenses/MIT",
        },
    )
    
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
