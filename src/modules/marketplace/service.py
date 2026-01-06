"""
Marketplace Module - Service Layer
"""
from datetime import datetime, timezone
from decimal import Decimal
from uuid import UUID

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from src.modules.marketplace.models import (
    Alarm,
    AlarmStatus,
    Job,
    JobStatus,
    JobOffer,
    JobOfferStatus,
    JobProof,
)


class AlarmService:
    """Service for managing alarms."""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def create(
        self,
        asset_id: UUID,
        severity: str,
        message: str,
        device_id: UUID | None = None,
        metadata: dict | None = None,
    ) -> Alarm:
        """Create a new alarm."""
        alarm = Alarm(
            asset_id=asset_id,
            device_id=device_id,
            severity=severity,
            message=message,
            status=AlarmStatus.OPEN.value,
            metadata_=metadata or {},
        )
        self.db.add(alarm)
        await self.db.commit()
        await self.db.refresh(alarm)
        return alarm

    async def get_by_id(self, alarm_id: UUID) -> Alarm | None:
        """Get alarm by ID."""
        result = await self.db.execute(
            select(Alarm).where(Alarm.id == alarm_id)
        )
        return result.scalar_one_or_none()

    async def get_for_asset(
        self,
        asset_id: UUID,
        status: str | None = None,
    ) -> list[Alarm]:
        """Get alarms for an asset."""
        query = select(Alarm).where(Alarm.asset_id == asset_id)
        if status:
            query = query.where(Alarm.status == status)
        query = query.order_by(Alarm.created_at.desc())
        result = await self.db.execute(query)
        return list(result.scalars().all())

    async def acknowledge(
        self, alarm_id: UUID, user_id: UUID
    ) -> Alarm | None:
        """Acknowledge an alarm."""
        alarm = await self.get_by_id(alarm_id)
        if alarm:
            alarm.status = AlarmStatus.ACKNOWLEDGED.value
            alarm.acknowledged_at = datetime.now(timezone.utc)
            alarm.acknowledged_by_user_id = user_id
            await self.db.commit()
            await self.db.refresh(alarm)
        return alarm

    async def close(self, alarm_id: UUID) -> Alarm | None:
        """Close an alarm."""
        alarm = await self.get_by_id(alarm_id)
        if alarm:
            alarm.status = AlarmStatus.CLOSED.value
            alarm.closed_at = datetime.now(timezone.utc)
            await self.db.commit()
            await self.db.refresh(alarm)
        return alarm


class JobService:
    """Service for managing maintenance jobs."""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def create(
        self,
        asset_id: UUID,
        category: str,
        title: str,
        created_by_user_id: UUID | None = None,
        alarm_id: UUID | None = None,
        description: str | None = None,
        urgency: str = "normal",
    ) -> Job:
        """Create a new job."""
        job = Job(
            asset_id=asset_id,
            created_by_user_id=created_by_user_id,
            alarm_id=alarm_id,
            category=category,
            title=title,
            description=description,
            urgency=urgency,
            status=JobStatus.OPEN.value,
        )
        self.db.add(job)
        await self.db.commit()
        await self.db.refresh(job)
        return job

    async def get_by_id(self, job_id: UUID) -> Job | None:
        """Get job by ID."""
        result = await self.db.execute(
            select(Job).where(Job.id == job_id)
        )
        return result.scalar_one_or_none()

    async def get_for_asset(
        self,
        asset_id: UUID,
        status: str | None = None,
        page: int = 1,
        page_size: int = 20,
    ) -> tuple[list[Job], int]:
        """Get jobs for an asset."""
        query = select(Job).where(Job.asset_id == asset_id)
        count_query = select(func.count(Job.id)).where(Job.asset_id == asset_id)

        if status:
            query = query.where(Job.status == status)
            count_query = count_query.where(Job.status == status)

        total_result = await self.db.execute(count_query)
        total = total_result.scalar() or 0

        query = query.order_by(Job.created_at.desc())
        query = query.offset((page - 1) * page_size).limit(page_size)

        result = await self.db.execute(query)
        return list(result.scalars().all()), total

    async def get_open_jobs(
        self,
        page: int = 1,
        page_size: int = 20,
    ) -> tuple[list[Job], int]:
        """Get all open jobs (for operators)."""
        query = select(Job).where(Job.status == JobStatus.OPEN.value)
        count_query = select(func.count(Job.id)).where(
            Job.status == JobStatus.OPEN.value
        )

        total_result = await self.db.execute(count_query)
        total = total_result.scalar() or 0

        query = query.order_by(Job.created_at.desc())
        query = query.offset((page - 1) * page_size).limit(page_size)

        result = await self.db.execute(query)
        return list(result.scalars().all()), total

    async def assign(
        self, job_id: UUID, operator_id: UUID
    ) -> Job | None:
        """Assign a job to an operator."""
        job = await self.get_by_id(job_id)
        if job:
            job.status = JobStatus.ASSIGNED.value
            job.assigned_operator_id = operator_id
            job.assigned_at = datetime.now(timezone.utc)
            await self.db.commit()
            await self.db.refresh(job)
        return job

    async def start(self, job_id: UUID) -> Job | None:
        """Start a job."""
        job = await self.get_by_id(job_id)
        if job:
            job.status = JobStatus.IN_PROGRESS.value
            await self.db.commit()
            await self.db.refresh(job)
        return job

    async def complete(self, job_id: UUID) -> Job | None:
        """Complete a job."""
        job = await self.get_by_id(job_id)
        if job:
            job.status = JobStatus.DONE.value
            job.completed_at = datetime.now(timezone.utc)
            await self.db.commit()
            await self.db.refresh(job)
        return job

    async def rate(
        self, job_id: UUID, rating: int, comment: str | None = None
    ) -> Job | None:
        """Rate a completed job."""
        job = await self.get_by_id(job_id)
        if job and job.status == JobStatus.DONE.value:
            job.rating = rating
            job.rating_comment = comment
            await self.db.commit()
            await self.db.refresh(job)
        return job


