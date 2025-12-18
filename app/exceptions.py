"""
Awaxen Backend - Custom Exceptions ve Error Handling.

Tüm özel exception sınıfları ve error response helper'ları burada tanımlanır.
"""
from typing import Any, Dict, Optional, Tuple
from flask import jsonify, Response

from app.constants import HttpStatus, ErrorCode


# ==========================================
# CUSTOM EXCEPTIONS
# ==========================================

class AwaxenException(Exception):
    """Base exception for all Awaxen errors."""
    
    def __init__(
        self,
        message: str,
        code: str = ErrorCode.INTERNAL_SERVER_ERROR,
        status_code: int = HttpStatus.INTERNAL_SERVER_ERROR,
        details: Optional[Dict[str, Any]] = None
    ):
        super().__init__(message)
        self.message = message
        self.code = code
        self.status_code = status_code
        self.details = details or {}
    
    def to_dict(self) -> Dict[str, Any]:
        """Exception'ı JSON-serializable dict'e çevir."""
        result = {
            "error": self.message,
            "code": self.code,
        }
        if self.details:
            result["details"] = self.details
        return result
    
    def to_response(self) -> Tuple[Response, int]:
        """Flask response tuple döndür."""
        return jsonify(self.to_dict()), self.status_code


class ValidationError(AwaxenException):
    """Input validation hatası."""
    
    def __init__(self, message: str, field: Optional[str] = None, details: Optional[Dict] = None):
        super().__init__(
            message=message,
            code=ErrorCode.VALIDATION_ERROR,
            status_code=HttpStatus.BAD_REQUEST,
            details=details
        )
        self.field = field
        if field:
            self.details["field"] = field


class AuthenticationError(AwaxenException):
    """Kimlik doğrulama hatası."""
    
    def __init__(self, message: str = "Authentication required", code: str = ErrorCode.INVALID_TOKEN):
        super().__init__(
            message=message,
            code=code,
            status_code=HttpStatus.UNAUTHORIZED
        )


class AuthorizationError(AwaxenException):
    """Yetkilendirme hatası."""
    
    def __init__(
        self,
        message: str = "You don't have permission to perform this action",
        required_permissions: Optional[list] = None,
        user_permissions: Optional[list] = None
    ):
        details = {}
        if required_permissions:
            details["required_permissions"] = required_permissions
        if user_permissions:
            details["your_permissions"] = user_permissions
        
        super().__init__(
            message=message,
            code=ErrorCode.FORBIDDEN,
            status_code=HttpStatus.FORBIDDEN,
            details=details
        )


class ResourceNotFoundError(AwaxenException):
    """Kaynak bulunamadı hatası."""
    
    def __init__(self, resource_type: str, resource_id: Optional[str] = None):
        message = f"{resource_type} not found"
        if resource_id:
            message = f"{resource_type} with id '{resource_id}' not found"
        
        super().__init__(
            message=message,
            code=ErrorCode.RESOURCE_NOT_FOUND,
            status_code=HttpStatus.NOT_FOUND,
            details={"resource_type": resource_type, "resource_id": resource_id}
        )


class ResourceConflictError(AwaxenException):
    """Kaynak çakışması hatası (duplicate, already exists vb.)."""
    
    def __init__(self, message: str, resource_type: Optional[str] = None):
        super().__init__(
            message=message,
            code=ErrorCode.RESOURCE_CONFLICT,
            status_code=HttpStatus.CONFLICT,
            details={"resource_type": resource_type} if resource_type else {}
        )


class DatabaseError(AwaxenException):
    """Veritabanı hatası."""
    
    def __init__(self, message: str = "Database operation failed", original_error: Optional[Exception] = None):
        details = {}
        if original_error:
            details["original_error"] = str(original_error)
        
        super().__init__(
            message=message,
            code=ErrorCode.DATABASE_ERROR,
            status_code=HttpStatus.INTERNAL_SERVER_ERROR,
            details=details
        )


