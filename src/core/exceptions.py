"""
Global Exception Handling
Custom exceptions and FastAPI exception handlers.

Error Response Format (RFC 7807 inspired):
{
    "error": {
        "code": "ERROR_CODE",
        "message": "Human readable message",
        "details": {},
        "request_id": "uuid",
        "timestamp": "ISO8601"
    }
}
"""
import uuid
from datetime import datetime, timezone
from typing import Any

from fastapi import HTTPException, Request, status
from fastapi.responses import ORJSONResponse

from src.core.logging import get_logger

logger = get_logger(__name__)


def _get_request_id(request: Request) -> str:
    """Get or generate request ID for tracing."""
    return request.headers.get("X-Request-ID", str(uuid.uuid4()))


class AwaxenException(Exception):
    """Base exception for Awaxen application."""
    
    def __init__(
        self,
        message: str = "An error occurred",
        code: str = "INTERNAL_ERROR",
        status_code: int = status.HTTP_500_INTERNAL_SERVER_ERROR,
        details: dict[str, Any] | None = None,
    ):
        self.message = message
        self.code = code
        self.status_code = status_code
        self.details = details or {}
        super().__init__(self.message)


class NotFoundError(AwaxenException):
    """Resource not found."""
    
    def __init__(self, resource: str, identifier: Any):
        super().__init__(
            message=f"{resource} with identifier '{identifier}' not found",
            code="NOT_FOUND",
            status_code=status.HTTP_404_NOT_FOUND,
            details={"resource": resource, "identifier": str(identifier)},
        )


class UnauthorizedError(AwaxenException):
    """Authentication required."""
    
    def __init__(self, message: str = "Authentication required"):
        super().__init__(
            message=message,
            code="UNAUTHORIZED",
            status_code=status.HTTP_401_UNAUTHORIZED,
        )


class ForbiddenError(AwaxenException):
    """Permission denied."""
    
    def __init__(self, message: str = "Permission denied"):
        super().__init__(
            message=message,
            code="FORBIDDEN",
            status_code=status.HTTP_403_FORBIDDEN,
        )


class ConflictError(AwaxenException):
    """Resource conflict."""
    
    def __init__(self, message: str = "Resource conflict"):
        super().__init__(
            message=message,
            code="CONFLICT",
            status_code=status.HTTP_409_CONFLICT,
        )


class ValidationError(AwaxenException):
    """Validation error."""
    
    def __init__(self, message: str, details: dict[str, Any] | None = None):
        super().__init__(
            message=message,
            code="VALIDATION_ERROR",
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            details=details,
        )


class TenantContextError(AwaxenException):
    """Tenant context not available."""
    
    def __init__(self):
        super().__init__(
            message="Tenant context is required but not available",
            code="TENANT_CONTEXT_MISSING",
            status_code=status.HTTP_400_BAD_REQUEST,
        )


class RateLimitError(AwaxenException):
    """Rate limit exceeded."""
    
    def __init__(self, retry_after: int = 60):
        super().__init__(
            message=f"Rate limit exceeded. Retry after {retry_after} seconds",
            code="RATE_LIMIT_EXCEEDED",
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            details={"retry_after": retry_after},
        )


class ServiceUnavailableError(AwaxenException):
    """External service unavailable."""
    
    def __init__(self, service: str, message: str = "Service temporarily unavailable"):
        super().__init__(
            message=f"{service}: {message}",
            code="SERVICE_UNAVAILABLE",
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            details={"service": service},
        )


class GatewayTimeoutError(AwaxenException):
    """Gateway/device timeout."""
    
    def __init__(self, gateway_id: str | None = None):
        super().__init__(
            message="Gateway did not respond in time",
            code="GATEWAY_TIMEOUT",
            status_code=status.HTTP_504_GATEWAY_TIMEOUT,
            details={"gateway_id": gateway_id} if gateway_id else {},
        )


