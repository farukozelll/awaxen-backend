"""
Admin Module - API Endpoints
Separated from Auth module for clean domain boundaries (Separation of Concerns).

L7 Best Practice:
- Auth modülü SADECE kimlik doğrulama (login, token, refresh) yapar
- Admin modülü kaynak yönetimi (organization, user, role) yapar

REST API yapısı:
- /api/v1/admin/organizations/*  → Organizasyon yönetimi
- /api/v1/admin/users/*          → Kullanıcı yönetimi (global)
- /api/v1/admin/roles/*          → Rol ve yetki yönetimi
- /api/v1/admin/system/*         → Sistem durumu ve sağlık
"""
from fastapi import APIRouter, Depends, HTTPException, status

from src.modules.auth.dependencies import (
    AuthServiceDep,
    CurrentUser,
    require_role,
)
from src.modules.auth.schemas import (
    AddUserToOrganizationRequest,
    AddUserToOrganizationResponse,
    AdminOrganizationDetailResponse,
    AdminOrganizationListResponse,
    AdminRoleListResponse,
    AdminUserListResponse,
    AssignRoleToUserRequest,
    AssignRoleToUserResponse,
    CreateOrganizationStep2Request,
    CreateOrganizationStep2Response,
    CreateOrganizationWithUserRequest,
    CreateOrganizationWithUserResponse,
    ImpersonateUserRequest,
    ImpersonateUserResponse,
    OrganizationModulesUpdate,
    OrganizationModulesUpdateRequest,
    OrganizationModulesUpdateResponse,
)

router = APIRouter(prefix="/admin", tags=["Admin"])


# ============================================================
# ORGANIZATION MANAGEMENT
# ============================================================

@router.post(
    "/organizations",
    response_model=CreateOrganizationWithUserResponse,
    summary="Organizasyon Oluştur",
    description="""
**Sadece Admin için.**

Yeni organizasyon ve ilk kullanıcı (tenant owner) oluşturur.

**Akış:**
1. Organization bilgileri (name, type, adres, koordinat)
2. İlk kullanıcı bilgileri (first_name, last_name, email, phone)
3. Kullanıcı otomatik tenant rolüyle eklenir
    """,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_role(["admin"]))],
)
async def create_organization(
    request: CreateOrganizationWithUserRequest,
    auth_service: AuthServiceDep,
) -> CreateOrganizationWithUserResponse:
    """Organizasyon ve ilk kullanıcı oluştur."""
    return await auth_service.create_organization_with_user(request)


@router.post(
    "/organizations/{org_id}/modules",
    response_model=CreateOrganizationStep2Response,
    summary="Modül Ata",
    description="""
**Sadece Admin için.**

Organizasyona aktif modülleri atar.

**Modüller:**
- core (otomatik eklenir)
- asset_management, iot, energy, rewards, billing, compliance, notifications, dashboard
    """,
    dependencies=[Depends(require_role(["admin"]))],
)
async def assign_organization_modules(
    org_id: str,
    request: OrganizationModulesUpdate,
    auth_service: AuthServiceDep,
) -> CreateOrganizationStep2Response:
    """Organizasyona modül ata."""
    step2_request = CreateOrganizationStep2Request(
        organization_id=org_id,
        modules=request.modules,
    )
    return await auth_service.create_organization_step2(step2_request)


@router.put(
    "/organizations/{org_id}/modules",
    response_model=OrganizationModulesUpdateResponse,
    summary="Modülleri Güncelle (Upsell & Feature Flagging)",
    description="""
**Sadece Admin için.**

Organizasyonun modüllerini günceller. Upsell ve Feature Flagging için kullanılır.

**Kullanım Senaryoları:**
- Müşteriye yeni modül satışı (Enerji Modülü aktif et)
- Deneme süresi bitince modülü kapat
- Modül ayarlarını güncelle

**Örnek İstek:**
```json
{
  "modules": [
    {"module_code": "iot", "is_active": true},
    {"module_code": "energy", "is_active": true, "trial_ends_at": "2024-02-15T00:00:00Z"},
    {"module_code": "billing", "is_active": false}
  ]
}
```
    """,
    dependencies=[Depends(require_role(["admin"]))],
)
async def update_organization_modules(
    org_id: str,
    request: OrganizationModulesUpdateRequest,
    auth_service: AuthServiceDep,
) -> OrganizationModulesUpdateResponse:
    """Organizasyon modüllerini güncelle (Upsell & Feature Flagging)."""
    import uuid
    return await auth_service.update_organization_modules(
        org_id=uuid.UUID(org_id),
        modules=[m.model_dump() for m in request.modules],
    )


