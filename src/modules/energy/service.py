"""
Energy Module - Service Layer

Core loop: Price trigger → Recommendation → Approval → Command → Proof → Reward
"""
import uuid
from datetime import datetime, timezone
from decimal import Decimal
from uuid import UUID

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from src.modules.energy.models import (
    Recommendation,
    RecommendationStatus,
    Command,
    CommandStatus,
    CommandProof,
    RewardLedger,
    Streak,
)


class RecommendationService:
    """Service for managing energy saving recommendations."""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def create(
        self,
        asset_id: UUID,
        reason: str,
        target_device_id: UUID | None = None,
        expected_saving_try: Decimal | None = None,
        expected_saving_kwh: Decimal | None = None,
        expires_at: datetime | None = None,
        payload: dict | None = None,
    ) -> Recommendation:
        """Create a new recommendation."""
        recommendation = Recommendation(
            asset_id=asset_id,
            target_device_id=target_device_id,
            reason=reason,
            expected_saving_try=expected_saving_try,
            expected_saving_kwh=expected_saving_kwh,
            status=RecommendationStatus.CREATED.value,
            expires_at=expires_at,
            payload=payload or {},
        )
        self.db.add(recommendation)
        await self.db.commit()
        await self.db.refresh(recommendation)
        return recommendation

    async def get_by_id(self, recommendation_id: UUID) -> Recommendation | None:
        """Get recommendation by ID."""
        result = await self.db.execute(
            select(Recommendation).where(Recommendation.id == recommendation_id)
        )
        return result.scalar_one_or_none()

    async def get_for_asset(
        self,
        asset_id: UUID,
        status: str | None = None,
        page: int = 1,
        page_size: int = 20,
    ) -> tuple[list[Recommendation], int]:
        """Get recommendations for an asset."""
        query = select(Recommendation).where(Recommendation.asset_id == asset_id)
        count_query = select(func.count(Recommendation.id)).where(
            Recommendation.asset_id == asset_id
        )

        if status:
            query = query.where(Recommendation.status == status)
            count_query = count_query.where(Recommendation.status == status)

        total_result = await self.db.execute(count_query)
        total = total_result.scalar() or 0

        query = query.order_by(Recommendation.created_at.desc())
        query = query.offset((page - 1) * page_size).limit(page_size)

        result = await self.db.execute(query)
        return list(result.scalars().all()), total

    async def respond(
        self, recommendation_id: UUID, action: str
    ) -> Recommendation | None:
        """Respond to a recommendation (approve/defer/reject)."""
        recommendation = await self.get_by_id(recommendation_id)
        if not recommendation:
            return None

        status_map = {
            "approve": RecommendationStatus.APPROVED.value,
            "defer": RecommendationStatus.DEFERRED.value,
            "reject": RecommendationStatus.REJECTED.value,
        }

        if action not in status_map:
            raise ValueError(f"Invalid action: {action}")

        recommendation.status = status_map[action]
        await self.db.commit()
        await self.db.refresh(recommendation)
        return recommendation

    async def mark_notified(self, recommendation_id: UUID) -> None:
        """Mark recommendation as notified."""
        recommendation = await self.get_by_id(recommendation_id)
        if recommendation:
            recommendation.status = RecommendationStatus.NOTIFIED.value
            await self.db.commit()


class CommandService:
    """Service for managing device commands."""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def create(
        self,
        gateway_id: UUID,
        device_id: UUID,
        action: str,
        recommendation_id: UUID | None = None,
        params: dict | None = None,
    ) -> Command:
        """Create a new command."""
        idempotency_key = f"{device_id}:{action}:{uuid.uuid4().hex[:8]}"
        
        command = Command(
            recommendation_id=recommendation_id,
            gateway_id=gateway_id,
            device_id=device_id,
            action=action,
            params=params or {},
            status=CommandStatus.QUEUED.value,
            idempotency_key=idempotency_key,
        )
        self.db.add(command)
        await self.db.commit()
        await self.db.refresh(command)
        return command

    async def get_by_id(self, command_id: UUID) -> Command | None:
        """Get command by ID."""
        result = await self.db.execute(
            select(Command).where(Command.id == command_id)
        )
        return result.scalar_one_or_none()

    async def mark_sent(self, command_id: UUID) -> None:
        """Mark command as sent."""
        command = await self.get_by_id(command_id)
        if command:
            command.status = CommandStatus.SENT.value
            command.sent_at = datetime.now(timezone.utc)
            await self.db.commit()

    async def mark_acked(self, command_id: UUID) -> None:
        """Mark command as acknowledged by gateway."""
        command = await self.get_by_id(command_id)
        if command:
            command.status = CommandStatus.ACKED.value
            command.acked_at = datetime.now(timezone.utc)
            await self.db.commit()

    async def complete(
        self,
        command_id: UUID,
        success: bool,
        proof_payload: dict | None = None,
        error: str | None = None,
    ) -> Command | None:
        """Complete a command with result."""
        command = await self.get_by_id(command_id)
        if not command:
            return None

        command.status = CommandStatus.SUCCESS.value if success else CommandStatus.FAILED.value
        command.finished_at = datetime.now(timezone.utc)
        command.error = error

        if success and proof_payload:
            proof = CommandProof(
                command_id=command_id,
                proof_type="state_changed",
                proof_payload=proof_payload,
                verified_at=datetime.now(timezone.utc),
            )
            self.db.add(proof)

        await self.db.commit()
        await self.db.refresh(command)
        return command


