"""
Otomasyon Task'ları.

Dakikalık olarak aktif otomasyonları değerlendirir ve tetikler.
Tüm otomasyon mantığı automation_engine servisinde merkezileştirilmiştir.
"""
import logging
from typing import Dict, Any

from app.extensions import celery
from app.models import Automation
from app.services.automation_engine import automation_engine, check_all_automations

logger = logging.getLogger(__name__)


@celery.task(bind=True, max_retries=3, default_retry_delay=60)
def check_automations(self) -> Dict[str, Any]:
    """
    Tüm aktif otomasyonları kontrol et ve tetikle.
    
    Celery Beat tarafından her dakika çağrılır.
    Tüm mantık automation_engine servisinde.
    """
    try:
        result = check_all_automations()
        logger.info(
            f"[AUTOMATION_TASK] Checked {result['checked']} automations, "
            f"triggered {result['triggered']}"
        )
        return result
    except Exception as exc:
        logger.exception("[AUTOMATION_TASK] Error checking automations")
        raise self.retry(exc=exc)


@celery.task(bind=True, max_retries=3, default_retry_delay=30)
def run_single_automation(self, automation_id: str) -> Dict[str, Any]:
    """
    Tek bir otomasyonu manuel tetikle.
    
    Args:
        automation_id: Otomasyon UUID
    
    Returns:
        Çalıştırma sonucu
    """
    try:
        automation = Automation.query.get(automation_id)
        if not automation:
            logger.warning(f"[AUTOMATION_TASK] Automation not found: {automation_id}")
            return {'status': 'error', 'message': 'Automation not found'}
        
        result = automation_engine.run_automation(automation)
        
        logger.info(
            f"[AUTOMATION_TASK] Manual run: {automation.name} - "
            f"triggered={result.get('triggered')}, executed={result.get('executed')}"
        )
        
        return {
            'status': 'success',
            'automation_id': automation_id,
            'automation_name': automation.name,
            **result
        }
    except Exception as exc:
        logger.exception(f"[AUTOMATION_TASK] Error running automation {automation_id}")
        raise self.retry(exc=exc)


@celery.task
def run_organization_automations(organization_id: str) -> Dict[str, Any]:
    """
    Belirli bir organizasyonun tüm aktif otomasyonlarını çalıştır.
    
    Args:
        organization_id: Organization UUID
    
    Returns:
        Çalıştırma sonuçları
    """
    automations = Automation.query.filter_by(
        organization_id=organization_id,
        is_active=True
    ).order_by(Automation.priority.asc()).all()
    
    results = []
    triggered_count = 0
    
    for automation in automations:
        try:
            result = automation_engine.run_automation(automation)
            result['automation_id'] = str(automation.id)
            result['name'] = automation.name
            results.append(result)
            
            if result.get('triggered'):
                triggered_count += 1
        except Exception as e:
            logger.exception(f"[AUTOMATION_TASK] Error running automation {automation.id}")
            results.append({
                'automation_id': str(automation.id),
                'name': automation.name,
                'triggered': False,
                'error': str(e)
            })
    
    logger.info(
        f"[AUTOMATION_TASK] Organization {organization_id}: "
        f"checked {len(automations)}, triggered {triggered_count}"
    )
    
    return {
        'status': 'success',
        'organization_id': organization_id,
        'checked': len(automations),
        'triggered': triggered_count,
        'results': results
    }