class JobOfferService:
    """Service for managing job offers."""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def create(
        self,
        job_id: UUID,
        operator_user_id: UUID,
        price_estimate: Decimal | None = None,
        currency: str = "TRY",
        eta_minutes: int | None = None,
        message: str | None = None,
    ) -> JobOffer:
        """Create a new job offer."""
        offer = JobOffer(
            job_id=job_id,
            operator_user_id=operator_user_id,
            price_estimate=price_estimate,
            currency=currency,
            eta_minutes=eta_minutes,
            message=message,
            status=JobOfferStatus.OFFERED.value,
        )
        self.db.add(offer)
        
        # Update job status
        job_result = await self.db.execute(
            select(Job).where(Job.id == job_id)
        )
        job = job_result.scalar_one_or_none()
        if job and job.status == JobStatus.OPEN.value:
            job.status = JobStatus.OFFERED.value
        
        await self.db.commit()
        await self.db.refresh(offer)
        return offer

    async def get_for_job(self, job_id: UUID) -> list[JobOffer]:
        """Get all offers for a job."""
        result = await self.db.execute(
            select(JobOffer)
            .where(JobOffer.job_id == job_id)
            .order_by(JobOffer.created_at.desc())
        )
        return list(result.scalars().all())

    async def accept(self, offer_id: UUID) -> JobOffer | None:
        """Accept an offer."""
        result = await self.db.execute(
            select(JobOffer).where(JobOffer.id == offer_id)
        )
        offer = result.scalar_one_or_none()
        if offer:
            offer.status = JobOfferStatus.ACCEPTED.value
            
            # Reject other offers for same job
            await self.db.execute(
                select(JobOffer)
                .where(
                    JobOffer.job_id == offer.job_id,
                    JobOffer.id != offer_id,
                    JobOffer.status == JobOfferStatus.OFFERED.value,
                )
            )
            
            await self.db.commit()
            await self.db.refresh(offer)
        return offer


class JobProofService:
    """Service for managing job proofs."""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def create(
        self,
        job_id: UUID,
        proof_type: str,
        proof_payload: dict,
        uploaded_by_user_id: UUID | None = None,
    ) -> JobProof:
        """Create a new job proof."""
        proof = JobProof(
            job_id=job_id,
            proof_type=proof_type,
            proof_payload=proof_payload,
            uploaded_by_user_id=uploaded_by_user_id,
        )
        self.db.add(proof)
        await self.db.commit()
        await self.db.refresh(proof)
        return proof

    async def get_for_job(self, job_id: UUID) -> list[JobProof]:
        """Get all proofs for a job."""
        result = await self.db.execute(
            select(JobProof)
            .where(JobProof.job_id == job_id)
            .order_by(JobProof.created_at.desc())
        )
        return list(result.scalars().all())

    async def verify(self, proof_id: UUID) -> JobProof | None:
        """Verify a proof."""
        result = await self.db.execute(
            select(JobProof).where(JobProof.id == proof_id)
        )
        proof = result.scalar_one_or_none()
        if proof:
            proof.verified_at = datetime.now(timezone.utc)
            await self.db.commit()
            await self.db.refresh(proof)
        return proof
