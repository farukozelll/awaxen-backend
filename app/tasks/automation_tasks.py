"""
Otomasyon Task'ları.

Dakikalık olarak aktif otomasyonları değerlendirir ve tetikler.
"""
from datetime import datetime

from app.extensions import celery, db
from app.models import Automation, AutomationLog, MarketPrice, SmartAsset, DeviceTelemetry
from app.services.shelly_service import get_shelly_service


@celery.task
def check_automations():
    """
    Tüm aktif otomasyonları kontrol et ve tetikle.
    
    Celery Beat tarafından her dakika çağrılır.
    """
    active_automations = Automation.query.filter_by(is_active=True).all()
    
    results = []
    for automation in active_automations:
        try:
            should_trigger, reason = _evaluate_automation(automation)
            
            if should_trigger:
                success = _execute_automation(automation)
                
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
                automation.last_triggered_at = datetime.utcnow()
                automation.trigger_count = (automation.trigger_count or 0) + 1
                
                results.append({
                    'automation_id': str(automation.id),
                    'name': automation.name,
                    'triggered': True,
                    'success': success,
                    'reason': reason
                })
        except Exception as e:
            results.append({
                'automation_id': str(automation.id),
                'name': automation.name,
                'triggered': False,
                'error': str(e)
            })
    
    db.session.commit()
    
    return {
        'status': 'success',
        'checked': len(active_automations),
        'triggered': len([r for r in results if r.get('triggered')]),
        'results': results
    }


def _evaluate_automation(automation: Automation) -> tuple[bool, str]:
    """
    Otomasyon kurallarını değerlendir.
    
    Returns:
        (should_trigger, reason) tuple
    """
    rules = automation.rules or {}
    trigger = rules.get('trigger', {})
    conditions = rules.get('conditions', [])
    
    trigger_type = trigger.get('type')
    
    # Fiyat bazlı tetikleyici
    if trigger_type == 'price':
        return _evaluate_price_trigger(trigger)
    
    # Zaman bazlı tetikleyici
    elif trigger_type == 'time_range':
        return _evaluate_time_trigger(trigger)
    
    # Sensör bazlı tetikleyici
    elif trigger_type == 'sensor':
        return _evaluate_sensor_trigger(trigger, automation.asset)
    
    return False, "Unknown trigger type"


def _evaluate_price_trigger(trigger: dict) -> tuple[bool, str]:
    """Fiyat eşiği kontrolü."""
    operator = trigger.get('operator', '<')
    threshold = trigger.get('value', 0)
    
    # Son fiyatı al
    current_price = MarketPrice.query.order_by(MarketPrice.time.desc()).first()
    
    if not current_price:
        return False, "No price data available"
    
    price = current_price.price
    
    if operator == '<' and price < threshold:
        return True, f"Price {price} TL/kWh is below threshold {threshold}"
    elif operator == '>' and price > threshold:
        return True, f"Price {price} TL/kWh is above threshold {threshold}"
    elif operator == '<=' and price <= threshold:
        return True, f"Price {price} TL/kWh is at or below threshold {threshold}"
    elif operator == '>=' and price >= threshold:
        return True, f"Price {price} TL/kWh is at or above threshold {threshold}"
    
    return False, f"Price {price} TL/kWh does not meet condition"


def _evaluate_time_trigger(trigger: dict) -> tuple[bool, str]:
    """Zaman aralığı kontrolü."""
    start_time = trigger.get('start', '00:00')
    end_time = trigger.get('end', '23:59')
    days = trigger.get('days', [0, 1, 2, 3, 4, 5, 6])  # Varsayılan: her gün
    
    now = datetime.now()
    current_time = now.strftime('%H:%M')
    current_day = now.weekday()
    
    # Gün kontrolü
    if current_day not in days:
        return False, f"Today ({current_day}) is not in scheduled days"
    
    # Saat kontrolü
    if start_time <= current_time <= end_time:
        return True, f"Current time {current_time} is within range {start_time}-{end_time}"
    
    # Gece yarısını geçen aralıklar için
    if start_time > end_time:
        if current_time >= start_time or current_time <= end_time:
            return True, f"Current time {current_time} is within overnight range {start_time}-{end_time}"
    
    return False, f"Current time {current_time} is outside range {start_time}-{end_time}"


