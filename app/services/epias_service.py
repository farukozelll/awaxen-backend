"""
EPİAŞ Şeffaflık Platformu 2.0 Entegrasyonu.

Dokümantasyon: https://seffaflik.epias.com.tr/electricity-service/technical/tr/index.html

TGT (Ticket Granting Ticket) ile kimlik doğrulama yapılır.
TGT yaklaşık 2 saat geçerlidir.

Özellikler:
- PTF (Piyasa Takas Fiyatı) / MCP (Market Clearing Price)
- SMF (Sistem Marjinal Fiyatı) / SMP (System Marginal Price)
- Gerçek zamanlı tüketim verileri
- Otomatik TGT yenileme
- Redis cache desteği
- Retry mekanizması
"""
import os
import logging
import requests
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any

# Redis cache için (opsiyonel)
try:
    import redis
    REDIS_AVAILABLE = True
except ImportError:
    REDIS_AVAILABLE = False

logger = logging.getLogger(__name__)


class EpiasService:
    """
    EPİAŞ API Client - PTF, SMF ve tüketim verilerini çeker.
    """
    
    BASE_URL = "https://seffaflik.epias.com.tr/electricity-service/v1"
    AUTH_URL = "https://giris.epias.com.tr/cas/v1/tickets"
    
    # EPİAŞ botları engelleyebilir, browser gibi görünmek önemli
    HEADERS = {
        "Content-Type": "application/json",
        "Accept": "application/json",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Origin": "https://seffaflik.epias.com.tr",
        "Referer": "https://seffaflik.epias.com.tr/transparency/piyasalar/gop/ptf.xhtml"
    }
    
    TGT_CACHE_KEY = "epias:tgt"
    TGT_EXPIRY_SECONDS = 7000  # ~2 saat, biraz erken yenile
    
    def __init__(self):
        self.username = os.getenv("EPIAS_USERNAME")
        self.password = os.getenv("EPIAS_PASSWORD")
        self._tgt = None
        self._tgt_expires_at = None
        self._redis = None
        
        # Redis bağlantısı (varsa)
        if REDIS_AVAILABLE:
            redis_url = os.getenv("REDIS_URL", "redis://localhost:6379/0")
            try:
                self._redis = redis.from_url(redis_url)
            except Exception:
                pass
    
    def get_tgt(self, force_refresh: bool = False) -> Optional[str]:
        """
        TGT (Ticket Granting Ticket) al veya cache'den getir.
        
        TGT yaklaşık 2 saat geçerli.
        """
        # Cache'den kontrol
        if not force_refresh:
            cached_tgt = self._get_cached_tgt()
            if cached_tgt:
                return cached_tgt
        
        if not self.username or not self.password:
            logger.warning("EPİAŞ credentials not configured (EPIAS_USERNAME/EPIAS_PASSWORD)")
            return None
        
        try:
            response = requests.post(
                self.AUTH_URL,
                headers={
                    "Content-Type": "application/x-www-form-urlencoded",
                    "Accept": "text/plain",
                },
                data={
                    "username": self.username,
                    "password": self.password,
                },
                timeout=15
            )
            
            if response.status_code != 201:
                logger.error(f"EPİAŞ TGT alınamadı: {response.status_code} - {response.text[:200]}")
                return None
            
            tgt = response.text.strip()
            self._cache_tgt(tgt)
            logger.info("EPİAŞ TGT başarıyla alındı")
            return tgt
            
        except requests.exceptions.RequestException as e:
            logger.error(f"EPİAŞ Auth Hatası: {str(e)}")
            return None
    
    def _get_cached_tgt(self) -> Optional[str]:
        """Cache'den TGT getir."""
        # Redis varsa
        if self._redis:
            try:
                cached = self._redis.get(self.TGT_CACHE_KEY)
                if cached:
                    return cached.decode('utf-8')
            except Exception:
                pass
        
        # Memory cache
        if self._tgt and self._tgt_expires_at:
            if datetime.utcnow() < self._tgt_expires_at:
                return self._tgt
        
        return None
    
    def _cache_tgt(self, tgt: str):
        """TGT'yi cache'le."""
        self._tgt = tgt
        self._tgt_expires_at = datetime.utcnow() + timedelta(seconds=self.TGT_EXPIRY_SECONDS)
        
        # Redis varsa
        if self._redis:
            try:
                self._redis.setex(self.TGT_CACHE_KEY, self.TGT_EXPIRY_SECONDS, tgt)
            except Exception:
                pass
    
    def get_mcp(self, date_obj: datetime = None, retry_count: int = 2) -> Optional[List[Dict[str, Any]]]:
        """
        MCP (Market Clearing Price) / PTF (Piyasa Takas Fiyatı) verilerini çeker.
        
        Endpoint: POST /v1/markets/dam/data/mcp
        
        Args:
            date_obj: Tarih (varsayılan: bugün)
            retry_count: Hata durumunda tekrar deneme sayısı
        
        Returns:
            Fiyat listesi veya None (hata durumunda)
        """
        if not date_obj:
            date_obj = datetime.now()
        
        date_str = date_obj.strftime("%Y-%m-%d")
        
        # Önce TGT ile dene
        tgt = self.get_tgt()
        if tgt:
            result = self._fetch_mcp_with_tgt(date_str, tgt)
            if result is not None:
                return result
            # TGT geçersiz olabilir, yenile ve tekrar dene
            tgt = self.get_tgt(force_refresh=True)
            if tgt:
                result = self._fetch_mcp_with_tgt(date_str, tgt)
                if result is not None:
                    return result
        
        # TGT başarısız, public endpoint dene
        for attempt in range(retry_count + 1):
            result = self._get_mcp_public(date_obj)
            if result is not None:
                return result
            if attempt < retry_count:
                import time
                time.sleep(2 ** attempt)  # Exponential backoff
        
        logger.error(f"EPİAŞ MCP verisi alınamadı: {date_str}")
        return None
    
    def _fetch_mcp_with_tgt(self, date_str: str, tgt: str) -> Optional[List[Dict[str, Any]]]:
        """TGT ile MCP verisi çek."""
        url = f"{self.BASE_URL}/markets/dam/data/mcp"
        headers = {**self.HEADERS, "TGT": tgt}
        payload = {
            "startDate": f"{date_str}T00:00:00+03:00",
            "endDate": f"{date_str}T23:59:59+03:00"
        }
        
        try:
            response = requests.post(url, json=payload, headers=headers, timeout=20)
            response.raise_for_status()
            
            data = response.json()
            if "items" in data:
                items = self._normalize_mcp_data(data["items"])
                logger.info(f"EPİAŞ MCP verisi alındı: {date_str} ({len(items)} kayıt)")
                return items
            
            return []
            
        except requests.exceptions.RequestException as e:
            logger.warning(f"EPİAŞ MCP (TGT) Hatası: {str(e)}")
            return None
        except ValueError as e:
            logger.warning(f"EPİAŞ MCP JSON parse hatası: {str(e)}")
            return None
    
    def _get_mcp_public(self, date_obj: datetime) -> Optional[List[Dict[str, Any]]]:
        """
        Public endpoint ile PTF çek (TGT gerektirmez, bazı veriler kısıtlı olabilir).
        """
        date_str = date_obj.strftime("%Y-%m-%d")
        url = f"{self.BASE_URL}/markets/dam/data/mcp"
        
        payload = {
            "startDate": f"{date_str}T00:00:00+03:00",
            "endDate": f"{date_str}T23:59:59+03:00"
        }
        
        try:
            response = requests.post(url, json=payload, headers=self.HEADERS, timeout=20)
            response.raise_for_status()
            
            data = response.json()
            if "items" in data:
                items = self._normalize_mcp_data(data["items"])
                logger.info(f"EPİAŞ MCP (public) verisi alındı: {date_str} ({len(items)} kayıt)")
                return items
            
            return []
            
        except requests.exceptions.RequestException as e:
            logger.warning(f"EPİAŞ Public MCP Hatası: {str(e)}")
            return None
        except ValueError as e:
            logger.warning(f"EPİAŞ Public MCP JSON parse hatası: {str(e)}")
            return None
    
    def _normalize_mcp_data(self, items: List[Dict]) -> List[Dict[str, Any]]:
        """
        EPİAŞ verisini normalize et.
        
        Gelen format: {"date": "2024-01-15T14:00:00+03:00", "price": 2450.50}
        """
        normalized = []
        
        for item in items:
            try:
                dt = datetime.fromisoformat(item["date"].replace("Z", "+00:00"))
                price_mwh = float(item.get("price", 0))
                
                # TL/MWh -> TL/kWh dönüşümü
                price_kwh = price_mwh / 1000
                
                normalized.append({
                    "time": dt,
                    "hour": dt.hour,
                    "ptf": price_mwh,           # TL/MWh (orijinal)
                    "price": price_kwh,         # TL/kWh (kullanıcı dostu)
                    "currency": "TRY",
                    "region": "TR",
                    "market_type": "PTF"
                })
            except (ValueError, KeyError) as e:
                logger.warning(f"EPİAŞ veri parse hatası: {e}")
                continue
        
        return normalized
    
    def get_realtime_consumption(self, start_date: datetime, end_date: datetime) -> Optional[List[Dict]]:
        """
        Gerçek zamanlı tüketim verilerini çeker.
        
        Endpoint: POST /v1/consumption/data/realtime-consumption
        Not: Veri 2 saat gecikmeli yayınlanır.
        """
        tgt = self.get_tgt()
        if not tgt:
            logger.warning("TGT gerekli: realtime-consumption")
            return None
        
        url = f"{self.BASE_URL}/consumption/data/realtime-consumption"
        
        headers = {**self.HEADERS, "TGT": tgt}
        payload = {
            "startDate": start_date.strftime("%Y-%m-%dT%H:%M:%S+03:00"),
            "endDate": end_date.strftime("%Y-%m-%dT%H:%M:%S+03:00")
        }
        
        try:
            response = requests.post(url, json=payload, headers=headers, timeout=15)
            response.raise_for_status()
            return response.json().get("items", [])
            
        except requests.exceptions.RequestException as e:
            logger.error(f"EPİAŞ Consumption Hatası: {str(e)}")
            return None
    
    def get_smp(self, date_obj: datetime = None) -> Optional[List[Dict[str, Any]]]:
        """
        SMP (System Marginal Price) / SMF (Sistem Marjinal Fiyatı) verilerini çeker.
        
        Endpoint: POST /v1/markets/bpm/data/smp
        """
        if not date_obj:
            date_obj = datetime.now()
        
        tgt = self.get_tgt()
        date_str = date_obj.strftime("%Y-%m-%d")
        url = f"{self.BASE_URL}/markets/bpm/data/smp"
        
        headers = {**self.HEADERS}
        if tgt:
            headers["TGT"] = tgt
        
        payload = {
            "startDate": f"{date_str}T00:00:00+03:00",
            "endDate": f"{date_str}T23:59:59+03:00"
        }
        
        try:
            response = requests.post(url, json=payload, headers=headers, timeout=15)
            response.raise_for_status()
            
            data = response.json()
            if "items" in data:
                return self._normalize_smp_data(data["items"])
            
            return []
            
        except requests.exceptions.RequestException as e:
            logger.error(f"EPİAŞ SMP Hatası: {str(e)}")
            return None
    
    def _normalize_smp_data(self, items: List[Dict]) -> List[Dict[str, Any]]:
        """SMF verisini normalize et."""
        normalized = []
        
        for item in items:
            try:
                dt = datetime.fromisoformat(item["date"].replace("Z", "+00:00"))
                
                # Pozitif ve negatif dengesizlik fiyatları
                smp_up = float(item.get("smpDirection", {}).get("upRegulationPrice", 0))
                smp_down = float(item.get("smpDirection", {}).get("downRegulationPrice", 0))
                
                normalized.append({
                    "time": dt,
                    "hour": dt.hour,
                    "smp_up": smp_up,
                    "smp_down": smp_down,
                    "currency": "TRY",
                    "market_type": "SMF"
                })
            except (ValueError, KeyError) as e:
                logger.warning(f"EPİAŞ SMP parse hatası: {e}")
                continue
        
        return normalized


# Singleton instance
epias_service = EpiasService()
