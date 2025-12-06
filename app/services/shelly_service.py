"""
Shelly Cloud Service - Shelly cihazlarını kontrol et.

Shelly Cloud API: https://shelly-api-docs.shelly.cloud/cloud-control-api/
"""
from datetime import datetime
from typing import Optional
import requests

from app.extensions import db
from app.models import Integration, SmartDevice


class ShellyService:
    """
    Shelly Cloud API ile iletişim kurar.
    
    Kullanım:
        service = ShellyService(integration)
        service.turn_on_device(device)
        service.get_device_status(device)
    """
    
    BASE_URL = "https://shelly-cloud-eu.shelly.cloud"
    TIMEOUT = 30
    
    def __init__(self, integration: Integration):
        """
        Args:
            integration: Shelly entegrasyonu (token'lar burada)
        """
        if integration.provider != 'shelly':
            raise ValueError("Integration must be a Shelly integration")
        
        self.integration = integration
        self.auth_key = integration.access_token
        
        # Server URI (EU, US, etc.)
        provider_data = integration.provider_data or {}
        self.server_uri = provider_data.get('server_uri', 'shelly-cloud-eu.shelly.cloud')
        self.base_url = f"https://{self.server_uri}"
    
    def _make_request(self, endpoint: str, data: dict = None) -> dict:
        """API isteği yap."""
        if not self.auth_key:
            raise ValueError("No access token available")
        
        url = f"{self.base_url}/{endpoint}"
        payload = {'auth_key': self.auth_key}
        if data:
            payload.update(data)
        
        response = requests.post(url, data=payload, timeout=self.TIMEOUT)
        response.raise_for_status()
        
        result = response.json()
        if not result.get('isok'):
            raise Exception(f"Shelly API error: {result.get('errors', 'Unknown error')}")
        
        return result.get('data', {})
    
    def get_all_devices(self) -> list:
        """Tüm cihazları listele."""
        data = self._make_request('device/all_status')
        return data.get('devices_status', {})
    
    def get_device_status(self, device: SmartDevice) -> dict:
        """
        Tek bir cihazın durumunu al.
        
        Returns:
            {
                'online': bool,
                'output': bool,  # Açık/Kapalı
                'power': float,  # Anlık güç (W)
                'voltage': float,
                'energy': float,  # Toplam enerji (Wh)
            }
        """
        if not device.external_id:
            raise ValueError("Device has no external_id")
        
        data = self._make_request('device/status', {'id': device.external_id})
        
        # Shelly Gen2 format
        status = data.get('data', {})
        switch_status = status.get('switch:0', {})
        power_status = status.get('pm1:0', {}) or status.get('switch:0', {})
        
        return {
            'online': status.get('cloud', {}).get('connected', False),
            'output': switch_status.get('output', False),
            'power': power_status.get('apower', 0),
            'voltage': power_status.get('voltage', 0),
            'energy': power_status.get('aenergy', {}).get('total', 0),
            'temperature': status.get('temperature:0', {}).get('tC'),
        }
    
    def turn_on(self, device: SmartDevice) -> bool:
        """Cihazı aç."""
        return self._control_device(device, 'on')
    
    def turn_off(self, device: SmartDevice) -> bool:
        """Cihazı kapat."""
        return self._control_device(device, 'off')
    
    def toggle(self, device: SmartDevice) -> bool:
        """Cihazı toggle et."""
        return self._control_device(device, 'toggle')
    
    def _control_device(self, device: SmartDevice, action: str) -> bool:
        """
        Cihazı kontrol et.
        
        Args:
            device: Kontrol edilecek cihaz
            action: 'on', 'off', 'toggle'
        """
        if not device.external_id:
            raise ValueError("Device has no external_id")
        
        try:
            self._make_request('device/relay/control', {
                'id': device.external_id,
                'channel': 0,
                'turn': action
            })
            
            # Cihaz durumunu güncelle
            device.last_seen = datetime.utcnow()
            db.session.commit()
            
            return True
            
        except Exception as e:
            print(f"Shelly control error: {e}")
            return False
    
    def set_power_limit(self, device: SmartDevice, power_limit: int) -> bool:
        """
        Güç limitini ayarla (destekleyen cihazlar için).
        
        Args:
            power_limit: Watt cinsinden maksimum güç
        """
        # TODO: Implement power limit for supported devices
        return False
    
    def get_energy_data(self, device: SmartDevice, date_from: str = None, date_to: str = None) -> list:
        """
        Enerji tüketim verilerini al.
        
        Args:
            date_from: Başlangıç tarihi (YYYY-MM-DD)
            date_to: Bitiş tarihi (YYYY-MM-DD)
        """
        if not device.external_id:
            raise ValueError("Device has no external_id")
        
        params = {'id': device.external_id}
        if date_from:
            params['date_from'] = date_from
        if date_to:
            params['date_to'] = date_to
        
        try:
            data = self._make_request('device/consumption', params)
            return data.get('consumption', [])
        except Exception:
            return []
    
    def sync_devices(self) -> list:
        """
        Shelly Cloud'daki tüm cihazları veritabanına senkronize et.
        
        Returns:
            Senkronize edilen cihaz listesi
        """
        devices_data = self.get_all_devices()
        synced = []
        
        for device_id, device_info in devices_data.items():
            # Mevcut cihazı bul veya oluştur
            existing = SmartDevice.query.filter_by(
                integration_id=self.integration.id,
                external_id=device_id
            ).first()
            
            cloud_info = device_info.get('cloud', {})
            sys_info = device_info.get('sys', {})
            wifi_info = device_info.get('wifi', {})
            
            if existing:
                # Güncelle
                existing.is_online = cloud_info.get('connected', False)
                existing.last_seen = datetime.utcnow()
                existing.metadata = {
                    **existing.metadata,
                    'firmware': sys_info.get('fw_id'),
                    'ip': wifi_info.get('sta_ip'),
                    'mac': sys_info.get('mac'),
                }
            else:
                # Yeni cihaz
                new_device = SmartDevice(
                    organization_id=self.integration.organization_id,
                    integration_id=self.integration.id,
                    external_id=device_id,
                    name=device_info.get('name', f'Shelly {device_id[-4:]}'),
                    brand='shelly',
                    model=device_info.get('model', 'unknown'),
                    is_sensor=True,
                    is_actuator=True,
                    is_online=cloud_info.get('connected', False),
                    last_seen=datetime.utcnow(),
                    metadata={
                        'firmware': sys_info.get('fw_id'),
                        'ip': wifi_info.get('sta_ip'),
                        'mac': sys_info.get('mac'),
                    }
                )
                db.session.add(new_device)
            
            synced.append({
                'external_id': device_id,
                'name': device_info.get('name'),
                'online': cloud_info.get('connected', False)
            })
        
        # Son senkronizasyon zamanını güncelle
        self.integration.last_sync_at = datetime.utcnow()
        db.session.commit()
        
        return synced


def get_shelly_service(organization_id: str) -> Optional[ShellyService]:
    """
    Organization için Shelly servisini döndür.
    
    Args:
        organization_id: Organization UUID
    
    Returns:
        ShellyService instance veya None
    """
    integration = Integration.query.filter_by(
        organization_id=organization_id,
        provider='shelly',
        is_active=True,
        status='active'
    ).first()
    
    if integration:
        return ShellyService(integration)
    return None
