"""
Entegrasyon Senkronizasyon Task'ları.

Bulut entegrasyonlarından (Shelly, Tesla, Tapo) cihazları senkronize eder.
"""
from datetime import datetime

from app.extensions import celery, db
from app.models import Integration, SmartDevice
from app.data.integration_providers import get_shelly_device_type


@celery.task
def sync_all_integrations():
    """
    Tüm aktif entegrasyonları senkronize et.
    
    Celery Beat tarafından saatlik çağrılır.
    """
    active_integrations = Integration.query.filter_by(
        is_active=True, 
        status='active'
    ).all()
    
    results = []
    for integration in active_integrations:
        try:
            result = sync_integration_devices.delay(str(integration.id))
            results.append({
                'integration_id': str(integration.id),
                'provider': integration.provider,
                'task_id': result.id
            })
        except Exception as e:
            results.append({
                'integration_id': str(integration.id),
                'provider': integration.provider,
                'error': str(e)
            })
    
    return {
        'status': 'success',
        'integrations_queued': len(results),
        'results': results
    }


@celery.task(bind=True, max_retries=3)
def sync_integration_devices(self, integration_id: str):
    """
    Tek bir entegrasyonun cihazlarını senkronize et.
    
    "Cihazları Tara" butonunun arkasındaki iş.
    """
    integration = Integration.query.get(integration_id)
    if not integration:
        return {'status': 'error', 'message': 'Integration not found'}
    
    provider = integration.provider
    
    try:
        if provider == 'shelly':
            devices = _sync_shelly_devices(integration)
        elif provider == 'tesla':
            devices = _sync_tesla_devices(integration)
        elif provider == 'tapo':
            devices = _sync_tapo_devices(integration)
        elif provider == 'tuya':
            devices = _sync_tuya_devices(integration)
        else:
            return {'status': 'error', 'message': f'Unknown provider: {provider}'}
        
        # Son senkronizasyon zamanını güncelle
        integration.last_sync_at = datetime.utcnow()
        db.session.commit()
        
        return {
            'status': 'success',
            'provider': provider,
            'devices_synced': len(devices),
            'devices': devices
        }
        
    except Exception as e:
        db.session.rollback()
        self.retry(exc=e, countdown=60 * (2 ** self.request.retries))


def _sync_shelly_devices(integration: Integration) -> list:
    """
    Shelly Cloud'dan cihazları çek ve veritabanına kaydet.
    
    API: https://shelly-api-docs.shelly.cloud/cloud-control-api/
    """
    import requests
    
    access_token = integration.access_token
    if not access_token:
        raise ValueError("No access token for Shelly integration")
    
    provider_data = integration.provider_data or {}
    server_uri = provider_data.get('server_uri', 'shelly-cloud-eu.shelly.cloud')
    
    # Shelly Cloud API - Cihaz listesi
    url = f"https://{server_uri}/device/all_status"
    
    try:
        response = requests.post(url, data={
            'auth_key': access_token
        }, timeout=30)
        response.raise_for_status()
        data = response.json()
    except requests.RequestException as e:
        # API hatası - boş liste dön, mock data kullanma
        print(f"Shelly API error: {e}")
        return []
    
    # API başarısız yanıt döndüyse
    if not data.get('isok', False):
        print(f"Shelly API returned error: {data.get('errors', 'Unknown error')}")
        return []
    
    synced_devices = []
    devices_data = data.get('data', {}).get('devices_status', {})
    
    for device_id, device_info in devices_data.items():
        # Mevcut cihazı bul veya yeni oluştur
        existing = SmartDevice.query.filter_by(
            integration_id=integration.id,
            external_id=device_id
        ).first()
        
        if existing:
            # Güncelle
            existing.is_online = device_info.get('cloud', {}).get('connected', False)
            existing.last_seen = datetime.utcnow()
            existing.settings = {
                **(existing.settings or {}),
                'firmware': device_info.get('sys', {}).get('fw_id'),
                'ip': device_info.get('wifi', {}).get('sta_ip'),
            }
            # device_type yoksa güncelle
            if not existing.device_type:
                existing.device_type = get_shelly_device_type(existing.model)
        else:
            # Yeni cihaz oluştur
            model = device_info.get('model', 'unknown')
            device_type = get_shelly_device_type(model)
            
            # Device type'a göre is_sensor ve is_actuator belirle
            is_sensor = device_type in ['sensor', 'energy_meter']
            is_actuator = device_type in ['relay', 'plug', 'dimmer', 'rgbw']
            
            new_device = SmartDevice(
                organization_id=integration.organization_id,
                integration_id=integration.id,
                external_id=device_id,
                name=device_info.get('name', f'Shelly {device_id[-4:]}'),
                brand='shelly',
                model=model,
                device_type=device_type,
                is_sensor=is_sensor,
                is_actuator=is_actuator,
                is_online=device_info.get('cloud', {}).get('connected', False),
                last_seen=datetime.utcnow(),
                settings={
                    'firmware': device_info.get('sys', {}).get('fw_id'),
                    'ip': device_info.get('wifi', {}).get('sta_ip'),
                    'mac': device_info.get('sys', {}).get('mac'),
                }
            )
            db.session.add(new_device)
        
        synced_devices.append({
            'external_id': device_id,
            'name': device_info.get('name'),
            'online': device_info.get('cloud', {}).get('connected', False)
        })
    
    db.session.commit()
    return synced_devices


