"""
Awaxen Services - Energy Savings Calculator.

Otomasyon kaynaklı enerji tasarruflarını hesaplar ve kaydeder.

Tasarruf Hesaplama Mantığı:
1. Cihaz kapandığında veya dimmer düşürüldüğünde DeviceStateLog'a kayıt yapılır
2. Cihaz tekrar açıldığında, kapalı kalma süresi hesaplanır
3. Tasarruf = Kapalı Süre (saat) × Cihaz Gücü (kW) × Elektrik Fiyatı
"""
from datetime import datetime, timezone, date, timedelta
from typing import Optional, Dict, Any, List
from decimal import Decimal
import logging

from sqlalchemy import func, and_

from app.extensions import db
from app.models import (
    SmartDevice,
    Organization,
    Automation,
    AutomationLog,
)
from app.models.savings import EnergySavings, DeviceStateLog

logger = logging.getLogger(__name__)


class SavingsService:
    """Enerji tasarruf hesaplama servisi."""
    
    # CO2 emission factor (kg CO2 per kWh) - Turkey average
    CO2_FACTOR = 0.5
    
    @classmethod
    def record_device_state_change(
        cls,
        device_id: str,
        new_state: str,
        power_level: int = 100,
        triggered_by: str = "manual",
        automation_id: str = None
    ) -> Optional[Dict[str, Any]]:
        """
        Cihaz durum değişikliğini kaydet ve tasarruf hesapla.
        
        Args:
            device_id: Cihaz UUID
            new_state: Yeni durum (on, off, dimmed)
            power_level: Güç seviyesi (0-100, dimmer için)
            triggered_by: Tetikleyen kaynak (automation, manual, schedule, vpp)
            automation_id: Otomasyon UUID (varsa)
        
        Returns:
            dict: Hesaplanan tasarruf bilgisi veya None
        """
        try:
            device = SmartDevice.query.get(device_id)
            if not device:
                logger.warning(f"Device not found: {device_id}")
                return None
            
            now = datetime.now(timezone.utc)
            
            # Get last state
            last_state = DeviceStateLog.query.filter_by(
                device_id=device_id
            ).order_by(DeviceStateLog.timestamp.desc()).first()
            
            # Record new state
            state_log = DeviceStateLog(
                device_id=device_id,
                timestamp=now,
                state=new_state,
                power_level=power_level,
                triggered_by=triggered_by,
                automation_id=automation_id
            )
            db.session.add(state_log)
            
            savings_result = None
            
            # Calculate savings if device was off and now turning on
            if last_state and last_state.state == "off" and new_state == "on":
                savings_result = cls._calculate_and_record_savings(
                    device=device,
                    off_start=last_state.timestamp,
                    off_end=now,
                    triggered_by=last_state.triggered_by,
                    automation_id=last_state.automation_id
                )
            
            # Calculate savings for dimmer reduction
            elif last_state and new_state == "dimmed" and last_state.state == "on":
                # Partial savings from dimming
                power_reduction = (100 - power_level) / 100
                if power_reduction > 0:
                    # Record as ongoing dimmed state - savings calculated when turned off or back to full
                    pass
            
            db.session.commit()
            return savings_result
            
        except Exception as e:
            logger.error(f"Error recording device state change: {e}")
            db.session.rollback()
            return None
    
    @classmethod
    def _calculate_and_record_savings(
        cls,
        device: SmartDevice,
        off_start: datetime,
        off_end: datetime,
        triggered_by: str,
        automation_id: str = None
    ) -> Dict[str, Any]:
        """
        Tasarruf hesapla ve kaydet.
        
        Args:
            device: SmartDevice instance
            off_start: Kapanma zamanı
            off_end: Açılma zamanı
            triggered_by: Tetikleyen kaynak
            automation_id: Otomasyon ID
        
        Returns:
            dict: Tasarruf bilgisi
        """
        # Get organization for electricity price
        org = Organization.query.get(device.organization_id)
        electricity_price = float(org.electricity_price_kwh) if org and org.electricity_price_kwh else 2.5
        currency = org.currency if org else "TRY"
        
        # Calculate duration in minutes
        duration = off_end - off_start
        duration_minutes = int(duration.total_seconds() / 60)
        
        # Get device power rating
        power_watt = device.power_rating_watt or 0
        if power_watt == 0:
            # Try to get from asset nominal power
            if device.asset and device.asset.nominal_power_watt:
                power_watt = device.asset.nominal_power_watt
        
        # Calculate savings
        savings = EnergySavings.calculate_savings(
            power_watt=power_watt,
            duration_minutes=duration_minutes,
            price_per_kwh=electricity_price
        )
        
        # Record savings
        today = off_end.date()
        
        # Check if there's already a record for this device today
        existing = EnergySavings.query.filter_by(
            organization_id=device.organization_id,
            device_id=device.id,
            date=today,
            source_type=triggered_by
        ).first()
        
        if existing:
            # Update existing record
            existing.off_duration_minutes += duration_minutes
            existing.energy_saved_kwh = Decimal(str(
                float(existing.energy_saved_kwh or 0) + savings["energy_saved_kwh"]
            ))
            existing.money_saved = Decimal(str(
                float(existing.money_saved or 0) + savings["money_saved"]
            ))
        else:
            # Create new record
            savings_record = EnergySavings(
                organization_id=device.organization_id,
                device_id=device.id,
                automation_id=automation_id,
                date=today,
                off_duration_minutes=duration_minutes,
                power_rating_watt=power_watt,
                energy_saved_kwh=Decimal(str(savings["energy_saved_kwh"])),
                money_saved=Decimal(str(savings["money_saved"])),
                currency=currency,
                source_type=triggered_by,
                details={
                    "off_start": off_start.isoformat(),
                    "off_end": off_end.isoformat(),
                    "electricity_price": electricity_price
                }
            )
            db.session.add(savings_record)
        
        return {
            "device_id": str(device.id),
            "device_name": device.name,
            "duration_minutes": duration_minutes,
            "power_watt": power_watt,
            "energy_saved_kwh": savings["energy_saved_kwh"],
            "money_saved": savings["money_saved"],
            "currency": currency,
            "source_type": triggered_by
        }
    
    @classmethod
    def get_organization_savings(
        cls,
        organization_id: str,
        start_date: date = None,
        end_date: date = None,
        group_by: str = "day"
    ) -> Dict[str, Any]:
        """
        Organizasyon tasarruf özeti.
        
        Args:
            organization_id: Organizasyon UUID
            start_date: Başlangıç tarihi
            end_date: Bitiş tarihi
            group_by: Gruplama (day, week, month)
        
        Returns:
            dict: Tasarruf özeti
        """
        if not start_date:
            start_date = date.today() - timedelta(days=30)
        if not end_date:
            end_date = date.today()
        
        # Get organization
        org = Organization.query.get(organization_id)
        currency = org.currency if org else "TRY"
        
        # Total savings
        totals = db.session.query(
            func.sum(EnergySavings.energy_saved_kwh).label('total_energy'),
            func.sum(EnergySavings.money_saved).label('total_money'),
            func.sum(EnergySavings.off_duration_minutes).label('total_minutes')
        ).filter(
            EnergySavings.organization_id == organization_id,
            EnergySavings.date >= start_date,
            EnergySavings.date <= end_date
        ).first()
        
        total_energy = float(totals[0] or 0)
        total_money = float(totals[1] or 0)
        total_minutes = int(totals[2] or 0)
        
        # By device
        by_device = db.session.query(
            EnergySavings.device_id,
            SmartDevice.name.label('device_name'),
            func.sum(EnergySavings.energy_saved_kwh).label('energy'),
            func.sum(EnergySavings.money_saved).label('money')
        ).join(
            SmartDevice, SmartDevice.id == EnergySavings.device_id
        ).filter(
            EnergySavings.organization_id == organization_id,
            EnergySavings.date >= start_date,
            EnergySavings.date <= end_date
        ).group_by(
            EnergySavings.device_id, SmartDevice.name
        ).order_by(
            func.sum(EnergySavings.energy_saved_kwh).desc()
        ).limit(10).all()
        
        # By source
        by_source = db.session.query(
            EnergySavings.source_type,
            func.sum(EnergySavings.energy_saved_kwh).label('energy'),
            func.sum(EnergySavings.money_saved).label('money')
        ).filter(
            EnergySavings.organization_id == organization_id,
            EnergySavings.date >= start_date,
            EnergySavings.date <= end_date
        ).group_by(EnergySavings.source_type).all()
        
        return {
            "period": {
                "start_date": start_date.isoformat(),
                "end_date": end_date.isoformat()
            },
            "totals": {
                "energy_saved_kwh": round(total_energy, 2),
                "money_saved": round(total_money, 2),
                "off_duration_hours": round(total_minutes / 60, 1),
                "co2_avoided_kg": round(total_energy * cls.CO2_FACTOR, 2),
                "currency": currency
            },
            "by_device": [
                {
                    "device_id": str(row[0]) if row[0] else None,
                    "device_name": row[1],
                    "energy_saved_kwh": round(float(row[2] or 0), 2),
                    "money_saved": round(float(row[3] or 0), 2)
                }
                for row in by_device
            ],
            "by_source": [
                {
                    "source": row[0],
                    "energy_saved_kwh": round(float(row[1] or 0), 2),
                    "money_saved": round(float(row[2] or 0), 2)
                }
                for row in by_source
            ]
        }
    
    @classmethod
    def estimate_potential_savings(
        cls,
        organization_id: str,
        daily_off_hours: int = 8
    ) -> Dict[str, Any]:
        """
        Potansiyel tasarruf tahmini.
        
        Tüm cihazların günde belirli saat kapatılması durumunda
        elde edilebilecek tasarrufu hesaplar.
        
        Args:
            organization_id: Organizasyon UUID
            daily_off_hours: Günlük kapalı kalma süresi (saat)
        
        Returns:
            dict: Potansiyel tasarruf tahmini
        """
        org = Organization.query.get(organization_id)
        electricity_price = float(org.electricity_price_kwh) if org and org.electricity_price_kwh else 2.5
        currency = org.currency if org else "TRY"
        
        # Get total power rating of all devices
        total_power = db.session.query(
            func.sum(SmartDevice.power_rating_watt)
        ).filter(
            SmartDevice.organization_id == organization_id,
            SmartDevice.is_active == True,
            SmartDevice.power_rating_watt > 0
        ).scalar() or 0
        
        # Calculate potential savings
        daily_kwh = (total_power / 1000) * daily_off_hours
        daily_money = daily_kwh * electricity_price
        
        monthly_kwh = daily_kwh * 30
        monthly_money = daily_money * 30
        
        yearly_kwh = daily_kwh * 365
        yearly_money = daily_money * 365
        
        return {
            "total_power_rating_watt": int(total_power),
            "daily_off_hours": daily_off_hours,
            "electricity_price_kwh": electricity_price,
            "currency": currency,
            "potential_savings": {
                "daily": {
                    "energy_kwh": round(daily_kwh, 2),
                    "money": round(daily_money, 2),
                    "co2_kg": round(daily_kwh * cls.CO2_FACTOR, 2)
                },
                "monthly": {
                    "energy_kwh": round(monthly_kwh, 2),
                    "money": round(monthly_money, 2),
                    "co2_kg": round(monthly_kwh * cls.CO2_FACTOR, 2)
                },
                "yearly": {
                    "energy_kwh": round(yearly_kwh, 2),
                    "money": round(yearly_money, 2),
                    "co2_kg": round(yearly_kwh * cls.CO2_FACTOR, 2)
                }
            }
        }
    
    @classmethod
    def record_automation_savings(
        cls,
        automation_id: str,
        device_id: str,
        action: str,
        duration_minutes: int = None
    ) -> Optional[Dict[str, Any]]:
        """
        Otomasyon kaynaklı tasarrufu kaydet.
        
        Bu metod otomasyon çalıştığında çağrılır.
        
        Args:
            automation_id: Otomasyon UUID
            device_id: Cihaz UUID
            action: Yapılan aksiyon (turn_off, dimmed, etc.)
            duration_minutes: Planlanan kapalı kalma süresi (opsiyonel)
        
        Returns:
            dict: Kayıt bilgisi
        """
        if action not in ("turn_off", "dimmed"):
            return None
        
        return cls.record_device_state_change(
            device_id=device_id,
            new_state="off" if action == "turn_off" else "dimmed",
            power_level=0 if action == "turn_off" else 50,
            triggered_by="automation",
            automation_id=automation_id
        )
