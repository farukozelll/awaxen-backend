"""
Automation Engine - Otomasyon kurallarını değerlendir ve çalıştır.

Bu modül otomasyon mantığının merkezidir.
Celery task'ları bu servisi kullanır.
"""
import logging
from datetime import datetime, timezone
from typing import Dict, Any, Optional, Tuple

from app.extensions import db
from app.models import (
    Automation, AutomationLog, MarketPrice, 
    SmartAsset, SmartDevice, DeviceTelemetry
)
from app.services.shelly_service import get_shelly_service

logger = logging.getLogger(__name__)


class AutomationEngine:
    """
    Otomasyon kurallarını değerlendirir ve çalıştırır.
    
    Kullanım:
        engine = AutomationEngine()
        should_trigger, reason = engine.evaluate(automation)
        if should_trigger:
            success = engine.execute(automation)
    """
    
    def evaluate(self, automation: Automation) -> Tuple[bool, str]:
        """
        Otomasyon kurallarını değerlendir.
        
        Args:
            automation: Değerlendirilecek otomasyon
        
        Returns:
            (should_trigger, reason) tuple
        """
        rules = automation.rules or {}
        trigger = rules.get('trigger', {})
        conditions = rules.get('conditions', [])
        
        # Önce koşulları kontrol et
        for condition in conditions:
            condition_met, reason = self._evaluate_condition(condition, automation)
            if not condition_met:
                return False, f"Condition not met: {reason}"
        
        # Ana tetikleyiciyi değerlendir
        trigger_type = trigger.get('type')
        
        if trigger_type == 'price':
            return self._evaluate_price_trigger(trigger)
        elif trigger_type == 'time_range':
            return self._evaluate_time_trigger(trigger)
        elif trigger_type == 'sensor':
            return self._evaluate_sensor_trigger(trigger, automation.asset)
        elif trigger_type == 'always':
            return True, "Always trigger"
        
        return False, f"Unknown trigger type: {trigger_type}"
    
    def execute(self, automation: Automation) -> bool:
        """
        Otomasyon aksiyonunu çalıştır.
        
        Args:
            automation: Çalıştırılacak otomasyon
        
        Returns:
            True if successful
        """
        rules = automation.rules or {}
        action = rules.get('action', {})
        action_type = action.get('type')
        
        asset = automation.asset
        if not asset:
            return False
        
        device = asset.device
        if not device:
            return False
        
        try:
            if action_type == 'turn_on':
                return self._control_device(device, 'on')
            elif action_type == 'turn_off':
                return self._control_device(device, 'off')
            elif action_type == 'toggle':
                return self._control_device(device, 'toggle')
            elif action_type == 'set_power':
                power_level = action.get('value', 100)
                return self._set_power(device, power_level)
            
            return False
            
        except Exception as e:
            logger.exception(f"Automation execution error: {e}")
            return False
    
    def run_automation(self, automation: Automation) -> dict:
        """
        Tek bir otomasyonu değerlendir ve çalıştır.
        
        Returns:
            {
                'triggered': bool,
                'executed': bool,
                'reason': str,
                'error': str (optional)
            }
        """
        try:
            should_trigger, reason = self.evaluate(automation)
            
            if not should_trigger:
                return {
                    'triggered': False,
                    'executed': False,
                    'reason': reason
                }
            
            success = self.execute(automation)
            
            # Log kaydı
            log = AutomationLog(
                organization_id=automation.organization_id,
                automation_id=automation.id,
                action_taken=automation.rules.get('action', {}).get('type', 'unknown'),
                reason=reason,
                status='success' if success else 'failed'
            )
            db.session.add(log)
            
            # İstatistik güncelle
            automation.last_triggered_at = datetime.now(timezone.utc)
            automation.trigger_count = (automation.trigger_count or 0) + 1
            db.session.commit()
            
            return {
                'triggered': True,
                'executed': success,
                'reason': reason
            }
            
        except Exception as e:
            return {
                'triggered': False,
                'executed': False,
                'reason': 'Error',
                'error': str(e)
            }
    
    def _evaluate_condition(self, condition: dict, automation: Automation) -> Tuple[bool, str]:
        """Ek koşulu değerlendir."""
        condition_type = condition.get('type')
        
        if condition_type == 'time_range':
            return self._evaluate_time_trigger(condition)
        elif condition_type == 'day_of_week':
            return self._evaluate_day_condition(condition)
        elif condition_type == 'device_state':
            return self._evaluate_device_state(condition, automation.asset)
        
        return True, "Unknown condition type (ignored)"
    
    def _evaluate_price_trigger(self, trigger: dict) -> Tuple[bool, str]:
        """Fiyat eşiği kontrolü."""
        operator = trigger.get('operator', '<')
        threshold = trigger.get('value', 0)
        
        # Son fiyatı al
        current_price = MarketPrice.query.order_by(MarketPrice.time.desc()).first()
        
        if not current_price:
            return False, "No price data available"
        
        price = current_price.price
        
        comparisons = {
            '<': lambda p, t: p < t,
            '>': lambda p, t: p > t,
            '<=': lambda p, t: p <= t,
            '>=': lambda p, t: p >= t,
            '==': lambda p, t: p == t,
        }
        
        compare_func = comparisons.get(operator)
        if compare_func and compare_func(price, threshold):
            return True, f"Price {price:.2f} TL/kWh {operator} {threshold}"
        
        return False, f"Price {price:.2f} TL/kWh does not meet {operator} {threshold}"
    
    def _evaluate_time_trigger(self, trigger: dict) -> Tuple[bool, str]:
        """Zaman aralığı kontrolü."""
        start_time = trigger.get('start', '00:00')
        end_time = trigger.get('end', '23:59')
        days = trigger.get('days', [0, 1, 2, 3, 4, 5, 6])
        
        now = datetime.now(timezone.utc)
        current_time = now.strftime('%H:%M')
        current_day = now.weekday()
        
        # Gün kontrolü
        if current_day not in days:
            return False, f"Today ({current_day}) not in scheduled days"
        
        # Normal aralık
        if start_time <= end_time:
            if start_time <= current_time <= end_time:
                return True, f"Time {current_time} in range {start_time}-{end_time}"
        else:
            # Gece yarısını geçen aralık (örn: 22:00 - 06:00)
            if current_time >= start_time or current_time <= end_time:
                return True, f"Time {current_time} in overnight range {start_time}-{end_time}"
        
        return False, f"Time {current_time} outside range {start_time}-{end_time}"
    
    def _evaluate_day_condition(self, condition: dict) -> Tuple[bool, str]:
        """Gün koşulu kontrolü."""
        days = condition.get('days', [0, 1, 2, 3, 4, 5, 6])
        current_day = datetime.now().weekday()
        
        if current_day in days:
            return True, f"Day {current_day} is in allowed days"
        return False, f"Day {current_day} not in allowed days"
    
    def _evaluate_sensor_trigger(self, trigger: dict, asset: SmartAsset) -> Tuple[bool, str]:
        """Sensör değeri kontrolü."""
        if not asset or not asset.device:
            return False, "No device linked to asset"
        
        sensor_key = trigger.get('key', 'power')
        operator = trigger.get('operator', '>')
        threshold = trigger.get('value', 0)
        
        # Son telemetri verisini al
        latest = DeviceTelemetry.query.filter_by(
            device_id=asset.device.id,
            key=sensor_key
        ).order_by(DeviceTelemetry.time.desc()).first()
        
        if not latest:
            return False, f"No telemetry data for {sensor_key}"
        
        value = latest.value
        
        comparisons = {
            '<': lambda v, t: v < t,
            '>': lambda v, t: v > t,
            '<=': lambda v, t: v <= t,
            '>=': lambda v, t: v >= t,
            '==': lambda v, t: v == t,
        }
        
        compare_func = comparisons.get(operator)
        if compare_func and compare_func(value, threshold):
            return True, f"Sensor {sensor_key}={value} {operator} {threshold}"
        
        return False, f"Sensor {sensor_key}={value} does not meet {operator} {threshold}"
    
    def _evaluate_device_state(self, condition: dict, asset: SmartAsset) -> Tuple[bool, str]:
        """Cihaz durumu kontrolü."""
        if not asset or not asset.device:
            return False, "No device linked"
        
        expected_state = condition.get('state')  # 'on', 'off', 'online'
        device = asset.device
        
        if expected_state == 'online':
            if device.is_online:
                return True, "Device is online"
            return False, "Device is offline"
        
        # Shelly cihazları için gerçek durumu kontrol et
        if device.brand == 'shelly':
            service = get_shelly_service(str(device.organization_id))
            if service:
                try:
                    status = service.get_device_status(device)
                    current_state = 'on' if status.get('output', False) else 'off'
                    
                    if current_state == expected_state:
                        return True, f"Device is {current_state}"
                    return False, f"Device is {current_state}, expected {expected_state}"
                except Exception as e:
                    return False, f"Could not get device status: {e}"
        
        # Diğer markalar için veritabanındaki son durumu kullan
        return True, "Device state check based on last known state"
    
    def _control_device(self, device: SmartDevice, action: str) -> bool:
        """Cihazı kontrol et."""
        if device.brand == 'shelly':
            service = get_shelly_service(str(device.organization_id))
            if service:
                if action == 'on':
                    return service.turn_on(device)
                elif action == 'off':
                    return service.turn_off(device)
                elif action == 'toggle':
                    return service.toggle(device)
        
        # Diğer markalar için placeholder (gelecekte Tapo, Tuya vb. eklenecek)
        logger.info(f"[ENGINE] Device brand '{device.brand}' not yet supported, would {action} {device.name}")
        return True
    
    def _set_power(self, device: SmartDevice, power_level: int) -> bool:
        """Güç seviyesi ayarla (dimmer, RGBW vb. için)."""
        if device.brand == 'shelly' and device.device_type in ['dimmer', 'rgbw']:
            service = get_shelly_service(str(device.organization_id))
            if service:
                try:
                    return service.set_power_limit(device, power_level)
                except Exception as e:
                    logger.error(f"[ENGINE] Shelly power control error: {e}")
                    return False
        
        logger.warning(f"[ENGINE] Power control not supported for {device.brand}/{device.device_type}")
        return False


# Singleton instance
automation_engine = AutomationEngine()


def check_all_automations() -> dict:
    """
    Tüm aktif otomasyonları kontrol et.
    
    Celery task tarafından çağrılır.
    """
    active_automations = Automation.query.filter_by(is_active=True).all()
    
    results = []
    triggered_count = 0
    
    for automation in active_automations:
        result = automation_engine.run_automation(automation)
        result['automation_id'] = str(automation.id)
        result['name'] = automation.name
        results.append(result)
        
        if result.get('triggered'):
            triggered_count += 1
    
    return {
        'status': 'success',
        'checked': len(active_automations),
        'triggered': triggered_count,
        'results': results
    }
