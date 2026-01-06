"""
Dashboard Module - API Router

Dashboard özet ve analitik endpoint'leri.

Endpoint'ler:
- GET /api/v1/dashboard/summary - Genel özet bilgileri
- GET /api/v1/dashboard/savings/summary - Tasarruf özeti
"""
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.database import get_db
from src.modules.auth.dependencies import CurrentUser
from src.modules.dashboard.schemas import DashboardSummaryResponse, SavingsSummaryResponse, SavingsSummary
from src.modules.dashboard.service import DashboardService


router = APIRouter(prefix="/dashboard", tags=["Dashboard"])


async def get_dashboard_service(
    db: Annotated[AsyncSession, Depends(get_db)],
) -> DashboardService:
    """Dashboard service dependency."""
    return DashboardService(db)


DashboardServiceDep = Annotated[DashboardService, Depends(get_dashboard_service)]


@router.get(
    "/summary",
    response_model=DashboardSummaryResponse,
    summary="Dashboard Özeti",
    description="""
Dashboard için genel özet bilgilerini döner.

## 📊 İçerik

| Alan | Açıklama |
|------|----------|
| **devices** | Cihaz sayıları (toplam, online, offline, warning) |
| **gateways** | Gateway sayıları (toplam, online, offline) |
| **energy** | Enerji özeti (üretim, tüketim, net, anlık güç) |
| **wallet** | AWX cüzdan bakiyesi ve bekleyen işlemler |
| **alerts** | Alarm sayıları (kritik, uyarı, bilgi) |

## 🔐 Yetkilendirme

Bu endpoint JWT token gerektirir. Token Auth0'dan alınmalıdır.

## 📝 Örnek Kullanım

```bash
curl -X GET "https://api.awaxen.com/api/v1/dashboard/summary" \\
  -H "Authorization: Bearer <jwt_token>"
```

## 📤 Örnek Yanıt

```json
{
  "devices": {
    "total": 25,
    "online": 20,
    "offline": 3,
    "warning": 2
  },
  "gateways": {
    "total": 5,
    "online": 4,
    "offline": 1
  },
  "energy": {
    "total_production_kwh": 1250.5,
    "total_consumption_kwh": 980.3,
    "net_kwh": 270.2,
    "current_power_kw": 15.7
  },
  "wallet": {
    "balance": 1500.00,
    "pending": 50.00
  },
  "alerts": {
    "total": 3,
    "critical": 0,
    "warning": 2,
    "info": 1
  }
}
```
    """,
    responses={
        200: {
            "description": "Dashboard özeti başarıyla döndürüldü",
            "content": {
                "application/json": {
                    "example": {
                        "devices": {"total": 25, "online": 20, "offline": 3, "warning": 2},
                        "gateways": {"total": 5, "online": 4, "offline": 1},
                        "energy": {
                            "total_production_kwh": 1250.5,
                            "total_consumption_kwh": 980.3,
                            "net_kwh": 270.2,
                            "current_power_kw": 15.7
                        },
                        "wallet": {"balance": 1500.00, "pending": 50.00},
                        "alerts": {"total": 3, "critical": 0, "warning": 2, "info": 1}
                    }
                }
            }
        },
        401: {"description": "Yetkisiz erişim - Geçersiz veya eksik token"},
    },
)
async def get_dashboard_summary(
    current_user: CurrentUser,
    service: DashboardServiceDep,
) -> DashboardSummaryResponse:
    """Dashboard özet bilgilerini döner."""
    # Kullanıcının varsayılan organizasyonunu al
    org_id = None
    if current_user.organization_memberships:
        for membership in current_user.organization_memberships:
            if membership.is_default:
                org_id = str(membership.organization_id)
                break
    
    return await service.get_summary(org_id)


@router.get(
    "/savings/summary",
    response_model=SavingsSummaryResponse,
    summary="Tasarruf Özeti",
    description="""
Enerji tasarruf özetini döner.

## 📊 İçerik

| Alan | Açıklama |
|------|----------|
| **total_savings_kwh** | Toplam tasarruf (kWh) |
| **total_savings_tl** | Toplam tasarruf (TL) |
| **monthly_savings_kwh** | Aylık tasarruf (kWh) |
| **monthly_savings_tl** | Aylık tasarruf (TL) |
| **co2_reduction_kg** | CO2 azaltma (kg) |
| **tree_equivalent** | Ağaç eşdeğeri |

## 📋 Parametreler

| Parametre | Tip | Default | Açıklama |
|-----------|-----|---------|----------|
| `period` | string | all_time | Dönem (all_time, monthly, yearly) |

## 📝 Örnek Kullanım

```bash
curl -X GET "https://api.awaxen.com/api/v1/dashboard/savings/summary?period=monthly" \\
  -H "Authorization: Bearer <jwt_token>"
```

## 📤 Örnek Yanıt

```json
{
  "savings": {
    "total_savings_kwh": 1250.5,
    "total_savings_tl": 3750.00,
    "monthly_savings_kwh": 125.5,
    "monthly_savings_tl": 375.00,
    "co2_reduction_kg": 625.25,
    "tree_equivalent": 31
  },
  "period": "monthly",
  "currency": "TRY"
}
```
    """,
    responses={
        200: {
            "description": "Tasarruf özeti başarıyla döndürüldü",
            "content": {
                "application/json": {
                    "example": {
                        "savings": {
                            "total_savings_kwh": 1250.5,
                            "total_savings_tl": 3750.00,
                            "monthly_savings_kwh": 125.5,
                            "monthly_savings_tl": 375.00,
                            "co2_reduction_kg": 625.25,
                            "tree_equivalent": 31
                        },
                        "period": "monthly",
                        "currency": "TRY"
                    }
                }
            }
        },
        401: {"description": "Yetkisiz erişim - Geçersiz veya eksik token"},
    },
)
async def get_savings_summary(
    current_user: CurrentUser,
    service: DashboardServiceDep,
    period: str = Query(default="all_time", description="Dönem (all_time, monthly, yearly)"),
) -> SavingsSummaryResponse:
    """Tasarruf özet bilgilerini döner."""
    # TODO: Gerçek tasarruf hesaplaması implement edilecek
    return SavingsSummaryResponse(
        savings=SavingsSummary(
            total_savings_kwh=0.0,
            total_savings_tl=0.0,
            monthly_savings_kwh=0.0,
            monthly_savings_tl=0.0,
            co2_reduction_kg=0.0,
            tree_equivalent=0,
        ),
        period=period,
        currency="TRY",
    )
