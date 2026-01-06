"""Dashboard Service - Summary and Analytics."""
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.logging import get_logger
from src.modules.dashboard.schemas import (
    AlertSummary,
    DashboardSummaryResponse,
    DeviceSummary,
    EnergySummary,
    GatewaySummary,
    WalletSummary,
)
from src.modules.iot.models import Device, DeviceStatus, Gateway, GatewayStatus
from src.modules.billing.models import Wallet

logger = get_logger(__name__)


class DashboardService:
    """Dashboard analytics service."""
    
    def __init__(self, db: AsyncSession):
        self.db = db
    
    async def get_summary(self, organization_id: str | None = None) -> DashboardSummaryResponse:
        """
        Dashboard özet bilgilerini döner.
        
        Args:
            organization_id: Opsiyonel organizasyon filtresi
        """
        devices = await self._get_device_summary(organization_id)
        gateways = await self._get_gateway_summary(organization_id)
        energy = await self._get_energy_summary(organization_id)
        wallet = await self._get_wallet_summary(organization_id)
        alerts = await self._get_alert_summary(organization_id)
        
        return DashboardSummaryResponse(
            devices=devices,
            gateways=gateways,
            energy=energy,
            wallet=wallet,
            alerts=alerts,
        )
    
    async def _get_device_summary(self, organization_id: str | None) -> DeviceSummary:
        """Cihaz özeti."""
        try:
            # Total devices
            stmt = select(func.count(Device.id))
            if organization_id:
                stmt = stmt.where(Device.organization_id == organization_id)
            result = await self.db.execute(stmt)
            total = result.scalar() or 0
            
            # Online devices
            stmt = select(func.count(Device.id)).where(Device.status == DeviceStatus.ONLINE)
            if organization_id:
                stmt = stmt.where(Device.organization_id == organization_id)
            result = await self.db.execute(stmt)
            online = result.scalar() or 0
            
            # Offline devices
            stmt = select(func.count(Device.id)).where(Device.status == DeviceStatus.OFFLINE)
            if organization_id:
                stmt = stmt.where(Device.organization_id == organization_id)
            result = await self.db.execute(stmt)
            offline = result.scalar() or 0
            
            # Warning devices
            stmt = select(func.count(Device.id)).where(Device.status == DeviceStatus.WARNING)
            if organization_id:
                stmt = stmt.where(Device.organization_id == organization_id)
            result = await self.db.execute(stmt)
            warning = result.scalar() or 0
            
            return DeviceSummary(
                total=total,
                online=online,
                offline=offline,
                warning=warning,
            )
        except Exception as e:
            logger.warning("Device summary error", error=str(e))
            return DeviceSummary()
    
    async def _get_gateway_summary(self, organization_id: str | None) -> GatewaySummary:
        """Gateway özeti."""
        try:
            # Total gateways
            stmt = select(func.count(Gateway.id))
            if organization_id:
                stmt = stmt.where(Gateway.organization_id == organization_id)
            result = await self.db.execute(stmt)
            total = result.scalar() or 0
            
            # Online gateways
            stmt = select(func.count(Gateway.id)).where(Gateway.status == GatewayStatus.ONLINE)
            if organization_id:
                stmt = stmt.where(Gateway.organization_id == organization_id)
            result = await self.db.execute(stmt)
            online = result.scalar() or 0
            
            # Offline gateways
            stmt = select(func.count(Gateway.id)).where(Gateway.status == GatewayStatus.OFFLINE)
            if organization_id:
                stmt = stmt.where(Gateway.organization_id == organization_id)
            result = await self.db.execute(stmt)
            offline = result.scalar() or 0
            
            return GatewaySummary(
                total=total,
                online=online,
                offline=offline,
            )
        except Exception as e:
            logger.warning("Gateway summary error", error=str(e))
            return GatewaySummary()
    
    async def _get_energy_summary(self, organization_id: str | None) -> EnergySummary:
        """Enerji özeti - şimdilik placeholder."""
        # TODO: Telemetri verilerinden hesapla
        return EnergySummary(
            total_production_kwh=0.0,
            total_consumption_kwh=0.0,
            net_kwh=0.0,
            current_power_kw=0.0,
        )
    
    async def _get_wallet_summary(self, organization_id: str | None) -> WalletSummary:
        """Cüzdan özeti."""
        try:
            if not organization_id:
                return WalletSummary()
            
            stmt = select(Wallet).where(Wallet.organization_id == organization_id)
            result = await self.db.execute(stmt)
            wallet = result.scalar_one_or_none()
            
            if wallet:
                return WalletSummary(
                    balance=float(wallet.balance),
                    pending=float(wallet.pending_balance) if hasattr(wallet, 'pending_balance') else 0.0,
                )
            return WalletSummary()
        except Exception as e:
            logger.warning("Wallet summary error", error=str(e))
            return WalletSummary()
    
    async def _get_alert_summary(self, organization_id: str | None) -> AlertSummary:
        """Alarm özeti - şimdilik placeholder."""
        # TODO: Alert tablosu oluşturulduğunda implement et
        return AlertSummary(
            total=0,
            critical=0,
            warning=0,
            info=0,
        )
