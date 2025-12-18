"""
EPİAŞ Piyasa Fiyatları Task'ları.

Saatlik olarak EPİAŞ Şeffaf Platform'dan PTF/SMF verilerini çeker.
Real-time fiyat güncellemeleri Socket.IO üzerinden yayınlanır.
"""
from datetime import datetime, timedelta
import requests
import logging

from app.extensions import celery, db
from app.models import MarketPrice
from app.realtime import broadcast_price_update, redis_pubsub

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
            # API hatası - boş liste ile devam et, mock data kullanma
            logger.warning("EPİAŞ API hatası - veri alınamadı")
            return {
                'status': 'warning',
                'date': today.strftime("%Y-%m-%d"),
                'message': 'EPİAŞ API yanıt vermedi, veri alınamadı'
            }
        
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
        
        # Real-time: Güncel saatin fiyatını WebSocket üzerinden yayınla
        current_hour = today.hour
        current_price = next(
            (p for p in prices if datetime.fromisoformat(
                p.get('time', '').replace("Z", "+00:00")
            ).hour == current_hour),
            None
        )
        if current_price:
            broadcast_price_update({
                "price": current_price.get('price', current_price.get('ptf', 0) / 1000),
                "ptf": current_price.get('ptf'),
                "smf": current_price.get('smf'),
                "hour": current_hour,
                "date": today.strftime("%Y-%m-%d"),
                "currency": "TRY"
            })
        
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


# Mock data fonksiyonu kaldırıldı - Sistem tamamen dinamik çalışıyor
# EPİAŞ API'den veri alınamazsa boş yanıt dönülür


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