class ExternalServiceError(AwaxenException):
    """Harici servis hatası (Shelly, EPİAŞ vb.)."""
    
    def __init__(self, service_name: str, message: str, original_error: Optional[Exception] = None):
        details = {"service": service_name}
        if original_error:
            details["original_error"] = str(original_error)
        
        super().__init__(
            message=f"{service_name} error: {message}",
            code=ErrorCode.EXTERNAL_SERVICE_ERROR,
            status_code=HttpStatus.SERVICE_UNAVAILABLE,
            details=details
        )


class RateLimitError(AwaxenException):
    """Rate limit aşıldı hatası."""
    
    def __init__(self, retry_after: Optional[int] = None):
        details = {}
        if retry_after:
            details["retry_after_seconds"] = retry_after
        
        super().__init__(
            message="Rate limit exceeded. Please try again later.",
            code=ErrorCode.RATE_LIMIT_EXCEEDED,
            status_code=HttpStatus.TOO_MANY_REQUESTS,
            details=details
        )


# ==========================================
# RESPONSE HELPERS
# ==========================================

def success_response(
    data: Any = None,
    message: Optional[str] = None,
    status_code: int = HttpStatus.OK
) -> Tuple[Response, int]:
    """
    Başarılı response oluştur.
    
    Args:
        data: Response data
        message: Opsiyonel mesaj
        status_code: HTTP status code
    
    Returns:
        Flask response tuple
    """
    response = {}
    
    if data is not None:
        if isinstance(data, dict) and "data" in data:
            response = data
        else:
            response["data"] = data
    
    if message:
        response["message"] = message
    
    return jsonify(response), status_code


def error_response(
    message: str,
    code: str = ErrorCode.INVALID_INPUT,
    status_code: int = HttpStatus.BAD_REQUEST,
    details: Optional[Dict[str, Any]] = None
) -> Tuple[Response, int]:
    """
    Hata response'u oluştur.
    
    Args:
        message: Hata mesajı
        code: Hata kodu
        status_code: HTTP status code
        details: Ek detaylar
    
    Returns:
        Flask response tuple
    """
    response = {
        "error": message,
        "code": code,
    }
    
    if details:
        response["details"] = details
    
    return jsonify(response), status_code


def paginated_response(
    items: list,
    total: int,
    page: int,
    page_size: int,
    status_code: int = HttpStatus.OK
) -> Tuple[Response, int]:
    """
    Sayfalanmış response oluştur.
    
    Args:
        items: Sayfa içeriği
        total: Toplam kayıt sayısı
        page: Mevcut sayfa
        page_size: Sayfa boyutu
        status_code: HTTP status code
    
    Returns:
        Flask response tuple
    """
    total_pages = (total + page_size - 1) // page_size if page_size > 0 else 0
    
    response = {
        "data": items,
        "pagination": {
            "page": page,
            "pageSize": page_size,
            "total": total,
            "totalPages": total_pages,
            "hasNext": page < total_pages,
            "hasPrev": page > 1,
        }
    }
    
    return jsonify(response), status_code


def created_response(
    data: Any,
    message: str = "Resource created successfully"
) -> Tuple[Response, int]:
    """201 Created response."""
    return success_response(data=data, message=message, status_code=HttpStatus.CREATED)


def no_content_response() -> Tuple[Response, int]:
    """204 No Content response."""
    return "", HttpStatus.NO_CONTENT


def unauthorized_response(message: str = "Unauthorized") -> Tuple[Response, int]:
    """401 Unauthorized response."""
    return error_response(message, ErrorCode.INVALID_TOKEN, HttpStatus.UNAUTHORIZED)


def forbidden_response(message: str = "Forbidden") -> Tuple[Response, int]:
    """403 Forbidden response."""
    return error_response(message, ErrorCode.FORBIDDEN, HttpStatus.FORBIDDEN)


def not_found_response(resource: str = "Resource") -> Tuple[Response, int]:
    """404 Not Found response."""
    return error_response(f"{resource} not found", ErrorCode.RESOURCE_NOT_FOUND, HttpStatus.NOT_FOUND)
