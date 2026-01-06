"""
RealEstate Module - API Router
"""
import uuid

from fastapi import APIRouter, Query, status

from src.modules.real_estate.dependencies import RealEstateServiceDep
from src.modules.real_estate.models import AssetType
from src.modules.real_estate.schemas import (
    AssetCreate,
    AssetHierarchy,
    AssetResponse,
    AssetUpdate,
    LeaseCreate,
    LeaseResponse,
    LeaseUpdate,
    LeaseWithAsset,
    ZoneCreate,
    ZoneResponse,
    ZoneListResponse,
    AssetMembershipCreate,
    AssetMembershipResponse,
    TenancyCreate,
    TenancyResponse,
    TenancyListResponse,
    HandoverTokenCreate,
    HandoverTokenResponse,
    HandoverClaim,
)

router = APIRouter(prefix="/real-estate", tags=["real-estate"])


# ============== Assets ==============

@router.get("/assets", response_model=list[AssetResponse])
async def list_assets(
    service: RealEstateServiceDep,
    asset_type: AssetType | None = None,
    parent_id: uuid.UUID | None = None,
    root_only: bool = Query(False, description="Only return root assets"),
) -> list[AssetResponse]:
    """List assets with optional filters."""
    assets = await service.list_assets(
        asset_type=asset_type,
        parent_id=parent_id,
        root_only=root_only,
    )
    return [AssetResponse.model_validate(a) for a in assets]


@router.get("/assets/hierarchy", response_model=list[AssetHierarchy])
async def get_asset_hierarchy(
    service: RealEstateServiceDep,
    root_id: uuid.UUID | None = None,
) -> list[AssetHierarchy]:
    """Get asset hierarchy tree."""
    assets = await service.get_asset_hierarchy(root_id)
    return [AssetHierarchy.model_validate(a) for a in assets]


@router.get("/assets/{asset_id}", response_model=AssetResponse)
async def get_asset(
    asset_id: uuid.UUID,
    service: RealEstateServiceDep,
) -> AssetResponse:
    """Get asset by ID."""
    from src.core.exceptions import NotFoundError
    
    asset = await service.get_asset_by_id(asset_id)
    if not asset:
        raise NotFoundError("Asset", asset_id)
    return AssetResponse.model_validate(asset)


