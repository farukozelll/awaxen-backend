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
        """Enerji özeti - telemetri verilerinden hesaplanır."""
        from datetime import datetime, timezone, timedelta
        from sqlalchemy import select, func
        
        try:
            # Import telemetry model
            from src.modules.iot.models import Telemetry
            
            # Get today's date range
            now = datetime.now(timezone.utc)
            today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
            
            # Base query for organization filter
            base_filter = []
            if organization_id:
                # Join through device to filter by organization
                from src.modules.iot.models import Device
                device_ids_stmt = select(Device.id).where(Device.organization_id == organization_id)
                device_ids_result = await self.db.execute(device_ids_stmt)
                device_ids = [row[0] for row in device_ids_result.fetchall()]
                if device_ids:
                    base_filter.append(Telemetry.device_id.in_(device_ids))
            
            # Total consumption today (sum of power readings converted to kWh)
            # Assuming telemetry has 'power' field in watts and readings every minute
            consumption_stmt = select(func.sum(Telemetry.power)).where(
                Telemetry.timestamp >= today_start,
                *base_filter,
            )
            consumption_result = await self.db.execute(consumption_stmt)
            total_power_readings = consumption_result.scalar() or 0
            
            # Convert to kWh (assuming readings are in watts and 1 reading per minute)
            # kWh = (sum of watts) / 60 / 1000
            total_consumption_kwh = float(total_power_readings) / 60 / 1000
            
            # Get current power (latest reading)
            current_power_stmt = (
                select(Telemetry.power)
                .where(*base_filter)
                .order_by(Telemetry.timestamp.desc())
                .limit(1)
            )
            current_power_result = await self.db.execute(current_power_stmt)
            current_power_w = current_power_result.scalar() or 0
            current_power_kw = float(current_power_w) / 1000
            
            # Production (if solar panels exist) - check for negative power or production field
            production_stmt = select(func.sum(Telemetry.production)).where(
                Telemetry.timestamp >= today_start,
                *base_filter,
            )
            try:
                production_result = await self.db.execute(production_stmt)
                total_production = production_result.scalar() or 0
                total_production_kwh = float(total_production) / 60 / 1000
            except Exception:
                total_production_kwh = 0.0
            
            return EnergySummary(
                total_production_kwh=total_production_kwh,
                total_consumption_kwh=total_consumption_kwh,
                net_kwh=total_production_kwh - total_consumption_kwh,
                current_power_kw=current_power_kw,
            )
        except Exception as e:
            logger.warning("Energy summary calculation error", error=str(e))
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
        """Alarm özeti - notification tablosundan hesaplanır."""
        from datetime import datetime, timezone, timedelta
        from sqlalchemy import select, func
        
        try:
            # Import notification model for alerts
            from src.modules.notifications.models import Notification
            
            # Get last 24 hours
            now = datetime.now(timezone.utc)
            yesterday = now - timedelta(hours=24)
            
            # Base filter
            base_filter = [Notification.created_at >= yesterday]
            if organization_id:
                base_filter.append(Notification.organization_id == organization_id)
            
            # Total alerts
            total_stmt = select(func.count(Notification.id)).where(*base_filter)
            total_result = await self.db.execute(total_stmt)
            total = total_result.scalar() or 0
            
            # Critical alerts
            critical_stmt = select(func.count(Notification.id)).where(
                *base_filter,
                Notification.priority == "critical",
            )
            critical_result = await self.db.execute(critical_stmt)
            critical = critical_result.scalar() or 0
            
            # Warning alerts
            warning_stmt = select(func.count(Notification.id)).where(
                *base_filter,
                Notification.priority == "warning",
            )
            warning_result = await self.db.execute(warning_stmt)
            warning = warning_result.scalar() or 0
            
            # Info alerts
            info_stmt = select(func.count(Notification.id)).where(
                *base_filter,
                Notification.priority == "info",
            )
            info_result = await self.db.execute(info_stmt)
            info = info_result.scalar() or 0
            
            return AlertSummary(
                total=total,
                critical=critical,
                warning=warning,
                info=info,
            )
        except Exception as e:
            logger.warning("Alert summary calculation error", error=str(e))
            return AlertSummary(
                total=0,
                critical=0,
                warning=0,
                info=0,
            )
