"""Tarife iş mantığı."""
from datetime import datetime
from typing import Any, Dict

from .. import db
from ..models import Tariff, TariffType


def create_tariff_logic(user_id: int, data: Dict[str, Any]) -> Tariff:
    """Yeni tarife oluştur."""
    name = data.get("name", "").strip()
    if not name:
        raise ValueError("Tarife adı zorunludur.")

    periods = data.get("periods")
    if not periods:
        raise ValueError("Tarife dilimleri (periods) zorunludur.")

    tariff = Tariff(
        user_id=user_id,
        name=name,
        tariff_type=data.get("tariff_type", TariffType.THREE_TIME.value),
        periods=periods,
        currency=data.get("currency", "TRY"),
        is_active=data.get("is_active", True),
    )

    db.session.add(tariff)
    db.session.commit()
    return tariff


def update_tariff_logic(user_id: int, tariff_id: int, data: Dict[str, Any]) -> Tariff:
    """Tarife güncelle."""
    tariff = Tariff.query.filter_by(id=tariff_id, user_id=user_id).first()
    if not tariff:
        raise ValueError("Tarife bulunamadı veya yetkiniz yok.")

    if "name" in data:
        tariff.name = data["name"]
    if "tariff_type" in data:
        tariff.tariff_type = data["tariff_type"]
    if "periods" in data:
        tariff.periods = data["periods"]
    if "currency" in data:
        tariff.currency = data["currency"]
    if "is_active" in data:
        tariff.is_active = data["is_active"]

    db.session.commit()
    return tariff


def delete_tariff_logic(user_id: int, tariff_id: int) -> None:
    """Tarife sil."""
    tariff = Tariff.query.filter_by(id=tariff_id, user_id=user_id).first()
    if not tariff:
        raise ValueError("Tarife bulunamadı veya yetkiniz yok.")

    db.session.delete(tariff)
    db.session.commit()


def get_current_tariff_price(user_id: int, tariff_id: int) -> Dict[str, Any]:
    """Şu anki tarife fiyatını hesapla."""
    tariff = Tariff.query.filter_by(id=tariff_id, user_id=user_id, is_active=True).first()
    if not tariff:
        raise ValueError("Aktif tarife bulunamadı.")

    now = datetime.now()
    current_time = now.strftime("%H:%M")

    current_period = None
    current_price = None

    for period_key, period_data in tariff.periods.items():
        start = period_data.get("start", "00:00")
        end = period_data.get("end", "23:59")

        # Gece geçişi kontrolü (22:00 - 06:00 gibi)
        if start > end:
            if current_time >= start or current_time < end:
                current_period = period_key
                current_price = period_data.get("price")
                break
        else:
            if start <= current_time < end:
                current_period = period_key
                current_price = period_data.get("price")
                break

    return {
        "tariff_id": tariff.id,
        "tariff_name": tariff.name,
        "current_period": current_period,
        "current_price": current_price,
        "currency": tariff.currency,
        "checked_at": now.isoformat(),
    }
