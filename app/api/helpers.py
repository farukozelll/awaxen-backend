import re
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

from flask import g, request

from app.extensions import db
from app.models import User, Organization
from app.auth import get_current_user_id

# Yapı: { org_id: { "data": {...}, "timestamp": 1701234567 } }
weather_cache: Dict[str, Dict[str, Any]] = {}
CACHE_TIMEOUT = 900  # 15 Dakika (Saniye cinsinden)


def get_current_user() -> Optional[User]:
    """Token'dan gelen kullanıcıyı DB'de bul veya oluştur."""
    auth0_id = get_current_user_id()
    if not auth0_id:
        return None

    user = User.query.filter_by(auth0_id=auth0_id).first()
    if not user:
        token_info = g.current_user
        
        # Yeni kullanıcı için organizasyon oluştur
        org = Organization(
            name=f"{token_info.get('name', 'Yeni Kullanıcı')}'in Evi",
            slug=f"user-{auth0_id[:8]}",
            type="home",
        )
        db.session.add(org)
        db.session.flush()
        
        user = User(
            organization_id=org.id,
            auth0_id=auth0_id,
            email=token_info.get("email", f"{auth0_id}@unknown.com"),
            full_name=token_info.get("name", "Yeni Kullanıcı"),
            role="admin",
        )
        db.session.add(user)
        db.session.commit()
    return user


# Geriye uyumluluk için alias
get_or_create_user = get_current_user


def parse_iso_datetime(value: Optional[str]):
    if not value:
        return None
    try:
        cleaned = value.replace("Z", "+00:00") if value.endswith("Z") else value
        return datetime.fromisoformat(cleaned)
    except ValueError:
        return None


def get_pagination_params() -> Tuple[int, int]:
    page = request.args.get("page", 1, type=int)
    page_size = request.args.get("pageSize", 20, type=int)
    page_size = min(page_size, 100)
    return page, page_size


def get_filter_params() -> Dict[str, str]:
    return {
        "search": request.args.get("search", "", type=str).strip(),
        "sort_by": request.args.get("sortBy", "id", type=str),
        "sort_order": request.args.get("sortOrder", "asc", type=str).lower(),
    }


def paginate_response(items: List[Any], total: int, page: int, page_size: int) -> Dict[str, Any]:
    return {
        "data": items,
        "pagination": {
            "page": page,
            "pageSize": page_size,
            "total": total,
            "totalPages": (total + page_size - 1) // page_size if page_size > 0 else 0,
        },
    }


def apply_sorting(query, model, sort_by: str, sort_order: str, allowed_fields: List[str]):
    if sort_by not in allowed_fields:
        sort_by = "id"

    column = getattr(model, sort_by, None)
    if column is None:
        column = model.id

    if sort_order == "desc":
        return query.order_by(column.desc())
    return query.order_by(column.asc())


def parse_decimal(value: Optional[str]) -> Optional[float]:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        cleaned = value.strip().replace("°", "")
        if not cleaned:
            return None
        cleaned = cleaned.replace(",", ".")
        try:
            return float(cleaned)
        except ValueError:
            return None
    return None


def resolve_organization_coordinates(org: Organization) -> Tuple[Optional[float], Optional[float]]:
    """Organization'ın location JSONB'sinden koordinatları çıkar."""
    if not org.location:
        return None, None
    
    lat = org.location.get("latitude") or org.location.get("lat")
    lon = org.location.get("longitude") or org.location.get("lon") or org.location.get("lng")
    
    if lat is not None and lon is not None:
        return parse_decimal(str(lat)), parse_decimal(str(lon))
    
    return None, None