@router.get(
    "/organizations",
    response_model=AdminOrganizationListResponse,
    summary="Organizasyonları Listele",
    description="""
**Sadece Admin için.**

Tüm organizasyonları listeler.

**Filtreler:** search, is_active, status
**Sayfalama:** page, page_size
    """,
    dependencies=[Depends(require_role(["admin"]))],
)
async def list_organizations(
    auth_service: AuthServiceDep,
    page: int = 1,
    page_size: int = 20,
    search: str | None = None,
    is_active: bool | None = None,
) -> AdminOrganizationListResponse:
    """Organizasyonları listele."""
    return await auth_service.list_all_organizations(
        page=page,
        page_size=page_size,
        search=search,
        is_active=is_active,
    )


@router.get(
    "/organizations/{org_id}",
    response_model=AdminOrganizationDetailResponse,
    summary="Organizasyon Detayı",
    description="Organizasyon detayını döner.",
    dependencies=[Depends(require_role(["admin"]))],
)
async def get_organization(
    org_id: str,
    auth_service: AuthServiceDep,
) -> AdminOrganizationDetailResponse:
    """Organizasyon detayı."""
    return await auth_service.get_organization_detail(org_id)


@router.delete(
    "/organizations/{org_id}",
    summary="Organizasyon Sil (Cascade)",
    description="""
**Sadece Admin için.**

Organizasyonu siler ve ilişkili kaynakları yönetir.

**Soft Delete (varsayılan):**
- Organizasyon is_active=False
- Kullanıcılar pasife çekilir (Zombi kullanıcı önleme)
- IoT cihazları ve Gateway'ler status='suspended'
- Veriler korunur, geri alınabilir

**Hard Delete:**
- Tüm veriler kalıcı olarak silinir (CASCADE)
- Geri alınamaz!
    """,
    dependencies=[Depends(require_role(["admin"]))],
)
async def delete_organization(
    org_id: str,
    auth_service: AuthServiceDep,
    hard_delete: bool = False,
):
    """Organizasyonu sil (cascade ile)."""
    import uuid
    return await auth_service.delete_organization_with_cascade(
        org_id=uuid.UUID(org_id),
        hard_delete=hard_delete,
    )


@router.patch(
    "/organizations/{org_id}/suspend",
    summary="Organizasyonu Askıya Al",
    description="""
**Sadece Admin için.**

Organizasyonu askıya alır. Kullanıcılar giriş yapamaz ama veriler silinmez.

**Kullanım Senaryoları:**
- Faturasını ödemeyen müşteri
- TOS (Kullanım Şartları) ihlali
- Güvenlik soruşturması
    """,
    dependencies=[Depends(require_role(["admin"]))],
)
async def suspend_organization(
    org_id: str,
    auth_service: AuthServiceDep,
    reason: str | None = None,
):
    """Organizasyonu askıya al."""
    import uuid
    return await auth_service.suspend_organization(
        org_id=uuid.UUID(org_id),
        reason=reason,
    )


@router.patch(
    "/organizations/{org_id}/reactivate",
    summary="Organizasyonu Yeniden Aktifleştir",
    description="Askıya alınmış organizasyonu yeniden aktifleştirir.",
    dependencies=[Depends(require_role(["admin"]))],
)
async def reactivate_organization(
    org_id: str,
    auth_service: AuthServiceDep,
):
    """Organizasyonu yeniden aktifleştir."""
    import uuid
    return await auth_service.reactivate_organization(
        org_id=uuid.UUID(org_id),
    )


@router.post(
    "/organizations/{org_id}/transfer-ownership",
    summary="Organizasyon Sahipliğini Devret",
    description="""
**Sadece Admin için.**

Organizasyon sahipliğini (Tenant Admin yetkisini) başka bir kullanıcıya devreder.

**Validasyonlar:**
- Yeni sahip organizasyonun mevcut üyesi olmalı
- Yeni sahip aktif kullanıcı olmalı

**İşlemler:**
- Eski sahip: tenant_admin → user rolüne düşürülür
- Yeni sahip: user → tenant_admin rolüne yükseltilir

**Kullanım Senaryoları:**
- Şirketin IT müdürü işten ayrıldı
- Organizasyon satıldı/devredildi
    """,
    dependencies=[Depends(require_role(["admin"]))],
)
async def transfer_organization_ownership(
    org_id: str,
    new_owner_user_id: str,
    auth_service: AuthServiceDep,
):
    """Organizasyon sahipliğini devret (validasyonlu)."""
    import uuid
    return await auth_service.transfer_organization_ownership_validated(
        org_id=uuid.UUID(org_id),
        new_owner_user_id=uuid.UUID(new_owner_user_id),
    )