def _evaluate_sensor_trigger(trigger: dict, asset: SmartAsset) -> tuple[bool, str]:
    """
    Sensör değeri kontrolü.
    
    Örnek trigger:
    {
        "type": "sensor",
        "key": "temperature",  # veya "power", "humidity", "voltage"
        "operator": ">",       # <, >, <=, >=, ==
        "value": 30            # Eşik değeri
    }
    """
    if not asset or not asset.device:
        return False, "Asset veya cihaz bulunamadı"
    
    sensor_key = trigger.get('key', 'temperature')
    operator = trigger.get('operator', '>')
    threshold = trigger.get('value', 0)
    
    # Son telemetri verisini al
    latest = DeviceTelemetry.query.filter_by(
        device_id=asset.device.id,
        key=sensor_key
    ).order_by(DeviceTelemetry.time.desc()).first()
    
    if not latest:
        return False, f"'{sensor_key}' için telemetri verisi bulunamadı"
    
    value = latest.value
    
    # Karşılaştırma operatörleri
    comparisons = {
        '<': lambda v, t: v < t,
        '>': lambda v, t: v > t,
        '<=': lambda v, t: v <= t,
        '>=': lambda v, t: v >= t,
        '==': lambda v, t: v == t,
        '!=': lambda v, t: v != t,
    }
    
    compare_func = comparisons.get(operator)
    if not compare_func:
        return False, f"Geçersiz operatör: {operator}"
    
    if compare_func(value, threshold):
        return True, f"Sensör {sensor_key}={value} {operator} {threshold} koşulu sağlandı"
    
    return False, f"Sensör {sensor_key}={value}, koşul {operator} {threshold} sağlanmadı"


def _execute_automation(automation: Automation) -> bool:
    """
    Otomasyon aksiyonunu çalıştır.
    
    Returns:
        True if successful, False otherwise
    """
    rules = automation.rules or {}
    action = rules.get('action', {})
    action_type = action.get('type')
    
    asset = automation.asset
    if not asset:
        return False
    
    try:
        if action_type == 'turn_on':
            # Cihazı aç
            return _control_device(asset, 'on')
        
        elif action_type == 'turn_off':
            # Cihazı kapat
            return _control_device(asset, 'off')
        
        elif action_type == 'set_power':
            # Güç seviyesi ayarla
            power_level = action.get('value', 100)
            return _set_device_power(asset, power_level)
        
        return False
        
    except Exception as e:
        print(f"Automation execution error: {e}")
        return False


def _control_device(asset: SmartAsset, state: str) -> bool:
    """
    Cihazı aç/kapat.
    
    Args:
        asset: Kontrol edilecek varlık
        state: 'on', 'off', 'toggle'
    
    Returns:
        True if successful, False otherwise
    """
    device = asset.device
    if not device:
        print(f"[AUTOMATION] Asset {asset.name} has no linked device")
        return False
    
    # Shelly cihazları için
    if device.brand == 'shelly':
        service = get_shelly_service(str(device.organization_id))
        if service:
            try:
                if state == 'on':
                    return service.turn_on(device)
                elif state == 'off':
                    return service.turn_off(device)
                elif state == 'toggle':
                    return service.toggle(device)
            except Exception as e:
                print(f"[AUTOMATION] Shelly control error: {e}")
                return False
        else:
            print(f"[AUTOMATION] No active Shelly integration for org {device.organization_id}")
            return False
    
    # Diğer markalar için placeholder
    print(f"[AUTOMATION] Device brand '{device.brand}' not yet supported, would {state} {device.name}")
    return True


def _set_device_power(asset: SmartAsset, power_level: int) -> bool:
    """
    Cihaz güç seviyesini ayarla (dimmer, HVAC vb. için).
    
    Args:
        asset: Kontrol edilecek varlık
        power_level: 0-100 arası güç yüzdesi
    
    Returns:
        True if successful, False otherwise
    """
    device = asset.device
    if not device:
        print(f"[AUTOMATION] Asset {asset.name} has no linked device")
        return False
    
    # Shelly dimmer/RGBW için
    if device.brand == 'shelly' and device.device_type in ['dimmer', 'rgbw']:
        service = get_shelly_service(str(device.organization_id))
        if service:
            try:
                return service.set_power_limit(device, power_level)
            except Exception as e:
                print(f"[AUTOMATION] Shelly power control error: {e}")
                return False
    
    print(f"[AUTOMATION] Power control not supported for {device.brand}/{device.device_type}")
    return False


@celery.task
def run_single_automation(automation_id: str):
    """Tek bir otomasyonu manuel tetikle."""
    automation = Automation.query.get(automation_id)
    if not automation:
        return {'status': 'error', 'message': 'Automation not found'}
    
    should_trigger, reason = _evaluate_automation(automation)
    
    if should_trigger:
        success = _execute_automation(automation)
        return {
            'status': 'success',
            'triggered': True,
            'executed': success,
            'reason': reason
        }
    
    return {
        'status': 'success',
        'triggered': False,
        'reason': reason
    }
