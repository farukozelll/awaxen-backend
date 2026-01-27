"""
Enhanced Auth Dependencies - Hybrid Authentication System

Supports both Auth0 tokens (RS256) and Local tokens (HS256) including impersonation tokens.
"""
import uuid
from typing import Annotated

from fastapi import Depends, Header, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from src.core.auth0 import Auth0User, get_current_user_auth0
from src.core.auth0 import verify_token as verify_auth0_token
from src.core.exceptions import ForbiddenError, TenantContextError, UnauthorizedError
from src.core.logging import get_logger
from src.core.security_enhanced import (
    get_token_info,
    is_impersonation_token,
    validate_impersonation_token,
)
from src.core.security_enhanced import (
    verify_token as verify_local_token,
)
from src.modules.auth.models import User
from src.modules.auth.service import AuthService, get_auth_service

logger = get_logger(__name__)

# Security scheme
security = HTTPBearer(auto_error=False)


async def get_current_user_hybrid(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(security)],
    auth_service: Annotated[AuthService, Depends(get_auth_service)],
) -> User:
    """
    Get current authenticated user using hybrid authentication.
    
    Tries Auth0 first, then falls back to local tokens.
    Supports impersonation tokens with proper validation.
    """
    if not credentials:
        raise UnauthorizedError("Authentication required")
    
    try:
        # Try Auth0 token first (production preference)
        auth0_user = await verify_auth0_token(credentials.credentials)
        logger.debug("Auth0 token verified", auth0_id=auth0_user.sub, email=auth0_user.email)
        
        # Get or sync user from database
        user = await auth_service.get_user_by_auth0_id(auth0_user.sub)
        if not user:
            raise UnauthorizedError(
                "User not synced. Please call /api/v1/auth/sync first."
            )
        
        if not user.is_active:
            raise UnauthorizedError("User account is disabled")
        
        # Add Auth0 context to user object for potential use
        user.auth0_user = auth0_user
        return user
        
    except HTTPException as e:
        # If Auth0 fails, try local token
        if e.status_code != 401:  # Only fall back for auth errors
            raise
        
        logger.debug("Auth0 token failed, trying local token")
        return await get_current_user_local(credentials, auth_service)
    except Exception as e:
        logger.error("Authentication error", error=str(e))
        raise UnauthorizedError("Invalid token")


async def get_current_user_local(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(security)],
    auth_service: Annotated[AuthService, Depends(get_auth_service)],
) -> User:
    """
    Get current authenticated user using local JWT tokens.
    
    Supports regular and impersonation tokens.
    """
    if not credentials:
        raise UnauthorizedError("Authentication required")
    
    try:
        # Verify local token
        payload = verify_local_token(credentials.credentials)
        if not payload:
            raise UnauthorizedError("Invalid token")
        
        # Check if this is an impersonation token
        if is_impersonation_token(payload):
            if not validate_impersonation_token(payload):
                raise UnauthorizedError("Invalid or expired impersonation token")
            
            logger.warning(
                "Impersonation token used",
                impersonated_user_id=payload.get("impersonated_user_id"),
                impersonator_id=payload.get("impersonator_id"),
                token_info=get_token_info(payload),
            )
        
        # Get user from database
        user = await auth_service.get_user_by_id(uuid.UUID(payload["sub"]))
        if not user:
            raise UnauthorizedError("User not found")
        
        if not user.is_active:
            raise UnauthorizedError("User account is disabled")
        
        return user
        
    except Exception as e:
        logger.error("Local token verification failed", error=str(e))
        raise UnauthorizedError("Invalid token")


async def get_current_user(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(security)],
    auth_service: Annotated[AuthService, Depends(get_auth_service)],
) -> User:
    """
    Get current authenticated user (legacy compatibility).
    
    Uses hybrid authentication for maximum compatibility.
    """
    return await get_current_user_hybrid(credentials, auth_service)


async def get_current_active_user(
    current_user: Annotated[User, Depends(get_current_user)],
) -> User:
    """Get current active user."""
    if not current_user.is_active:
        raise ForbiddenError("User account is disabled")
    return current_user


async def get_current_superuser(
    current_user: Annotated[User, Depends(get_current_user)],
) -> User:
    """Get current superuser."""
    if not current_user.is_superuser:
        raise ForbiddenError("Superuser access required")
    return current_user


class TenantContext:
    """
    Tenant context for multi-tenant operations.
    Extracts organization_id from token or header.
    """
    
    def __init__(
        self,
        organization_id: uuid.UUID,
        user: User,
        token_info: dict | None = None,
    ):
        self.organization_id = organization_id
        self.user = user
        self.token_info = token_info
    
    @property
    def user_id(self) -> uuid.UUID:
        return self.user.id
    
    @property
    def is_impersonated(self) -> bool:
        """Check if current session is impersonated."""
        return self.token_info and self.token_info.get("is_impersonated", False)


async def get_tenant_context_hybrid(
    current_user: Annotated[User, Depends(get_current_user)],
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(security)],
    x_organization_id: Annotated[str | None, Header()] = None,
) -> TenantContext:
    """
    Get tenant context from token or header (enhanced).
    
    Supports both Auth0 and local tokens with proper impersonation detection.
    """
    org_id: uuid.UUID | None = None
    token_info: dict | None = None
    
    # Try header first
    if x_organization_id:
        try:
            org_id = uuid.UUID(x_organization_id)
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid X-Organization-Id header",
            )
    
    # Try token
    if not org_id and credentials:
        try:
            # Try to verify token to get org_id
            payload = verify_local_token(credentials.credentials)
            if payload and payload.get("org_id"):
                try:
                    org_id = uuid.UUID(payload["org_id"])
                    token_info = get_token_info(payload)
                except ValueError:
                    pass
        except Exception:
            # Token verification failed, continue with default org
            pass
    
    # Try default organization
    if not org_id:
        for membership in current_user.organization_memberships:
            if membership.is_default:
                org_id = membership.organization_id
                break
    
    if not org_id:
        raise TenantContextError()
    
    # Verify user belongs to organization
    user_org_ids = {m.organization_id for m in current_user.organization_memberships}
    if org_id not in user_org_ids:
        raise ForbiddenError("You don't have access to this organization")
    
    return TenantContext(organization_id=org_id, user=current_user, token_info=token_info)


async def get_tenant_context(
    current_user: Annotated[User, Depends(get_current_user)],
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(security)],
    x_organization_id: Annotated[str | None, Header()] = None,
) -> TenantContext:
    """
    Get tenant context from token or header (legacy compatibility).
    """
    return await get_tenant_context_hybrid(current_user, credentials, x_organization_id)


# Type aliases for dependency injection
CurrentUser = Annotated[User, Depends(get_current_user)]
CurrentActiveUser = Annotated[User, Depends(get_current_active_user)]
CurrentSuperuser = Annotated[User, Depends(get_current_superuser)]
TenantContextDep = Annotated[TenantContext, Depends(get_tenant_context)]
AuthServiceDep = Annotated[AuthService, Depends(get_auth_service)]
Auth0UserDep = Annotated[Auth0User, Depends(get_current_user_auth0)]

# Enhanced dependencies for specific use cases
HybridCurrentUser = Annotated[User, Depends(get_current_user_hybrid)]
LocalCurrentUser = Annotated[User, Depends(get_current_user_local)]
HybridTenantContextDep = Annotated[TenantContext, Depends(get_tenant_context_hybrid)]