@router.get(
    "/organizations/{org_id}/stats",
    summary="Organizasyon İstatistikleri",
    description="Organizasyon istatistiklerini döner.",
    dependencies=[Depends(require_role(["admin"]))],
)
async def get_organization_stats(
    org_id: str,
    auth_service: AuthServiceDep,
):
    """Organizasyon istatistikleri."""
    return await auth_service.get_organization_stats(org_id)


@router.get(
    "/organizations/{org_id}/users",
    response_model=AdminUserListResponse,
    summary="Organizasyon Kullanıcıları",
    description="Organizasyondaki kullanıcıları listeler.",
    dependencies=[Depends(require_role(["admin"]))],
)
async def list_organization_users(
    org_id: str,
    auth_service: AuthServiceDep,
    page: int = 1,
    page_size: int = 20,
    search: str | None = None,
    role: str | None = None,
    is_active: bool | None = None,
) -> AdminUserListResponse:
    """Organizasyon kullanıcılarını listele."""
    return await auth_service.list_organization_users(
        organization_id=org_id,
        page=page,
        page_size=page_size,
        search=search,
        role=role,
        is_active=is_active,
    )


@router.post(
    "/organizations/{org_id}/users",
    response_model=AddUserToOrganizationResponse,
    summary="Kullanıcı Davet Et",
    description="Organizasyona kullanıcı davet eder.",
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_role(["admin"]))],
)
async def invite_user_to_organization(
    org_id: str,
    request: AddUserToOrganizationRequest,
    auth_service: AuthServiceDep,
) -> AddUserToOrganizationResponse:
    """Kullanıcı davet et."""
    request.organization_id = org_id
    return await auth_service.add_user_to_organization(request)


# ============================================================
# USER MANAGEMENT (Global)
# ============================================================

@router.get(
    "/users",
    response_model=AdminUserListResponse,
    summary="Tüm Kullanıcıları Listele (Global)",
    description="""
**Sadece Admin için.**

Sistemdeki TÜM kullanıcıları (hangi organizasyonda olursa olsun) listeler.

**Filtreler:** search (email, ad, telefon), status, is_active
**Sayfalama:** page, page_size
    """,
    dependencies=[Depends(require_role(["admin"]))],
)
async def list_all_users_global(
    auth_service: AuthServiceDep,
    page: int = 1,
    page_size: int = 20,
    search: str | None = None,
    status: str | None = None,
    is_active: bool | None = None,
) -> AdminUserListResponse:
    """Tüm kullanıcıları listele (Global Search)."""
    return await auth_service.list_all_users_global(
        page=page,
        page_size=page_size,
        search=search,
        status=status,
        is_active=is_active,
    )


@router.post(
    "/users/{user_id}/role",
    response_model=AssignRoleToUserResponse,
    summary="Kullanıcıya Rol Ata",
    description="Kullanıcıya belirli bir organizasyonda rol atar.",
    dependencies=[Depends(require_role(["admin"]))],
)
async def assign_role_to_user(
    user_id: str,
    request: AssignRoleToUserRequest,
    auth_service: AuthServiceDep,
) -> AssignRoleToUserResponse:
    """Kullanıcıya rol ata."""
    return await auth_service.assign_role_to_user(user_id, request)


@router.post(
    "/users/{user_id}/revoke-sessions",
    summary="Kullanıcı Oturumlarını Sonlandır",
    description="""
**Sadece Admin için.**

Kullanıcının tüm aktif oturumlarını (token'larını) iptal eder.

**Yapılan İşlemler:**
1. Redis'te token blacklist'e eklenir
2. Auth0 Management API ile oturum kapatılır (varsa)

**Kullanım Senaryoları:**
- Kullanıcı hesabı hacklendiğinde
- Cihaz çalındığında
- Güvenlik ihlali şüphesinde
    """,
    dependencies=[Depends(require_role(["admin"]))],
)
async def revoke_user_sessions(
    user_id: str,
    auth_service: AuthServiceDep,
    revoke_auth0: bool = True,
):
    """Kullanıcı oturumlarını sonlandır (Redis + Auth0)."""
    import uuid
    return await auth_service.revoke_user_sessions_enhanced(
        user_id=uuid.UUID(user_id),
        revoke_auth0=revoke_auth0,
    )


