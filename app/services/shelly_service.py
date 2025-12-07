"""
Shelly Cloud Service - Shelly cihazlarını kontrol et.

Shelly Cloud API: https://shelly-api-docs.shelly.cloud/cloud-control-api/
"""
from datetime import datetime
from typing import Optional, Dict, Any

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
        
        provider_data = integration.provider_data or {}
        self.base_url = self._normalize_base_url(provider_data.get("server_uri"))
    
    @staticmethod
    def _normalize_base_url(server_uri: Optional[str]) -> str:
        """
        Shelly hesabına özel Server URI'yi normalize et.
        Kullanıcı http/https veya trailing slash bırakmış olabilir.
        """
        default = "https://shelly-cloud-eu.shelly.cloud"
        if not server_uri:
            return default
        server_uri = server_uri.strip()
        if not server_uri:
            return default
        if not server_uri.startswith(("http://", "https://")):
            server_uri = f"https://{server_uri}"
        return server_uri.rstrip("/")
    
    def _make_request(self, endpoint: str, data: dict = None) -> dict:
        """API isteği yap."""
        if not self.auth_key:
            raise ValueError("No access token available")
        
        url = f"{self.base_url}/{endpoint.lstrip('/')}"
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
        data = self._make_request('device/all_status', {
            'show_info': 'true',
            'no_shared': 'true',
        })
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
            device_meta = device_info.get('_dev_info', {})
            cloud_info = device_info.get('cloud', {}) or {}
            wifi_info = device_info.get('wifi', {}) or {}
            sys_info = device_info.get('sys', {}) or {}
            
            name = device_info.get('name') or device_info.get('device_name') or f"Shelly {device_id[-4:]}"
            device_code = device_meta.get('code') or device_info.get('model', 'unknown')
            device_type = self._infer_device_type(device_code)
            is_online = cloud_info.get('connected', False)
            
            existing = SmartDevice.query.filter_by(
                integration_id=self.integration.id,
                external_id=device_id
            ).first()
            
            settings_payload: Dict[str, Any] = {
                "gen": device_meta.get('gen', 'G1'),
                "ip": wifi_info.get('sta_ip') or device_info.get('ip'),
                "mac": sys_info.get('mac') or device_info.get('mac'),
                "fw_id": sys_info.get('fw_id'),
            }
            
            if existing:
                existing.name = name
                existing.brand = 'shelly'
                existing.model = device_code
                existing.device_type = device_type
                existing.is_online = is_online
                existing.last_seen = datetime.utcnow()
                existing.settings = {**(existing.settings or {}), **{k: v for k, v in settings_payload.items() if v}}
            else:
                new_device = SmartDevice(
                    organization_id=self.integration.organization_id,
                    integration_id=self.integration.id,
                    external_id=device_id,
                    name=name,
                    brand='shelly',
                    model=device_code,
                    is_sensor=True,
                    is_actuator=True,
                    is_online=is_online,
                    device_type=device_type,
                    last_seen=datetime.utcnow(),
                    settings={k: v for k, v in settings_payload.items() if v},
                )
                db.session.add(new_device)
            
            synced.append({
                'external_id': device_id,
                'name': name,
                'model': device_code,
                'online': is_online,
            })
        
        self.integration.last_sync_at = datetime.utcnow()
        db.session.commit()
        
        return synced
    
    @staticmethod
    def _infer_device_type(device_code: Optional[str]) -> str:
        if not device_code:
            return "relay"
        code = device_code.upper()
        if "THERM" in code or "TRV" in code:
            return "thermostat"
        if "PM" in code or "EM" in code:
            return "meter"
        if "RGB" in code or "DIM" in code:
            return "lighting"
        return "relay"


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
