"""
Security Module - Enhanced JWT Token Management

Hybrid Authentication System:
- Supports both Auth0 tokens (RS256) and Local tokens (HS256)
- Impersonation tokens with proper validation
- Token type detection and validation
"""
from datetime import datetime, timedelta, UTC
from typing import Any

from jose import JWTError, jwt
from passlib.context import CryptContext

from src.core.config import settings
from src.core.logging import get_logger

logger = get_logger(__name__)

# Password hashing context
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify a password against its hash."""
    return pwd_context.verify(plain_password, hashed_password)


def get_password_hash(password: str) -> str:
    """Hash a password."""
    return pwd_context.hash(password)


def create_access_token(
    subject: str | int,
    expires_delta: timedelta | None = None,
    extra_claims: dict[str, Any] | None = None,
    token_type: str = "access",  # Token type for validation
) -> str:
    """
    Create a JWT access token with type support.
    
    Args:
        subject: The subject of the token (usually user ID)
        expires_delta: Optional custom expiration time
        extra_claims: Additional claims to include in the token
        token_type: Token type for validation ("local" or "auth0")
    
    Returns:
        Encoded JWT token string
    """
    if expires_delta:
        expire = datetime.now(UTC) + expires_delta
    else:
        expire = datetime.now(UTC) + timedelta(
            minutes=settings.access_token_expire_minutes
        )
    
    to_encode: dict[str, Any] = {
        "exp": expire,
        "sub": str(subject),
        "iat": datetime.now(UTC),
        "token_type": token_type,  # Critical: Token type identification
    }
    
    if extra_claims:
        to_encode.update(extra_claims)
    
    # Use different keys for different token types if needed
    secret_key = settings.secret_key
    algorithm = settings.algorithm
    
    return jwt.encode(to_encode, secret_key, algorithm=algorithm)


def create_impersonation_token(
    target_user_id: str,
    admin_user_id: str,
    duration_minutes: int = 60,
    org_id: str | None = None,
    reason: str | None = None,
) -> str:
    """
    Create a secure impersonation token with proper claims.
    
    Args:
        target_user_id: ID of the user being impersonated
        admin_user_id: ID of the admin performing impersonation
        duration_minutes: How long the impersonation lasts
        org_id: Organization context (optional)
        reason: Reason for impersonation (optional)
    
    Returns:
        Encoded JWT impersonation token
    """
    expires_at = datetime.now(UTC) + timedelta(minutes=duration_minutes)
    
    extra_claims = {
        "token_type": "impersonation",
        "impersonator_id": admin_user_id,
        "impersonated_user_id": target_user_id,
        "impersonation_reason": reason,
        "impersonation_expires_at": expires_at.isoformat(),
        "is_impersonated": True,
    }
    
    if org_id:
        extra_claims["org_id"] = org_id
    
    logger.info(
        "Creating impersonation token",
        target_user_id=target_user_id,
        admin_user_id=admin_user_id,
        duration_minutes=duration_minutes,
        expires_at=expires_at.isoformat(),
    )
    
    return create_access_token(
        subject=target_user_id,
        expires_delta=timedelta(minutes=duration_minutes),
        extra_claims=extra_claims,
        token_type="impersonation"  # Token type for impersonation
    )


def verify_token(token: str) -> dict[str, Any] | None:
    """
    Verify and decode a JWT token with type support.
    
    Args:
        token: The JWT token string
    
    Returns:
        Decoded token payload or None if invalid
    """
    try:
        payload = jwt.decode(
            token,
            settings.secret_key,
            algorithms=[settings.algorithm],
        )
        return payload
    except JWTError as e:
        logger.warning("Token verification failed", error=str(e))
        return None


def verify_token_with_type(token: str, expected_type: str | None = None) -> dict[str, Any] | None:
    """
    Verify token with optional type checking.
    
    Args:
        token: The JWT token string
        expected_type: Expected token type (optional)
    
    Returns:
        Decoded token payload or None if invalid
    """
    payload = verify_token(token)
    
    if not payload:
        return None
    
    # Check token type if specified
    if expected_type and payload.get("token_type") != expected_type:
        logger.warning(
            "Token type mismatch",
            expected=expected_type,
            actual=payload.get("token_type")
        )
        return None
    
    return payload


def is_impersonation_token(payload: dict[str, Any]) -> bool:
    """
    Check if token is an impersonation token.
    
    Args:
        payload: Decoded token payload
    
    Returns:
        True if this is an impersonation token
    """
    return payload.get("token_type") == "impersonation" and payload.get("is_impersonated") is True


def validate_impersonation_token(payload: dict[str, Any]) -> bool:
    """
    Validate impersonation token for security.
    
    Args:
        payload: Decoded token payload
    
    Returns:
        True if token is valid for impersonation
    """
    if not is_impersonation_token(payload):
        return False
    
    # Check if impersonation is still valid
    expires_at_str = payload.get("impersonation_expires_at")
    if expires_at_str:
        try:
            expires_at = datetime.fromisoformat(expires_at_str)
            if datetime.now(UTC) > expires_at:
                logger.warning("Impersonation token expired")
                return False
        except ValueError:
            logger.warning("Invalid expiration date in impersonation token")
            return False
    
    return True


def get_token_info(payload: dict[str, Any]) -> dict[str, Any]:
    """
    Extract token information for logging and debugging.
    
    Args:
        payload: Decoded token payload
    
    Returns:
        Token information dictionary
    """
    return {
        "token_type": payload.get("token_type", "unknown"),
        "subject": payload.get("sub"),
        "expires_at": payload.get("exp"),
        "issued_at": payload.get("iat"),
        "is_impersonated": payload.get("is_impersonated", False),
        "impersonator_id": payload.get("impersonator_id"),
        "impersonated_user_id": payload.get("impersonated_user_id"),
        "org_id": payload.get("org_id"),
    }