@router.post(
    "/users/{user_id}/impersonate",
    response_model=ImpersonateUserResponse,
    summary="Kullanıcı Taklit Et (Impersonation)",
    description="""
**Sadece Admin için.**

Müşteri hizmetleri için: Admin, kullanıcının gözünden sistemi görebilir.
Geçici bir access token üretir.

**Güvenlik:**
- Sadece admin yapabilir
- Audit log'a kaydedilir
- Token süresi sınırlı (varsayılan 60 dakika, max 8 saat)
- Token'da impersonation flag'i var

**Kullanım Senaryoları:**
- Müşteri "Panelimde hata alıyorum" dediğinde
- Kullanıcı deneyimini test etmek için
- Sorun giderme (troubleshooting)
    """,
    dependencies=[Depends(require_role(["admin"]))],
)
async def impersonate_user(
    user_id: str,
    auth_service: AuthServiceDep,
    current_user: CurrentUser,
    request: ImpersonateUserRequest | None = None,
) -> ImpersonateUserResponse:
    """Kullanıcı taklit et (impersonation)."""
    import uuid
    reason = request.reason if request else None
    duration = request.duration_minutes if request else 60
    return await auth_service.impersonate_user(
        admin_user=current_user,
        target_user_id=uuid.UUID(user_id),
        reason=reason,
        duration_minutes=duration,
    )


@router.post(
    "/users/{user_id}/ban",
    summary="Kullanıcıyı Yasakla",
    description="""
**Sadece Admin için.**

Kullanıcıyı sistemden kalıcı olarak yasaklar.
Tüm oturumları sonlandırılır ve giriş yapması engellenir.
    """,
    dependencies=[Depends(require_role(["admin"]))],
)
async def ban_user(
    user_id: str,
    auth_service: AuthServiceDep,
    reason: str | None = None,
):
    """Kullanıcıyı yasakla."""
    import uuid
    return await auth_service.ban_user(
        user_id=uuid.UUID(user_id),
        reason=reason,
    )


# ============================================================
# ROLE & PERMISSION MANAGEMENT
# ============================================================

@router.get(
    "/roles",
    response_model=AdminRoleListResponse,
    summary="Rolleri Listele",
    description="Sistemdeki tüm rolleri listeler.",
    dependencies=[Depends(require_role(["admin"]))],
)
async def list_roles(auth_service: AuthServiceDep) -> AdminRoleListResponse:
    """Rolleri listele."""
    return await auth_service.list_all_roles()


@router.get(
    "/permissions",
    summary="Yetkileri Listele",
    description="Sistemdeki tüm yetkileri listeler.",
    dependencies=[Depends(require_role(["admin"]))],
)
async def list_permissions(auth_service: AuthServiceDep):
    """Yetkileri listele."""
    return await auth_service.list_all_permissions()


# ============================================================
# SYSTEM STATUS (Deep Health Check)
# ============================================================