class RewardService:
    """Service for managing AWX rewards."""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def credit(
        self,
        user_id: UUID,
        amount_awx: int,
        event_type: str,
        asset_id: UUID | None = None,
        reference_type: str | None = None,
        reference_id: UUID | None = None,
        description: str | None = None,
        expires_at: datetime | None = None,
    ) -> RewardLedger:
        """Credit AWX points to user."""
        entry = RewardLedger(
            user_id=user_id,
            asset_id=asset_id,
            event_type=event_type,
            amount_awx=amount_awx,
            expires_at=expires_at,
            reference_type=reference_type,
            reference_id=reference_id,
            description=description,
        )
        self.db.add(entry)
        await self.db.commit()
        await self.db.refresh(entry)
        return entry

    async def get_balance(self, user_id: UUID) -> dict:
        """Get user's AWX balance."""
        now = datetime.now(timezone.utc)
        
        # Total (non-expired)
        total_result = await self.db.execute(
            select(func.coalesce(func.sum(RewardLedger.amount_awx), 0))
            .where(
                RewardLedger.user_id == user_id,
                (RewardLedger.expires_at.is_(None)) | (RewardLedger.expires_at > now),
            )
        )
        total = total_result.scalar() or 0

        return {
            "user_id": user_id,
            "total_awx": total,
            "available_awx": total,
            "pending_awx": 0,
        }

    async def get_ledger(
        self,
        user_id: UUID,
        page: int = 1,
        page_size: int = 20,
    ) -> tuple[list[RewardLedger], int]:
        """Get user's reward ledger."""
        query = select(RewardLedger).where(RewardLedger.user_id == user_id)
        count_query = select(func.count(RewardLedger.id)).where(
            RewardLedger.user_id == user_id
        )

        total_result = await self.db.execute(count_query)
        total = total_result.scalar() or 0

        query = query.order_by(RewardLedger.created_at.desc())
        query = query.offset((page - 1) * page_size).limit(page_size)

        result = await self.db.execute(query)
        return list(result.scalars().all()), total


class StreakService:
    """Service for managing user streaks."""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_user_streaks(self, user_id: UUID) -> list[Streak]:
        """Get all streaks for a user."""
        result = await self.db.execute(
            select(Streak).where(Streak.user_id == user_id)
        )
        return list(result.scalars().all())

    async def update_streak(
        self, user_id: UUID, streak_type: str
    ) -> Streak:
        """Update or create a streak."""
        result = await self.db.execute(
            select(Streak).where(
                Streak.user_id == user_id,
                Streak.streak_type == streak_type,
            )
        )
        streak = result.scalar_one_or_none()
        now = datetime.now(timezone.utc)

        if not streak:
            streak = Streak(
                user_id=user_id,
                streak_type=streak_type,
                current_count=1,
                longest_count=1,
                last_date=now,
            )
            self.db.add(streak)
        else:
            # Check if streak continues (within 24-48 hours for daily)
            if streak.last_date:
                hours_diff = (now - streak.last_date).total_seconds() / 3600
                if hours_diff <= 48:
                    streak.current_count += 1
                else:
                    streak.current_count = 1
            else:
                streak.current_count = 1

            if streak.current_count > streak.longest_count:
                streak.longest_count = streak.current_count
            streak.last_date = now

        await self.db.commit()
        await self.db.refresh(streak)
        return streak
