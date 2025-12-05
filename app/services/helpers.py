"""Ortak yardımcı fonksiyonlar."""
from typing import Any, Dict


def _resolve_metadata(payload: Dict[str, Any]) -> Dict[str, Any]:
    """Payload'dan metadata bilgisini çıkar."""
    metadata = payload.get("metadata_info")
    if metadata is None:
        metadata = payload.get("metadata")
    return metadata or {}
