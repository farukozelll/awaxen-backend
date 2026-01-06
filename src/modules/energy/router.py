"""
Energy Module - API Routes
"""
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.database import get_db
from src.modules.auth.dependencies import get_current_user
from src.modules.auth.models import User
from src.modules.energy.schemas import (
    RecommendationCreate,
    RecommendationResponse,
    RecommendationListResponse,
    RecommendationAction,
    CommandCreate,
    CommandResponse,
    CommandResult,
    RewardBalanceResponse,
    RewardLedgerListResponse,
    UserStreaksResponse,
    StreakResponse,
)
from src.modules.energy.service import (
    RecommendationService,
    CommandService,
    RewardService,
    StreakService,
)

router = APIRouter(prefix="/energy", tags=["Energy"])


# === Recommendations ===

@router.get("/recommendations", response_model=RecommendationListResponse)
async def get_recommendations(
    asset_id: UUID = Query(...),
    status: str | None = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get recommendations for an asset."""
    service = RecommendationService(db)
    recommendations, total = await service.get_for_asset(
        asset_id=asset_id,
        status=status,
        page=page,
        page_size=page_size,
    )
    return RecommendationListResponse(
        recommendations=recommendations,
        total=total,
    )


@router.get("/recommendations/{recommendation_id}", response_model=RecommendationResponse)
async def get_recommendation(
    recommendation_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get a specific recommendation."""
    service = RecommendationService(db)
    recommendation = await service.get_by_id(recommendation_id)
    if not recommendation:
        raise HTTPException(status_code=404, detail="Recommendation not found")
    return recommendation


@router.post("/recommendations/{recommendation_id}/respond", response_model=RecommendationResponse)
async def respond_to_recommendation(
    recommendation_id: UUID,
    data: RecommendationAction,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Respond to a recommendation (approve/defer/reject)."""
    service = RecommendationService(db)
    recommendation = await service.respond(recommendation_id, data.action)
    if not recommendation:
        raise HTTPException(status_code=404, detail="Recommendation not found")
    return recommendation


# === Commands ===

@router.post("/commands/dispatch", response_model=CommandResponse)
async def dispatch_command(
    data: CommandCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Dispatch a command to a device."""
    service = CommandService(db)
    command = await service.create(
        gateway_id=data.gateway_id,
        device_id=data.device_id,
        action=data.action,
        recommendation_id=data.recommendation_id,
        params=data.params,
    )
    return command


@router.post("/commands/{command_id}/ack")
async def ack_command(
    command_id: UUID,
    db: AsyncSession = Depends(get_db),
):
    """Acknowledge command receipt (called by gateway)."""
    service = CommandService(db)
    await service.mark_acked(command_id)
    return {"status": "ok"}


@router.post("/commands/{command_id}/result", response_model=CommandResponse)
async def submit_command_result(
    command_id: UUID,
    data: CommandResult,
    db: AsyncSession = Depends(get_db),
):
    """Submit command execution result (called by gateway)."""
    service = CommandService(db)
    command = await service.complete(
        command_id=command_id,
        success=data.status == "success",
        proof_payload=data.proof,
        error=data.error,
    )
    if not command:
        raise HTTPException(status_code=404, detail="Command not found")
    return command


# === Rewards ===

rewards_router = APIRouter(prefix="/rewards", tags=["Rewards"])


@rewards_router.get("/balance", response_model=RewardBalanceResponse)
async def get_reward_balance(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get current user's AWX balance."""
    service = RewardService(db)
    balance = await service.get_balance(current_user.id)
    return RewardBalanceResponse(**balance)


@rewards_router.get("/ledger", response_model=RewardLedgerListResponse)
async def get_reward_ledger(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get current user's reward ledger."""
    service = RewardService(db)
    entries, total = await service.get_ledger(
        user_id=current_user.id,
        page=page,
        page_size=page_size,
    )
    return RewardLedgerListResponse(
        entries=entries,
        total=total,
        page=page,
        page_size=page_size,
    )


@rewards_router.get("/streaks", response_model=UserStreaksResponse)
async def get_user_streaks(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get current user's streaks."""
    service = StreakService(db)
    streaks = await service.get_user_streaks(current_user.id)
    return UserStreaksResponse(
        streaks=[StreakResponse.model_validate(s) for s in streaks]
    )
