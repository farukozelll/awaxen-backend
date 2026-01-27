"""
Energy Module - API Routes
"""
from datetime import UTC
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.database import get_db
from src.modules.auth.dependencies import get_current_user
from src.modules.auth.models import User
from src.modules.energy.schemas import (
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
    CommandService,
    RecommendationService,
    RewardService,
    StreakService,
)

router = APIRouter(prefix="/energy", tags=["30. ⚡ Energy"])


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

rewards_router = APIRouter(prefix="/rewards", tags=["31. 🎁 Rewards"])


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

wallet_router = APIRouter(prefix="/wallet", tags=["32. 💰 Wallet"])


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

epias_router = APIRouter(prefix="/epias", tags=["33. 📈 Market"])


@epias_router.get("/prices/current", response_model=EpiasPriceResponse)
async def get_current_prices(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Get current EPİAŞ electricity prices and high price windows.
    
    Returns:
    - Current price (real-time from EPİAŞ API)
    - Next 24 hours forecast
    - High price windows (for recommendations)
    - Price threshold for triggering recommendations
    """
    from datetime import datetime
    from decimal import Decimal

    from src.modules.integrations.epias import get_epias_service
    
    now = datetime.now(UTC)
    epias = get_epias_service()
    
    # Get today's prices from EPİAŞ
    today_prices = await epias.get_day_ahead_prices(now.date())
    
    # Find current hour's price
    current_hour = now.hour
    current_price_value = Decimal("0")
    
    for price_data in today_prices:
        ts = price_data.get("timestamp", "")
        if ts:
            try:
                dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
                if dt.hour == current_hour:
                    # EPİAŞ returns TRY/MWh, convert to TRY/kWh
                    current_price_value = price_data.get("price", Decimal(0)) / 1000
                    break
            except ValueError:
                continue
    
    # If no price found, try to get average
    if current_price_value == 0:
        avg_price = await epias.get_average_price(now.date())
        if avg_price:
            current_price_value = avg_price / 1000  # Convert MWh to kWh
    
    # Calculate threshold (average + 20%)
    avg_price = await epias.get_average_price(now.date())
    threshold = (avg_price / 1000 * Decimal("1.2")) if avg_price else Decimal("2.50")
    
    # Determine if current price is high
    is_high = current_price_value > threshold
    
    current_price = EpiasPrice(
        timestamp=now,
        price_try_kwh=current_price_value,
        is_high=is_high,
    )
    
    # Build next 24h prices
    next_24h = []
    for price_data in today_prices:
        ts = price_data.get("timestamp", "")
        if ts:
            try:
                dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
                price_kwh = price_data.get("price", Decimal(0)) / 1000
                next_24h.append(EpiasPrice(
                    timestamp=dt,
                    price_try_kwh=price_kwh,
                    is_high=price_kwh > threshold,
                ))
            except ValueError:
                continue
    
    # Find high price windows (consecutive hours above threshold)
    high_price_windows = []
    window_start = None
    for price in next_24h:
        if price.is_high:
            if window_start is None:
                window_start = price.timestamp
        else:
            if window_start is not None:
                high_price_windows.append({
                    "start": window_start.isoformat(),
                    "end": price.timestamp.isoformat(),
                })
                window_start = None
    
    return EpiasPriceResponse(
        current_price=current_price,
        next_24h=next_24h,
        high_price_windows=high_price_windows,
        threshold_try_kwh=threshold,
    )


@epias_router.post("/prices/history", response_model=EpiasPriceHistoryResponse)
async def get_price_history(
    request: EpiasPriceHistoryRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get historical EPİAŞ prices for a time range."""
    from decimal import Decimal

    from src.modules.integrations.epias import get_epias_service
    
    epias = get_epias_service()
    
    # Get price range from EPİAŞ
    price_range = await epias.get_price_range(request.start_date, request.end_date)
    
    # Build response
    prices = []
    all_prices = []
    
    for _day_data in price_range:
        # Get detailed hourly prices for each day
        day_prices = await epias.get_day_ahead_prices(
            target_date=request.start_date  # This will be iterated in get_price_range
        )
        for p in day_prices:
            price_kwh = p.get("price", Decimal(0)) / 1000
            all_prices.append(price_kwh)
            prices.append(EpiasPrice(
                timestamp=p.get("timestamp"),
                price_try_kwh=price_kwh,
                is_high=False,  # Will be calculated based on threshold
            ))
    
    # Calculate statistics
    if all_prices:
        avg_price = sum(all_prices) / len(all_prices)
        min_price = min(all_prices)
        max_price = max(all_prices)
    else:
        avg_price = Decimal("0")
        min_price = Decimal("0")
        max_price = Decimal("0")
    
    return EpiasPriceHistoryResponse(
        prices=prices,
        avg_price=avg_price,
        min_price=min_price,
        max_price=max_price,
    )


# === Core Loop Endpoints ===

core_loop_router = APIRouter(prefix="/core-loop", tags=["30. ⚡ Energy"])


@core_loop_router.get("/status/{asset_id}", response_model=CoreLoopStatusResponse)
async def get_core_loop_status(
    asset_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Get core loop status for an asset.
    
    Shows:
    - Current EPİAŞ price (real-time)
    - Active recommendations count
    - Pending commands count
    - Today's savings and AWX earned
    """
    from datetime import datetime
    from decimal import Decimal

    from sqlalchemy import func, select

    from src.modules.energy.models import Command, Recommendation, RewardLedger
    from src.modules.integrations.epias import get_epias_service
    
    now = datetime.now(UTC)
    today = datetime.now(UTC).date()
    epias = get_epias_service()
    
    # Get current EPİAŞ price
    current_price_value = Decimal("0")
    today_prices = await epias.get_day_ahead_prices(today)
    current_hour = now.hour
    
    for price_data in today_prices:
        ts = price_data.get("timestamp", "")
        if ts:
            try:
                dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
                if dt.hour == current_hour:
                    current_price_value = price_data.get("price", Decimal(0)) / 1000
                    break
            except ValueError:
                continue
    
    # Calculate threshold
    avg_price = await epias.get_average_price(today)
    threshold = (avg_price / 1000 * Decimal("1.2")) if avg_price else Decimal("2.50")
    is_high = current_price_value > threshold
    
    # Count active recommendations for this asset
    active_reco_stmt = select(func.count(Recommendation.id)).where(
        Recommendation.asset_id == asset_id,
        Recommendation.status == "pending",
    )
    active_reco_result = await db.execute(active_reco_stmt)
    active_recommendations = active_reco_result.scalar() or 0
    
    # Count pending commands for this asset
    pending_cmd_stmt = select(func.count(Command.id)).where(
        Command.status.in_(["pending", "dispatched"]),
    )
    pending_cmd_result = await db.execute(pending_cmd_stmt)
    pending_commands = pending_cmd_result.scalar() or 0
    
    # Calculate today's savings (from completed recommendations)
    today_start = datetime.combine(today, datetime.min.time()).replace(tzinfo=UTC)
    savings_stmt = select(func.sum(Recommendation.expected_saving_try)).where(
        Recommendation.asset_id == asset_id,
        Recommendation.status == "approved",
        Recommendation.updated_at >= today_start,
    )
    savings_result = await db.execute(savings_stmt)
    total_savings = savings_result.scalar() or Decimal("0")
    
    # Calculate today's AWX earned
    awx_stmt = select(func.sum(RewardLedger.amount_awx)).where(
        RewardLedger.asset_id == asset_id,
        RewardLedger.created_at >= today_start,
    )
    awx_result = await db.execute(awx_stmt)
    total_awx = awx_result.scalar() or 0
    
    return CoreLoopStatusResponse(
        asset_id=asset_id,
        current_price=EpiasPrice(
            timestamp=now,
            price_try_kwh=current_price_value,
            is_high=is_high,
        ),
        active_recommendations=active_recommendations,
        pending_commands=pending_commands,
        total_savings_today_try=total_savings,
        total_awx_today=total_awx,
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
    from datetime import datetime
    from decimal import Decimal

    from sqlalchemy import select

    from src.modules.integrations.epias import get_epias_service
    from src.modules.iot.models import Device
    
    service = RecommendationService(db)
    epias = get_epias_service()
    
    # Condition checks (unless force=True)
    conditions_met = True
    condition_details = {}
    target_device_id = None
    expected_saving_try = None
    expected_saving_kwh = None
    
    if not request.force:
        # 1. Price check - Is current price above threshold?
        now = datetime.now(UTC)
        today = datetime.now(UTC).date()
        today_prices = await epias.get_day_ahead_prices(today)
        current_hour = now.hour
        current_price = Decimal("0")
        
        for price_data in today_prices:
            ts = price_data.get("timestamp", "")
            if ts:
                try:
                    dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
                    if dt.hour == current_hour:
                        current_price = price_data.get("price", Decimal(0)) / 1000  # TRY/kWh
                        break
                except ValueError:
                    continue
        
        avg_price = await epias.get_average_price(today)
        threshold = (avg_price / 1000 * Decimal("1.2")) if avg_price else Decimal("2.50")
        price_is_high = current_price > threshold
        condition_details["price_check"] = {
            "current_price": float(current_price),
            "threshold": float(threshold),
            "is_high": price_is_high,
        }
        
        if not price_is_high:
            conditions_met = False
        
        # 2. Device availability check - Find controllable device for this asset
        device_stmt = select(Device).where(
            Device.asset_id == request.asset_id,
            Device.controllable,
            Device.safety_profile != "critical",
            Device.status == "online",
        ).limit(1)
        device_result = await db.execute(device_stmt)
        controllable_device = device_result.scalar_one_or_none()
        
        condition_details["device_check"] = {
            "controllable_device_found": controllable_device is not None,
            "device_id": str(controllable_device.id) if controllable_device else None,
        }
        
        if controllable_device:
            target_device_id = controllable_device.id
            # Estimate savings (1 hour at current price, assuming 100W device)
            estimated_power_kw = Decimal("0.1")  # 100W default
            expected_saving_kwh = estimated_power_kw  # 1 hour
            expected_saving_try = expected_saving_kwh * current_price
        else:
            conditions_met = False
    
    # If conditions not met and not forced, return without creating recommendation
    if not conditions_met and not request.force:
        return RecommendationTriggerResponse(
            triggered=False,
            message="Koşullar sağlanmadı: " + ", ".join(
                k for k, v in condition_details.items() 
                if not v.get("is_high", True) or not v.get("controllable_device_found", True)
            ),
            recommendation=None,
        )
    
    # Create recommendation
    recommendation = await service.create(
        asset_id=request.asset_id,
        reason=request.reason or "Yüksek elektrik fiyatı - tasarruf fırsatı",
        target_device_id=target_device_id,
        expected_saving_try=expected_saving_try,
        expected_saving_kwh=expected_saving_kwh,
        payload={
            "triggered_by": "manual" if request.force else "auto",
            "user_id": str(current_user.id),
            "conditions": condition_details,
        },
    )
    
    return RecommendationTriggerResponse(
        triggered=True,
        message="Recommendation oluşturuldu" + (" (zorla)" if request.force else ""),
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
        # Get device's gateway from IoT module
        from sqlalchemy import select

        from src.modules.iot.models import Device
        
        device_result = await db.execute(
            select(Device).where(Device.id == recommendation.target_device_id)
        )
        device = device_result.scalar_one_or_none()
        
        if device and device.gateway_id:
            # Get gateway for MQTT topic
            from src.modules.iot.models import Gateway
            gateway_result = await db.execute(
                select(Gateway).where(Gateway.id == device.gateway_id)
            )
            gateway = gateway_result.scalar_one_or_none()
            
            # Create command for the device
            command = await cmd_service.create(
                gateway_id=device.gateway_id,
                device_id=device.id,
                action="turn_off",  # Default action from recommendation
                recommendation_id=recommendation_id,
                params=recommendation.payload.get("action_params") if recommendation.payload else None,
            )
            
            # MQTT publish to gateway
            if gateway:
                from src.modules.iot.mqtt_ingestion import mqtt_service
                await mqtt_service.publish_device_command(
                    gateway_serial=gateway.serial_number,
                    device_id=device.external_id or str(device.id),
                    action="turn_off",
                    parameters=recommendation.payload.get("action_params") if recommendation.payload else None,
                    command_id=str(command.id),
                )
    
    return ApproveRecommendationResponse(
        message="Öneri onaylandı" + (" ve komut oluşturuldu" if command else ""),
        recommendation=RecommendationResponse.model_validate(recommendation),
        command=CommandResponse.model_validate(command) if command else None,
    )
