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
    ApproveRecommendationRequest,
    ApproveRecommendationResponse,
    CommandCreate,
    CommandResponse,
    CommandResult,
    CoreLoopStatusResponse,
    EpiasPrice,
    EpiasPriceHistoryRequest,
    EpiasPriceHistoryResponse,
    EpiasPriceResponse,
    RecommendationAction,
    RecommendationCreate,
    RecommendationListResponse,
    RecommendationResponse,
    RecommendationTriggerRequest,
    RecommendationTriggerResponse,
    RewardBalanceResponse,
    RewardDistributeRequest,
    RewardDistributeResponse,
    RewardLedgerListResponse,
    RewardLedgerResponse,
    StreakResponse,
    UserStreaksResponse,
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


# === Commands (Sistem Otomasyonu) ===

@router.post("/commands/dispatch", response_model=CommandResponse)
async def dispatch_command(
    data: CommandCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    **🤖 SİSTEM OTOMASYONU** - Enerji tasarrufu için otomatik komut gönderimi.
    
    Bu endpoint sistem tarafından (Recommendation onaylandığında) tetiklenir.
    Manuel cihaz kontrolü için `/api/v1/iot/devices/control` kullanın.
    
    **Fark:**
    | Endpoint | Kullanım | Tetikleyen |
    |----------|----------|------------|
    | `POST /iot/devices/control` | Manuel müdahale | Kullanıcı (UI'dan) |
    | `POST /energy/commands/dispatch` | Otomasyon | Sistem (Recommendation) |
    
    **Akış:**
    1. EPİAŞ fiyat yüksek → Recommendation oluşur
    2. Kullanıcı onaylar → Bu endpoint çağrılır
    3. Gateway komutu alır ve cihazı kontrol eder
    4. Gateway execution-proof gönderir
    5. AWX puan verilir
    """
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


@router.post("/commands/{command_id}/execution-proof", response_model=CommandResponse)
async def submit_execution_proof(
    command_id: UUID,
    data: CommandResult,
    db: AsyncSession = Depends(get_db),
):
    """
    Submit command execution proof (called by gateway).
    
    Gateway komut çalıştırdıktan sonra kanıt gönderir:
    - state_changed: Cihaz durumu değişti
    - power_drop: Güç tüketimi düştü
    
    Kanıt doğrulanırsa:
    1. Command status: SUCCESS
    2. Proof kaydedilir
    3. AWX puan kullanıcıya verilir
    
    **Örnek İstek:**
    ```json
    {
      "command_id": "550e8400-e29b-41d4-a716-446655440000",
      "status": "success",
      "executed_at": "2024-01-15T10:30:00Z",
      "proof": {
        "type": "state_changed",
        "before": {"state": "on", "power": 150},
        "after": {"state": "off", "power": 0},
        "duration_seconds": 3600
      }
    }
    ```
    """
    cmd_service = CommandService(db)
    reward_service = RewardService(db)
    
    command = await cmd_service.complete(
        command_id=command_id,
        success=data.status == "success",
        proof_payload=data.proof,
        error=data.error,
    )
    if not command:
        raise HTTPException(status_code=404, detail="Command not found")
    
    # Başarılı ise AWX puan ver
    if data.status == "success" and command.recommendation_id:
        # Recommendation'dan asset ve user bilgisi al
        reco_service = RecommendationService(db)
        recommendation = await reco_service.get_by_id(command.recommendation_id)
        
        if recommendation and recommendation.payload:
            user_id = recommendation.payload.get("user_id")
            if user_id:
                # AWX puan hesapla (basit formül: 10 + tasarruf TRY * 2)
                base_awx = 10
                saving_bonus = 0
                if recommendation.expected_saving_try:
                    saving_bonus = int(float(recommendation.expected_saving_try) * 2)
                
                total_awx = base_awx + saving_bonus
                
                await reward_service.credit(
                    user_id=UUID(user_id),
                    amount_awx=total_awx,
                    event_type="saving_action",
                    asset_id=recommendation.asset_id,
                    reference_type="command",
                    reference_id=command_id,
                    description=f"Enerji tasarrufu: {command.action}",
                )
    
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


# === Wallet/Rewards Distribution (Internal) ===

wallet_router = APIRouter(prefix="/wallet", tags=["Wallet"])


@wallet_router.post("/rewards/distribute", response_model=RewardDistributeResponse)
async def distribute_rewards(
    request: RewardDistributeRequest,
    db: AsyncSession = Depends(get_db),
):
    """
    Internal endpoint for distributing AWX rewards.
    
    Called by:
    - Command execution-proof handler (after successful proof)
    - Daily login bonus system
    - Streak bonus system
    - Referral system
    
    **Örnek İstek:**
    ```json
    {
      "user_id": "550e8400-e29b-41d4-a716-446655440000",
      "amount_awx": 50,
      "event_type": "saving_action",
      "asset_id": "550e8400-e29b-41d4-a716-446655440001",
      "reference_type": "command",
      "reference_id": "550e8400-e29b-41d4-a716-446655440002",
      "description": "Enerji tasarrufu: turn_off"
    }
    ```
    """
    service = RewardService(db)
    
    entry = await service.credit(
        user_id=request.user_id,
        amount_awx=request.amount_awx,
        event_type=request.event_type,
        asset_id=request.asset_id,
        reference_type=request.reference_type,
        reference_id=request.reference_id,
        description=request.description,
    )
    
    balance = await service.get_balance(request.user_id)
    
    return RewardDistributeResponse(
        message=f"{request.amount_awx} AWX puan eklendi",
        entry=RewardLedgerResponse.model_validate(entry),
        new_balance=balance["total_awx"],
    )


# === EPİAŞ Price Endpoints (Market Data) ===
# NOT: Fiyat verileri Market tag'i altında toplanır.
# Integrations modülü sadece API key yönetimi ve bağlantı testi içindir.

epias_router = APIRouter(prefix="/epias", tags=["Market"])


@epias_router.get("/prices/current", response_model=EpiasPriceResponse)
async def get_current_prices(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Get current EPİAŞ electricity prices and high price windows.
    
    Returns:
    - Current price
    - Next 24 hours forecast
    - High price windows (for recommendations)
    - Price threshold for triggering recommendations
    """
    from datetime import datetime, timezone
    from decimal import Decimal
    
    # TODO: Gerçek EPİAŞ API entegrasyonu
    # Şimdilik mock data
    now = datetime.now(timezone.utc)
    
    current_price = EpiasPrice(
        timestamp=now,
        price_try_kwh=Decimal("2.85"),
        is_high=True,
    )
    
    return EpiasPriceResponse(
        current_price=current_price,
        next_24h=[],
        high_price_windows=[],
        threshold_try_kwh=Decimal("2.50"),
    )


@epias_router.post("/prices/history", response_model=EpiasPriceHistoryResponse)
async def get_price_history(
    request: EpiasPriceHistoryRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get historical EPİAŞ prices for a time range."""
    from decimal import Decimal
    
    # TODO: Gerçek EPİAŞ API entegrasyonu
    return EpiasPriceHistoryResponse(
        prices=[],
        avg_price=Decimal("2.50"),
        min_price=Decimal("1.80"),
        max_price=Decimal("3.50"),
    )


# === Core Loop Endpoints ===

core_loop_router = APIRouter(prefix="/core-loop", tags=["Energy"])


@core_loop_router.get("/status/{asset_id}", response_model=CoreLoopStatusResponse)
async def get_core_loop_status(
    asset_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Get core loop status for an asset.
    
    Shows:
    - Current EPİAŞ price
    - Active recommendations count
    - Pending commands count
    - Today's savings and AWX earned
    """
    from datetime import datetime, timezone
    from decimal import Decimal
    
    now = datetime.now(timezone.utc)
    
    # TODO: Gerçek verilerle doldur
    return CoreLoopStatusResponse(
        asset_id=asset_id,
        current_price=EpiasPrice(
            timestamp=now,
            price_try_kwh=Decimal("2.85"),
            is_high=True,
        ),
        active_recommendations=0,
        pending_commands=0,
        total_savings_today_try=Decimal("0"),
        total_awx_today=0,
    )


@router.post("/recommendations/calculate", response_model=RecommendationTriggerResponse)
async def trigger_recommendation(
    request: RecommendationTriggerRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Manually trigger recommendation generation for an asset.
    
    Normally the system automatically triggers recommendations when:
    - EPİAŞ price > threshold
    - Total consumption > threshold
    - Controllable device available (safety != critical)
    
    Use `force=true` to bypass condition checks (for testing).
    """
    service = RecommendationService(db)
    
    # TODO: Implement full trigger logic
    # For now, create a simple recommendation
    
    if not request.force:
        # Check conditions
        # 1. Price check
        # 2. Consumption check
        # 3. Device availability check
        pass
    
    recommendation = await service.create(
        asset_id=request.asset_id,
        reason=request.reason,
        target_device_id=None,
        expected_saving_try=None,
        expected_saving_kwh=None,
        payload={"triggered_by": "manual", "user_id": str(current_user.id)},
    )
    
    return RecommendationTriggerResponse(
        triggered=True,
        message="Recommendation oluşturuldu",
        recommendation=RecommendationResponse.model_validate(recommendation),
    )


@router.post("/recommendations/{recommendation_id}/approve", response_model=ApproveRecommendationResponse)
async def approve_recommendation(
    recommendation_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Approve a recommendation and dispatch command to gateway.
    
    Flow:
    1. Update recommendation status to 'approved'
    2. Create command for target device
    3. Dispatch command to gateway via MQTT
    4. Return command info
    
    After gateway executes:
    - Gateway sends proof (state_changed, power_drop)
    - System verifies proof
    - AWX points awarded to user
    """
    reco_service = RecommendationService(db)
    cmd_service = CommandService(db)
    
    # Get recommendation
    recommendation = await reco_service.get_by_id(recommendation_id)
    if not recommendation:
        raise HTTPException(status_code=404, detail="Recommendation not found")
    
    # Update status to approved
    recommendation = await reco_service.respond(recommendation_id, "approve")
    
    # Create and dispatch command if device is specified
    command = None
    if recommendation.target_device_id:
        # Get device's gateway
        # TODO: Get gateway_id from device
        # For now, skip command creation
        pass
    
    return ApproveRecommendationResponse(
        message="Öneri onaylandı",
        recommendation=RecommendationResponse.model_validate(recommendation),
        command=command,
    )