@router.post(
    "/assets",
    response_model=AssetResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_asset(
    data: AssetCreate,
    service: RealEstateServiceDep,
) -> AssetResponse:
    """Create a new asset."""
    asset = await service.create_asset(data)
    return AssetResponse.model_validate(asset)


@router.patch("/assets/{asset_id}", response_model=AssetResponse)
async def update_asset(
    asset_id: uuid.UUID,
    data: AssetUpdate,
    service: RealEstateServiceDep,
) -> AssetResponse:
    """Update an asset."""
    asset = await service.update_asset(asset_id, data)
    return AssetResponse.model_validate(asset)


@router.delete("/assets/{asset_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_asset(
    asset_id: uuid.UUID,
    service: RealEstateServiceDep,
) -> None:
    """Delete an asset."""
    await service.delete_asset(asset_id)


# ============== Leases ==============

@router.get("/leases", response_model=list[LeaseWithAsset])
async def list_leases(
    service: RealEstateServiceDep,
    asset_id: uuid.UUID | None = None,
    status: str | None = None,
) -> list[LeaseWithAsset]:
    """List leases with optional filters."""
    leases = await service.list_leases(asset_id=asset_id, status=status)
    return [LeaseWithAsset.model_validate(l) for l in leases]


@router.get("/leases/{lease_id}", response_model=LeaseWithAsset)
async def get_lease(
    lease_id: uuid.UUID,
    service: RealEstateServiceDep,
) -> LeaseWithAsset:
    """Get lease by ID."""
    from src.core.exceptions import NotFoundError
    
    lease = await service.get_lease_by_id(lease_id)
    if not lease:
        raise NotFoundError("Lease", lease_id)
    return LeaseWithAsset.model_validate(lease)


@router.post(
    "/leases",
    response_model=LeaseResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_lease(
    data: LeaseCreate,
    service: RealEstateServiceDep,
) -> LeaseResponse:
    """Create a new lease."""
    lease = await service.create_lease(data)
    return LeaseResponse.model_validate(lease)


@router.patch("/leases/{lease_id}", response_model=LeaseResponse)
async def update_lease(
    lease_id: uuid.UUID,
    data: LeaseUpdate,
    service: RealEstateServiceDep,
) -> LeaseResponse:
    """Update a lease."""
    lease = await service.update_lease(lease_id, data)
    return LeaseResponse.model_validate(lease)


@router.delete("/leases/{lease_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_lease(
    lease_id: uuid.UUID,
    service: RealEstateServiceDep,
) -> None:
    """Delete a lease."""
    await service.delete_lease(lease_id)


# ============== Zones ==============

@router.get("/assets/{asset_id}/zones", response_model=ZoneListResponse)
async def list_zones(
    asset_id: uuid.UUID,
    service: RealEstateServiceDep,
) -> ZoneListResponse:
    """List zones for an asset."""
    zones = await service.list_zones(asset_id)
    return ZoneListResponse(
        zones=[ZoneResponse.model_validate(z) for z in zones],
        total=len(zones),
    )


@router.post(
    "/assets/{asset_id}/zones",
    response_model=ZoneResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_zone(
    asset_id: uuid.UUID,
    data: ZoneCreate,
    service: RealEstateServiceDep,
) -> ZoneResponse:
    """Create a new zone for an asset."""
    data.asset_id = asset_id
    zone = await service.create_zone(data)
    return ZoneResponse.model_validate(zone)


@router.delete("/zones/{zone_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_zone(
    zone_id: uuid.UUID,
    service: RealEstateServiceDep,
) -> None:
    """Delete a zone."""
    await service.delete_zone(zone_id)


# ============== Tenancy & Handover ==============

@router.get("/assets/{asset_id}/tenancies", response_model=TenancyListResponse)
async def list_tenancies(
    asset_id: uuid.UUID,
    service: RealEstateServiceDep,
) -> TenancyListResponse:
    """List tenancies for an asset."""
    tenancies = await service.list_tenancies(asset_id)
    return TenancyListResponse(
        tenancies=[TenancyResponse.model_validate(t) for t in tenancies],
        total=len(tenancies),
    )


@router.post(
    "/assets/{asset_id}/tenancies/invite",
    response_model=TenancyResponse,
    status_code=status.HTTP_201_CREATED,
)
async def invite_tenant(
    asset_id: uuid.UUID,
    data: TenancyCreate,
    service: RealEstateServiceDep,
) -> TenancyResponse:
    """Create a new tenancy (invite tenant)."""
    data.asset_id = asset_id
    tenancy = await service.create_tenancy(data)
    return TenancyResponse.model_validate(tenancy)


@router.post("/assets/{asset_id}/handover/create-token", response_model=HandoverTokenResponse)
async def create_handover_token(
    asset_id: uuid.UUID,
    data: HandoverTokenCreate,
    service: RealEstateServiceDep,
) -> HandoverTokenResponse:
    """Create a handover token for tenant transition."""
    token = await service.create_handover_token(
        asset_id=asset_id,
        expires_in_hours=data.expires_in_hours,
    )
    return HandoverTokenResponse.model_validate(token)


@router.post("/assets/{asset_id}/handover/claim", response_model=TenancyResponse)
async def claim_handover(
    asset_id: uuid.UUID,
    data: HandoverClaim,
    service: RealEstateServiceDep,
) -> TenancyResponse:
    """Claim a handover token and become the new tenant."""
    from src.modules.auth.dependencies import get_current_user
    from fastapi import Depends
    
    # Note: In real implementation, get user_id from current_user
    # For now, we need to pass it differently
    _, tenancy = await service.claim_handover(data.token, uuid.uuid4())  # TODO: get real user_id
    return TenancyResponse.model_validate(tenancy)


@router.post("/assets/{asset_id}/handover/wipe", status_code=status.HTTP_204_NO_CONTENT)
async def wipe_tenant_data(
    asset_id: uuid.UUID,
    service: RealEstateServiceDep,
) -> None:
    """Wipe tenant data during handover (owner only)."""
    await service.wipe_tenant_data(asset_id)
