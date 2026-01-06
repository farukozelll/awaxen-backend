"""
Marketplace Module - API Routes
"""
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.database import get_db
from src.modules.auth.dependencies import get_current_user
from src.modules.auth.models import User
from src.modules.marketplace.schemas import (
    AlarmCreate,
    AlarmResponse,
    AlarmListResponse,
    JobCreate,
    JobResponse,
    JobListResponse,
    JobOfferCreate,
    JobOfferResponse,
    JobOfferListResponse,
    JobProofCreate,
    JobProofResponse,
    JobAssign,
    JobRate,
)
from src.modules.marketplace.service import (
    AlarmService,
    JobService,
    JobOfferService,
    JobProofService,
)

router = APIRouter(prefix="/maintenance", tags=["Maintenance"])


# === Alarms ===

@router.post("/alarms", response_model=AlarmResponse)
async def create_alarm(
    data: AlarmCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Create a new alarm."""
    service = AlarmService(db)
    alarm = await service.create(
        asset_id=data.asset_id,
        device_id=data.device_id,
        severity=data.severity,
        message=data.message,
        metadata=data.metadata,
    )
    return alarm


@router.get("/alarms", response_model=AlarmListResponse)
async def get_alarms(
    asset_id: UUID = Query(...),
    status: str | None = Query(None),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get alarms for an asset."""
    service = AlarmService(db)
    alarms = await service.get_for_asset(asset_id=asset_id, status=status)
    return AlarmListResponse(alarms=alarms, total=len(alarms))


@router.post("/alarms/{alarm_id}/acknowledge", response_model=AlarmResponse)
async def acknowledge_alarm(
    alarm_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Acknowledge an alarm."""
    service = AlarmService(db)
    alarm = await service.acknowledge(alarm_id, current_user.id)
    if not alarm:
        raise HTTPException(status_code=404, detail="Alarm not found")
    return alarm


@router.post("/alarms/{alarm_id}/close", response_model=AlarmResponse)
async def close_alarm(
    alarm_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Close an alarm."""
    service = AlarmService(db)
    alarm = await service.close(alarm_id)
    if not alarm:
        raise HTTPException(status_code=404, detail="Alarm not found")
    return alarm


# === Jobs ===

@router.post("/jobs", response_model=JobResponse)
async def create_job(
    data: JobCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Create a new maintenance job."""
    service = JobService(db)
    job = await service.create(
        asset_id=data.asset_id,
        category=data.category,
        title=data.title,
        created_by_user_id=current_user.id,
        alarm_id=data.alarm_id,
        description=data.description,
        urgency=data.urgency,
    )
    return job


@router.get("/jobs", response_model=JobListResponse)
async def get_jobs(
    asset_id: UUID | None = Query(None),
    status: str | None = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get jobs. If asset_id is provided, get jobs for that asset. Otherwise get open jobs."""
    service = JobService(db)
    if asset_id:
        jobs, total = await service.get_for_asset(
            asset_id=asset_id,
            status=status,
            page=page,
            page_size=page_size,
        )
    else:
        jobs, total = await service.get_open_jobs(page=page, page_size=page_size)
    
    return JobListResponse(
        jobs=jobs,
        total=total,
        page=page,
        page_size=page_size,
    )


@router.get("/jobs/{job_id}", response_model=JobResponse)
async def get_job(
    job_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get a specific job."""
    service = JobService(db)
    job = await service.get_by_id(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return job


@router.post("/jobs/{job_id}/assign", response_model=JobResponse)
async def assign_job(
    job_id: UUID,
    data: JobAssign,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Assign a job to an operator (accept an offer)."""
    offer_service = JobOfferService(db)
    job_service = JobService(db)
    
    # Accept the offer
    offer = await offer_service.accept(data.offer_id)
    if not offer:
        raise HTTPException(status_code=404, detail="Offer not found")
    
    # Assign the job
    job = await job_service.assign(job_id, offer.operator_user_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    
    return job


@router.post("/jobs/{job_id}/complete", response_model=JobResponse)
async def complete_job(
    job_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Mark a job as completed."""
    service = JobService(db)
    job = await service.complete(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return job


@router.post("/jobs/{job_id}/rate", response_model=JobResponse)
async def rate_job(
    job_id: UUID,
    data: JobRate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Rate a completed job."""
    service = JobService(db)
    job = await service.rate(job_id, data.rating, data.comment)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found or not completed")
    return job


# === Job Offers ===

@router.post("/jobs/{job_id}/offer", response_model=JobOfferResponse)
async def create_offer(
    job_id: UUID,
    data: JobOfferCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Create an offer for a job (operator)."""
    service = JobOfferService(db)
    offer = await service.create(
        job_id=job_id,
        operator_user_id=current_user.id,
        price_estimate=data.price_estimate,
        currency=data.currency,
        eta_minutes=data.eta_minutes,
        message=data.message,
    )
    return offer


@router.get("/jobs/{job_id}/offers", response_model=JobOfferListResponse)
async def get_job_offers(
    job_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get all offers for a job."""
    service = JobOfferService(db)
    offers = await service.get_for_job(job_id)
    return JobOfferListResponse(offers=offers, total=len(offers))


# === Job Proofs ===

@router.post("/jobs/{job_id}/proof", response_model=JobProofResponse)
async def upload_proof(
    job_id: UUID,
    data: JobProofCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Upload proof for a job."""
    service = JobProofService(db)
    proof = await service.create(
        job_id=job_id,
        proof_type=data.proof_type,
        proof_payload=data.proof_payload,
        uploaded_by_user_id=current_user.id,
    )
    return proof