def _sync_tesla_devices(integration: Integration) -> list:
    """Tesla API'den araç ve Powerwall bilgilerini çek."""
    # TODO: Tesla Fleet API entegrasyonu
    # https://developer.tesla.com/docs/fleet-api
    return []


def _sync_tapo_devices(integration: Integration) -> list:
    """TP-Link Tapo cihazlarını senkronize et."""
    # TODO: Tapo Cloud API entegrasyonu
    return []


def _sync_tuya_devices(integration: Integration) -> list:
    """Tuya/Smart Life cihazlarını senkronize et."""
    # TODO: Tuya Cloud API entegrasyonu
    return []



# Mock data fonksiyonu kaldırıldı - Sistem tamamen dinamik çalışıyor


@celery.task
def refresh_integration_token(integration_id: str):
    """
    Entegrasyon OAuth token'ını yenile.
    
    Token süresi dolmadan önce çağrılmalı.
    """
    integration = Integration.query.get(integration_id)
    if not integration:
        return {'status': 'error', 'message': 'Integration not found'}
    
    refresh_token = integration.refresh_token
    if not refresh_token:
        return {'status': 'error', 'message': 'No refresh token available'}
    
    provider = integration.provider
    
    try:
        if provider == 'shelly':
            new_tokens = _refresh_shelly_token(refresh_token)
        elif provider == 'tesla':
            new_tokens = _refresh_tesla_token(refresh_token)
        else:
            return {'status': 'error', 'message': f'Token refresh not implemented for {provider}'}
        
        # Token'ları güncelle
        integration.access_token = new_tokens['access_token']
        if 'refresh_token' in new_tokens:
            integration.refresh_token = new_tokens['refresh_token']
        if 'expires_at' in new_tokens:
            integration.expires_at = new_tokens['expires_at']
        
        integration.status = 'active'
        db.session.commit()
        
        return {'status': 'success', 'message': 'Token refreshed successfully'}
        
    except Exception as e:
        integration.status = 'expired'
        db.session.commit()
        return {'status': 'error', 'message': str(e)}


def _refresh_shelly_token(refresh_token: str) -> dict:
    """Shelly OAuth token yenileme."""
    # TODO: Implement Shelly OAuth refresh
    raise NotImplementedError("Shelly token refresh not yet implemented")


def _refresh_tesla_token(refresh_token: str) -> dict:
    """Tesla OAuth token yenileme."""
    # TODO: Implement Tesla OAuth refresh
    raise NotImplementedError("Tesla token refresh not yet implemented")
