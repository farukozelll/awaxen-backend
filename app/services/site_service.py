"""Site (Saha) iş mantığı."""
from typing import Any, Dict

from .. import db
from ..models import Site, SiteType
from .helpers import _resolve_metadata


def create_site_logic(user_id: int, data: Dict[str, Any]) -> Site:
    """Yeni saha oluştur (tipli ve boyutlu)."""
    if not data:
        raise ValueError("Saha verisi gereklidir.")

    name = data.get("name")
    if not name:
        raise ValueError("Saha adı zorunludur.")

    site_type = data.get("site_type", SiteType.GREENHOUSE.value)
    dimensions = data.get("dimensions", {})

    # Validasyon: Sera seçildiyse boyut girmek zorunlu olsun
    if site_type == SiteType.GREENHOUSE.value:
        if dimensions and ("rows" in dimensions or "columns" in dimensions):
            if "rows" not in dimensions or "columns" not in dimensions:
                raise ValueError("Sera tipi için hem satır hem sütun sayısı girilmelidir.")

    site = Site(
        user_id=user_id,
        name=name,
        city=data.get("city"),
        district=data.get("district"),
        location=data.get("location"),
        address=data.get("address"),
        latitude=data.get("latitude"),
        longitude=data.get("longitude"),
        site_type=site_type,
        dimensions=dimensions,
        image_url=data.get("image_url"),
        metadata_info=_resolve_metadata(data),
    )
    db.session.add(site)
    db.session.commit()
    return site


def update_site_logic(user_id: int, site_id: int, data: Dict[str, Any]) -> Site:
    """Saha bilgilerini güncelle."""
    site = Site.query.filter_by(id=site_id, user_id=user_id).first()
    if not site:
        raise ValueError("Saha bulunamadı veya yetkiniz yok.")

    if not data:
        return site

    updatable_fields = [
        "name", "city", "district", "location", "address",
        "latitude", "longitude", "site_type", "dimensions", "image_url"
    ]

    for field in updatable_fields:
        if field in data and data[field] is not None:
            setattr(site, field, data[field])

    if "metadata" in data or "metadata_info" in data:
        site.metadata_info = _resolve_metadata(data)

    db.session.commit()
    return site