@router.get(
    "/system/status",
    summary="Sistem Durumu (Deep Health Check)",
    description="""
**Sadece Admin için.**

Sistemin detaylı sağlık durumunu döner.

**Kontrol Edilen Servisler:**
- PostgreSQL/TimescaleDB bağlantısı + latency
- Redis bağlantısı + latency
- Celery worker durumu + queue depth
- MQTT broker durumu
- Dış servis entegrasyonları (EPİAŞ, Weather, Telegram)

**Uyarı Eşikleri:**
- DB Latency > 100ms: Yavaş
- Redis Latency > 50ms: Yavaş
- Celery Queue > 1000: Tıkanıklık riski
- Celery Queue > 10000: Kritik tıkanıklık
    """,
    dependencies=[Depends(require_role(["admin"]))],
)
async def get_system_status():
    """Sistem durumu (Deep Health Check)."""
    from datetime import datetime, timezone
    import time
    from src.core.config import settings
    
    status_report = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "environment": settings.environment,
        "services": {},
        "overall_status": "healthy",
        "warnings": [],
    }
    
    # PostgreSQL/TimescaleDB Check with Latency
    try:
        from src.core.database import async_session_maker
        from sqlalchemy import text
        
        start_time = time.perf_counter()
        async with async_session_maker() as session:
            result = await session.execute(text("SELECT 1"))
            result.scalar()
        db_latency_ms = (time.perf_counter() - start_time) * 1000
        
        db_status = "healthy"
        if db_latency_ms > 100:
            db_status = "slow"
            status_report["warnings"].append(f"DB latency high: {db_latency_ms:.2f}ms")
        
        status_report["services"]["database"] = {
            "status": db_status,
            "type": "PostgreSQL/TimescaleDB",
            "latency_ms": round(db_latency_ms, 2),
        }
    except Exception as e:
        status_report["services"]["database"] = {
            "status": "unhealthy",
            "error": str(e),
        }
        status_report["overall_status"] = "degraded"
    
    # Redis Check with Latency
    try:
        from src.core.redis import get_redis
        redis = await get_redis()
        if redis:
            start_time = time.perf_counter()
            await redis.ping()
            redis_latency_ms = (time.perf_counter() - start_time) * 1000
            
            redis_status = "healthy"
            if redis_latency_ms > 50:
                redis_status = "slow"
                status_report["warnings"].append(f"Redis latency high: {redis_latency_ms:.2f}ms")
            
            # Get some Redis info
            try:
                info = await redis.info("memory")
                used_memory = info.get("used_memory_human", "unknown")
            except Exception:
                used_memory = "unknown"
            
            status_report["services"]["redis"] = {
                "status": redis_status,
                "latency_ms": round(redis_latency_ms, 2),
                "used_memory": used_memory,
            }
        else:
            status_report["services"]["redis"] = {
                "status": "not_configured",
            }
    except Exception as e:
        status_report["services"]["redis"] = {
            "status": "unhealthy",
            "error": str(e),
        }
        status_report["overall_status"] = "degraded"
    
    # Celery Check with Queue Depth
    try:
        from src.worker import celery_app
        
        celery_status = {
            "status": "unknown",
            "workers": 0,
            "active_tasks": 0,
            "queued_tasks": 0,
        }
        
        # Worker check
        inspector = celery_app.control.inspect()
        active_workers = inspector.active()
        
        if active_workers:
            celery_status["workers"] = len(active_workers)
            celery_status["status"] = "healthy"
            
            # Count active tasks
            total_active = sum(len(tasks) for tasks in active_workers.values())
            celery_status["active_tasks"] = total_active
            
            # Get reserved (queued) tasks
            reserved = inspector.reserved()
            if reserved:
                total_reserved = sum(len(tasks) for tasks in reserved.values())
                celery_status["queued_tasks"] = total_reserved
                
                # Queue depth warnings
                if total_reserved > 10000:
                    celery_status["status"] = "critical"
                    status_report["warnings"].append(f"Celery queue CRITICAL: {total_reserved} tasks waiting")
                    status_report["overall_status"] = "degraded"
                elif total_reserved > 1000:
                    celery_status["status"] = "warning"
                    status_report["warnings"].append(f"Celery queue high: {total_reserved} tasks waiting")
        else:
            celery_status["status"] = "no_workers"
            status_report["warnings"].append("No Celery workers running")
        
        status_report["services"]["celery"] = celery_status
    except Exception as e:
        status_report["services"]["celery"] = {
            "status": "unknown",
            "error": str(e),
        }
    
    # External Integrations Check
    try:
        from src.modules.integrations.epias import get_epias_service
        from src.modules.integrations.weather import get_weather_service
        from src.modules.integrations.telegram import get_telegram_service
        
        epias = get_epias_service()
        weather = get_weather_service()
        telegram = get_telegram_service()
        
        status_report["services"]["integrations"] = {
            "epias": "configured" if epias.is_authenticated else "not_configured",
            "weather": "configured" if weather.is_configured else "not_configured",
            "telegram": "configured" if telegram.is_configured else "not_configured",
        }
    except Exception as e:
        status_report["services"]["integrations"] = {
            "status": "error",
            "error": str(e),
        }
    
    # MQTT Check
    status_report["services"]["mqtt"] = {
        "broker": settings.mqtt_broker_host,
        "port": settings.mqtt_broker_port,
        "status": "configured",
    }
    
    return status_report
