"""Dashboard Schemas."""
from pydantic import BaseModel, Field


class DeviceSummary(BaseModel):
    """Cihaz özeti."""
    total: int = Field(default=0, description="Toplam cihaz sayısı")
    online: int = Field(default=0, description="Çevrimiçi cihaz sayısı")
    offline: int = Field(default=0, description="Çevrimdışı cihaz sayısı")
    warning: int = Field(default=0, description="Uyarı durumundaki cihaz sayısı")


class GatewaySummary(BaseModel):
    """Gateway özeti."""
    total: int = Field(default=0, description="Toplam gateway sayısı")
    online: int = Field(default=0, description="Çevrimiçi gateway sayısı")
    offline: int = Field(default=0, description="Çevrimdışı gateway sayısı")


class EnergySummary(BaseModel):
    """Enerji özeti."""
    total_production_kwh: float = Field(default=0.0, description="Toplam üretim (kWh)")
    total_consumption_kwh: float = Field(default=0.0, description="Toplam tüketim (kWh)")
    net_kwh: float = Field(default=0.0, description="Net enerji (kWh)")
    current_power_kw: float = Field(default=0.0, description="Anlık güç (kW)")


class WalletSummary(BaseModel):
    """Cüzdan özeti."""
    balance: float = Field(default=0.0, description="AWX bakiye")
    pending: float = Field(default=0.0, description="Bekleyen işlemler")


class AlertSummary(BaseModel):
    """Alarm özeti."""
    total: int = Field(default=0, description="Toplam alarm sayısı")
    critical: int = Field(default=0, description="Kritik alarm sayısı")
    warning: int = Field(default=0, description="Uyarı sayısı")
    info: int = Field(default=0, description="Bilgi sayısı")


class DashboardSummaryResponse(BaseModel):
    """
    Dashboard özet yanıtı.
    
    GET /api/v1/dashboard/summary endpoint'i için.
    """
    devices: DeviceSummary = Field(default_factory=DeviceSummary)
    gateways: GatewaySummary = Field(default_factory=GatewaySummary)
    energy: EnergySummary = Field(default_factory=EnergySummary)
    wallet: WalletSummary = Field(default_factory=WalletSummary)
    alerts: AlertSummary = Field(default_factory=AlertSummary)


class SavingsSummary(BaseModel):
    """Tasarruf özeti."""
    total_savings_kwh: float = Field(default=0.0, description="Toplam tasarruf (kWh)")
    total_savings_tl: float = Field(default=0.0, description="Toplam tasarruf (TL)")
    monthly_savings_kwh: float = Field(default=0.0, description="Aylık tasarruf (kWh)")
    monthly_savings_tl: float = Field(default=0.0, description="Aylık tasarruf (TL)")
    co2_reduction_kg: float = Field(default=0.0, description="CO2 azaltma (kg)")
    tree_equivalent: int = Field(default=0, description="Ağaç eşdeğeri")


class SavingsSummaryResponse(BaseModel):
    """
    Tasarruf özet yanıtı.
    
    GET /api/v1/dashboard/savings/summary endpoint'i için.
    """
    savings: SavingsSummary = Field(default_factory=SavingsSummary)
    period: str = Field(default="all_time", description="Dönem (all_time, monthly, yearly)")
    currency: str = Field(default="TRY", description="Para birimi")