def _build_error_response(
    code: str,
    message: str,
    status_code: int,
    request: Request,
    details: dict | None = None,
) -> ORJSONResponse:
    """Build standardized error response."""
    request_id = _get_request_id(request)
    timestamp = datetime.now(timezone.utc).isoformat()
    
    return ORJSONResponse(
        status_code=status_code,
        content={
            "error": {
                "code": code,
                "message": message,
                "details": details or {},
                "request_id": request_id,
                "timestamp": timestamp,
                "path": str(request.url.path),
                "method": request.method,
            }
        },
        headers={"X-Request-ID": request_id},
    )


async def awaxen_exception_handler(request: Request, exc: AwaxenException) -> ORJSONResponse:
    """Handler for AwaxenException."""
    request_id = _get_request_id(request)
    
    # Log the error
    logger.warning(
        "Application error",
        error_code=exc.code,
        message=exc.message,
        status_code=exc.status_code,
        request_id=request_id,
        path=str(request.url.path),
        method=request.method,
    )
    
    # Report to Sentry if available (5xx errors only)
    if exc.status_code >= 500:
        try:
            import sentry_sdk
            sentry_sdk.capture_exception(exc)
        except ImportError:
            pass
    
    return _build_error_response(
        code=exc.code,
        message=exc.message,
        status_code=exc.status_code,
        request=request,
        details=exc.details,
    )


async def http_exception_handler(request: Request, exc: HTTPException) -> ORJSONResponse:
    """Handler for HTTPException."""
    request_id = _get_request_id(request)
    
    # Map common HTTP status codes to error codes
    code_map = {
        400: "BAD_REQUEST",
        401: "UNAUTHORIZED",
        403: "FORBIDDEN",
        404: "NOT_FOUND",
        405: "METHOD_NOT_ALLOWED",
        409: "CONFLICT",
        422: "VALIDATION_ERROR",
        429: "RATE_LIMIT_EXCEEDED",
        500: "INTERNAL_ERROR",
        502: "BAD_GATEWAY",
        503: "SERVICE_UNAVAILABLE",
        504: "GATEWAY_TIMEOUT",
    }
    
    error_code = code_map.get(exc.status_code, "HTTP_ERROR")
    
    logger.warning(
        "HTTP error",
        error_code=error_code,
        status_code=exc.status_code,
        detail=exc.detail,
        request_id=request_id,
        path=str(request.url.path),
    )
    
    return _build_error_response(
        code=error_code,
        message=str(exc.detail),
        status_code=exc.status_code,
        request=request,
    )


async def validation_exception_handler(request: Request, exc: Exception) -> ORJSONResponse:
    """Handler for Pydantic validation errors."""
    from pydantic import ValidationError as PydanticValidationError
    
    request_id = _get_request_id(request)
    
    if isinstance(exc, PydanticValidationError):
        errors = exc.errors()
        details = {
            "validation_errors": [
                {
                    "field": ".".join(str(loc) for loc in err.get("loc", [])),
                    "message": err.get("msg", "Invalid value"),
                    "type": err.get("type", "value_error"),
                }
                for err in errors
            ]
        }
        message = f"Validation failed: {len(errors)} error(s)"
    else:
        details = {}
        message = "Request validation failed"
    
    logger.warning(
        "Validation error",
        request_id=request_id,
        path=str(request.url.path),
        errors=details,
    )
    
    return _build_error_response(
        code="VALIDATION_ERROR",
        message=message,
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        request=request,
        details=details,
    )


async def generic_exception_handler(request: Request, exc: Exception) -> ORJSONResponse:
    """Handler for unhandled exceptions."""
    request_id = _get_request_id(request)
    
    # Log the full exception
    logger.exception(
        "Unhandled exception",
        request_id=request_id,
        path=str(request.url.path),
        method=request.method,
        error_type=type(exc).__name__,
        error_message=str(exc),
    )
    
    # Report to Sentry
    try:
        import sentry_sdk
        sentry_sdk.capture_exception(exc)
    except ImportError:
        pass
    
    return _build_error_response(
        code="INTERNAL_ERROR",
        message="An unexpected error occurred. Please try again later.",
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        request=request,
        details={"error_id": request_id},
    )
