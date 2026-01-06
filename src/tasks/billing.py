"""
Billing Background Tasks
"""
from datetime import date

from src.worker import celery_app
from src.core.logging import get_logger

logger = get_logger(__name__)


@celery_app.task(name="src.tasks.billing.check_overdue_invoices")
def check_overdue_invoices() -> dict:
    """
    Check for overdue invoices and update their status.
    Runs hourly via Celery Beat.
    """
    import asyncio
    from sqlalchemy import select, update
    from src.core.database import async_session_maker
    from src.modules.billing.models import Invoice, InvoiceStatus
    
    async def _check():
        async with async_session_maker() as session:
            today = date.today()
            
            # Find pending invoices past due date
            stmt = (
                update(Invoice)
                .where(
                    Invoice.status == InvoiceStatus.PENDING,
                    Invoice.due_date < today,
                )
                .values(status=InvoiceStatus.OVERDUE)
            )
            
            result = await session.execute(stmt)
            await session.commit()
            
            updated_count = result.rowcount
            logger.info(
                "Overdue invoices check completed",
                updated=updated_count,
            )
            
            return {"status": "completed", "updated": updated_count}
    
    return asyncio.run(_check())


@celery_app.task(name="src.tasks.billing.generate_monthly_invoices")
def generate_monthly_invoices(organization_id: str) -> dict:
    """
    Generate monthly invoices for an organization.
    """
    logger.info(
        "Monthly invoice generation started",
        organization_id=organization_id,
    )
    
    # Implementation would calculate usage and create invoices
    return {"status": "completed", "organization_id": organization_id}
