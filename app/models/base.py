"""
Awaxen Models - Base Mixins.

Ortak model davranışları için mixin sınıfları.
Production-ready: Soft delete, timestamps, serialization.
"""
from datetime import datetime, timezone
from typing import Any, Dict, Optional
import json

from sqlalchemy import Column, DateTime, Boolean, event
from sqlalchemy.orm import validates

from app.extensions import db


def utcnow() -> datetime:
    """Timezone-aware UTC datetime döndür."""
    return datetime.now(timezone.utc)


class TimestampMixin:
    """
    Timestamp mixin - created_at ve updated_at alanları ekler.
    
    Tüm modellerde kullanılmalıdır.
    """
    created_at = Column(DateTime(timezone=True), default=utcnow, nullable=False, index=True)
    updated_at = Column(DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False)


class SoftDeleteMixin:
    """
    Soft delete mixin - is_active ve deleted_at alanları ekler.
    
    Kayıtlar silinmez, is_active=False ve deleted_at set edilir.
    Yanlışlıkla silinen veriyi kurtarmak için deleted_at kullanılır.
    """
    is_active = Column(Boolean, default=True, nullable=False, index=True)
    deleted_at = Column(DateTime(timezone=True), nullable=True, index=True)
    
    def soft_delete(self) -> None:
        """Kaydı soft delete yap."""
        self.is_active = False
        self.deleted_at = utcnow()
    
    def restore(self) -> None:
        """Soft delete yapılmış kaydı geri getir."""
        self.is_active = True
        self.deleted_at = None
    
    @property
    def is_deleted(self) -> bool:
        """Kayıt silinmiş mi?"""
        return self.deleted_at is not None or not self.is_active


class JSONBValidatorMixin:
    """
    JSONB alanları için validasyon mixin'i.
    
    Alt sınıflar _jsonb_fields dict'ini tanımlayarak
    hangi alanların hangi şemaya uyması gerektiğini belirtebilir.
    """
    # Alt sınıflar override edebilir: {'field_name': {'required_keys': [...], 'allowed_keys': [...]}}
    _jsonb_schema: Dict[str, Dict] = {}
    
    def validate_jsonb_field(self, field_name: str, value: Any) -> Any:
        """
        JSONB alanını validate et.
        
        Args:
            field_name: Alan adı
            value: Değer
        
        Returns:
            Validate edilmiş değer
        
        Raises:
            ValueError: Geçersiz değer
        """
        if value is None:
            return {}
        
        if isinstance(value, str):
            try:
                value = json.loads(value)
            except json.JSONDecodeError:
                raise ValueError(f"{field_name} must be valid JSON")
        
        if not isinstance(value, dict):
            raise ValueError(f"{field_name} must be a JSON object")
        
        # Şema kontrolü
        if field_name in self._jsonb_schema:
            schema = self._jsonb_schema[field_name]
            required_keys = schema.get('required_keys', [])
            allowed_keys = schema.get('allowed_keys', [])
            
            # Required keys kontrolü
            for key in required_keys:
                if key not in value:
                    raise ValueError(f"{field_name} must contain '{key}'")
            
            # Allowed keys kontrolü (eğer tanımlıysa)
            if allowed_keys:
                for key in value.keys():
                    if key not in allowed_keys:
                        raise ValueError(f"{field_name} contains invalid key '{key}'")
        
        return value


class SerializerMixin:
    """
    Serializer mixin - to_dict metodu ekler.
    
    Model'i JSON-serializable dict'e çevirir.
    """
    
    # Alt sınıflar bu listeyi override edebilir
    _serializable_fields: list = []
    _exclude_fields: list = []
    
    def to_dict(self, include_relationships: bool = False) -> Dict[str, Any]:
        """
        Model'i dict'e çevir.
        
        Args:
            include_relationships: İlişkili modelleri de dahil et
        
        Returns:
            JSON-serializable dict
        """
        result = {}
        
        for column in self.__table__.columns:
            if column.name in self._exclude_fields:
                continue
            
            value = getattr(self, column.name)
            
            # UUID'leri string'e çevir
            if hasattr(value, 'hex'):
                value = str(value)
            # Datetime'ları ISO format'a çevir
            elif isinstance(value, datetime):
                value = value.isoformat()
            
            result[column.name] = value
        
        return result
