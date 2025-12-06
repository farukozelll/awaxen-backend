"""
EPİAŞ Piyasa Fiyatları Task'ları.

Saatlik olarak EPİAŞ Şeffaf Platform'dan PTF/SMF verilerini çeker.
"""
from datetime import datetime, timedelta
import requests
import logging

from app.extensions import celery, db
from app.models import MarketPrice

logger = logging.getLogger(__name__)


@celery.task(bind=True, max_retries=3)
def fetch_epias_prices(self):
    """
    EPİAŞ'tan günlük elektrik fiyatlarını çek.
    
    Celery Beat tarafından her saat başı çağrılır.
    Tüm organizasyonlar bu global tablodan beslenir (Singleton).
    """
    from app.services.epias_service import epias_service
    
    try:
        today = datetime.now()
        
        # EPİAŞ servisinden PTF verilerini çek
        prices = epias_service.get_mcp(today)
        
        if prices is None:
            # API hatası, mock data kullan
            logger.warning("EPİAŞ API hatası, mock data kullanılıyor")
            prices = _generate_mock_prices(today.strftime("%Y-%m-%d"))
        
        saved_count = 0
        for price_data in prices:
            time_val = price_data.get('time')
            if isinstance(time_val, str):
                time_val = datetime.fromisoformat(time_val.replace("Z", "+00:00"))
            
            # Upsert: Varsa güncelle, yoksa ekle
            existing = MarketPrice.query.filter_by(time=time_val).first()
            
            if existing:
                existing.price = price_data.get('price', price_data.get('ptf', 0) / 1000)
                existing.ptf = price_data.get('ptf')
                existing.smf = price_data.get('smf')
            else:
                new_price = MarketPrice(
                    time=time_val,
                    price=price_data.get('price', price_data.get('ptf', 0) / 1000),
                    ptf=price_data.get('ptf'),
                    smf=price_data.get('smf'),
                    currency='TRY',
                    region='TR'
                )
                db.session.add(new_price)
                saved_count += 1
        
        db.session.commit()
        
        logger.info(f"EPİAŞ fiyatları güncellendi: {saved_count} yeni kayıt")
        
        return {
            'status': 'success',
            'date': today.strftime("%Y-%m-%d"),
            'new_records': saved_count,
            'message': f'EPİAŞ fiyatları güncellendi: {saved_count} yeni kayıt'
        }
        
    except requests.RequestException as e:
        logger.error(f"EPİAŞ request hatası: {e}")
        self.retry(exc=e, countdown=60 * (2 ** self.request.retries))
    except Exception as e:
        logger.error(f"EPİAŞ task hatası: {e}")
        db.session.rollback()
        return {
            'status': 'error',
            'error': str(e)
        }


@celery.task(bind=True, max_retries=3)
def fetch_tomorrow_prices(self):
    """
    Yarının fiyatlarını çek (saat 14:00'ten sonra açıklanır).
    
    Celery Beat tarafından her gün 14:30'da çağrılır.
    """
    from app.services.epias_service import epias_service
    
    try:
        tomorrow = datetime.now() + timedelta(days=1)
        
        prices = epias_service.get_mcp(tomorrow)
        
        if not prices:
            logger.info("Yarının fiyatları henüz açıklanmamış")
            return {'status': 'pending', 'message': 'Yarının fiyatları henüz açıklanmamış'}
        
        saved_count = 0
        for price_data in prices:
            time_val = price_data.get('time')
            if isinstance(time_val, str):
                time_val = datetime.fromisoformat(time_val.replace("Z", "+00:00"))
            
            existing = MarketPrice.query.filter_by(time=time_val).first()
            
            if not existing:
                new_price = MarketPrice(
                    time=time_val,
                    price=price_data.get('price', price_data.get('ptf', 0) / 1000),
                    ptf=price_data.get('ptf'),
                    smf=price_data.get('smf'),
                    currency='TRY',
                    region='TR'
                )
                db.session.add(new_price)
                saved_count += 1
        
        db.session.commit()
        
        logger.info(f"Yarının fiyatları eklendi: {saved_count} kayıt")
        
        return {
            'status': 'success',
            'date': tomorrow.strftime("%Y-%m-%d"),
            'new_records': saved_count
        }
        
    except Exception as e:
        logger.error(f"Yarın fiyat task hatası: {e}")
        db.session.rollback()
        return {'status': 'error', 'error': str(e)}


def _generate_mock_prices(date_str: str) -> list:
    """
    Test için mock fiyat verisi üret.
    
    Gerçek EPİAŞ entegrasyonu yapıldığında bu fonksiyon kaldırılacak.
    """
    import random
    from datetime import datetime
    
    prices = []
    base_date = datetime.strptime(date_str, "%Y-%m-%d")
    
    # Saatlik fiyatlar (0-23)
    for hour in range(24):
        time = base_date.replace(hour=hour, minute=0, second=0, microsecond=0)
        
        # Gerçekçi fiyat simülasyonu
        # Gece (22-06): Düşük fiyat
        # Gündüz (06-17): Orta fiyat  
        # Puant (17-22): Yüksek fiyat
        if 22 <= hour or hour < 6:
            base_price = random.uniform(1.0, 1.8)  # Gece
        elif 17 <= hour < 22:
            base_price = random.uniform(3.5, 5.5)  # Puant
        else:
            base_price = random.uniform(2.0, 3.0)  # Gündüz
        
        prices.append({
            'time': time,
            'price': round(base_price, 2),
            'ptf': round(base_price * 1000, 2),  # TL/MWh
            'smf': round(base_price * 1000 * 1.05, 2),  # SMF genelde PTF'den biraz yüksek
        })
    
    return prices


@celery.task
def cleanup_old_prices(days_to_keep: int = 90):
    """
    Eski fiyat verilerini temizle.
    
    TimescaleDB retention policy yerine manuel temizlik.
    """
    cutoff_date = datetime.now() - timedelta(days=days_to_keep)
    
    deleted = MarketPrice.query.filter(MarketPrice.time < cutoff_date).delete()
    db.session.commit()
    
    return {
        'status': 'success',
        'deleted_records': deleted,
        'cutoff_date': cutoff_date.isoformat()
    }
