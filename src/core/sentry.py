"""
Sentry Integration - Error Tracking & Monitoring

Sentry captures:
- Unhandled exceptions
- 5xx errors
- Performance traces
"""
import sentry_sdk
from sentry_sdk.integrations.fastapi import FastApiIntegration
from sentry_sdk.integrations.sqlalchemy import SqlalchemyIntegration
from sentry_sdk.integrations.redis import RedisIntegration
from sentry_sdk.integrations.celery import CeleryIntegration

from src.core.config import settings
from src.core.logging import get_logger

logger = get_logger(__name__)


def init_sentry() -> None:
    """
    Initialize Sentry SDK.
    
    Call this in application startup.
    """
    if not settings.sentry_dsn:
        logger.info("Sentry DSN not configured, skipping initialization")
        return
    
    sentry_sdk.init(
        dsn=settings.sentry_dsn,
        environment=settings.environment,
        release=f"awaxen-backend@{settings.app_version}",
        
        # Performance monitoring
        traces_sample_rate=0.1 if settings.environment == "production" else 1.0,
        profiles_sample_rate=0.1 if settings.environment == "production" else 1.0,
        
        # Integrations
        integrations=[
            FastApiIntegration(transaction_style="endpoint"),
            SqlalchemyIntegration(),
            RedisIntegration(),
            CeleryIntegration(),
        ],
        
        # Filter sensitive data
        send_default_pii=False,
        
        # Before send hook
        before_send=_before_send,
    )
    
    logger.info(
        "Sentry initialized",
        environment=settings.environment,
        dsn_configured=True,
    )


def _before_send(event, hint):
    """
    Filter events before sending to Sentry.
    
    - Remove sensitive headers
    - Filter out expected errors
    """
    # Don't send 4xx errors
    if "exception" in event:
        exc_info = hint.get("exc_info")
        if exc_info:
            exc_type, exc_value, _ = exc_info
            # Skip client errors
            if hasattr(exc_value, "status_code"):
                if 400 <= exc_value.status_code < 500:
                    return None
    
    # Remove sensitive headers
    if "request" in event and "headers" in event["request"]:
        headers = event["request"]["headers"]
        sensitive_headers = ["authorization", "cookie", "x-api-key"]
        for header in sensitive_headers:
            if header in headers:
                headers[header] = "[FILTERED]"
    
    return event


def capture_message(message: str, level: str = "info", **extra) -> None:
    """Capture a message to Sentry."""
    with sentry_sdk.push_scope() as scope:
        for key, value in extra.items():
            scope.set_extra(key, value)
        sentry_sdk.capture_message(message, level=level)


def set_user(user_id: str, email: str | None = None) -> None:
    """Set user context for Sentry."""
    sentry_sdk.set_user({
        "id": user_id,
        "email": email,
    })


def set_tag(key: str, value: str) -> None:
    """Set a tag for the current scope."""
    sentry_sdk.set_tag(key, value)
