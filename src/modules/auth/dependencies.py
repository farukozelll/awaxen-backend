"""
Auth Module - FastAPI Dependencies

Auth0 JWT token doğrulaması ile kullanıcı kimlik doğrulama.
Token'daki auth0_id ile veritabanından kullanıcı bulunur.
"""
import uuid
from typing import Annotated

from fastapi import Depends, Header, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.auth0 import Auth0User, get_current_user_auth0, verify_token as verify_auth0_token
from src.core.database import get_db
from src.core.exceptions import ForbiddenError, TenantContextError, UnauthorizedError
from src.core.logging import get_logger
from src.core.security import verify_token
from src.modules.auth.models import User
from src.modules.auth.service import AuthService

logger = get_logger(__name__)

# Security scheme
security = HTTPBearer(auto_error=False)


async def get_auth_service(db: Annotated[AsyncSession, Depends(get_db)]) -> AuthService:
    """Get AuthService instance with injected database session."""
    return AuthService(db)


async def get_current_user(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(security)],
    auth_service: Annotated[AuthService, Depends(get_auth_service)],
) -> User:
    """
    Get current authenticated user from Auth0 JWT token.
    
    Flow:
    1. Auth0 token'ı doğrula
    2. Token'daki auth0_id (sub) ile veritabanından kullanıcıyı bul
    3. Kullanıcı yoksa UnauthorizedError fırlat
    
    Raises:
        UnauthorizedError: Token geçersiz veya kullanıcı bulunamadı
    """
    if not credentials:
        raise UnauthorizedError("Authentication required")
    
    try:
        # Auth0 token'ı doğrula
        auth0_user = await verify_auth0_token(credentials.credentials)
        auth0_id = auth0_user.sub
        
        logger.debug("Auth0 token verified", auth0_id=auth0_id, email=auth0_user.email)
        
    except HTTPException as e:
        logger.warning("Auth0 token verification failed", detail=e.detail)
        raise UnauthorizedError(e.detail)
    except Exception as e:
        logger.error("Token verification error", error=str(e))
        raise UnauthorizedError("Invalid or expired token")
    
    # Auth0 ID ile kullanıcıyı bul
    user = await auth_service.get_user_by_auth0_id(auth0_id)
    
    if not user:
        logger.warning("User not found in database", auth0_id=auth0_id)
        raise UnauthorizedError(
            "User not synced. Please call /api/v1/auth/sync first."
        )
    
    if not user.is_active:
        raise UnauthorizedError("User account is disabled")
    
    return user


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
    ):
        self.organization_id = organization_id
        self.user = user
    
    @property
    def user_id(self) -> uuid.UUID:
        return self.user.id


async def get_tenant_context(
    current_user: Annotated[User, Depends(get_current_user)],
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(security)],
    x_organization_id: Annotated[str | None, Header()] = None,
) -> TenantContext:
    """
    Get tenant context from token or header.
    
    Priority:
    1. X-Organization-Id header
    2. org_id from JWT token
    3. User's default organization
    
    Raises TenantContextError if no organization context available.
    """
    org_id: uuid.UUID | None = None
    
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
        payload = verify_token(credentials.credentials)
        if payload and payload.get("org_id"):
            try:
                org_id = uuid.UUID(payload["org_id"])
            except ValueError:
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
    
    return TenantContext(organization_id=org_id, user=current_user)


def require_permissions(permissions: list[str]):
    """
    Dependency factory for permission-based access control.
    
    Rol Hiyerarşisi:
    - admin: Tüm yetkiler ("*")
    - tenant: Organizasyon yönetimi yetkileri
    - user: Salt okunur yetkiler
    - device: Telemetri yetkileri
    
    Usage:
        @router.get("/admin", dependencies=[Depends(require_permissions(["audit:read"]))])
        async def admin_endpoint(): ...
    
    Or as a dependency:
        current_user: User = Depends(require_permissions(["audit:read"]))
    """
    async def permission_checker(
        current_user: Annotated[User, Depends(get_current_user)],
    ) -> User:
        # Superusers have all permissions
        if current_user.is_superuser:
            return current_user
        
        # Check user's permissions from organization memberships
        user_permissions: set[str] = set()
        user_role: str | None = None
        
        for membership in current_user.organization_memberships:
            if membership.role and membership.role.permissions:
                user_permissions.update(membership.role.permissions)
                # Track if user has admin role
                if membership.role.code == "admin":
                    user_role = "admin"
        
        # Admin role has all permissions (wildcard)
        if user_role == "admin" or "*" in user_permissions:
            return current_user
        
        # Check if user has required permissions
        missing = set(permissions) - user_permissions
        if missing:
            raise ForbiddenError(f"Missing permissions: {', '.join(missing)}")
        
        return current_user
    
    return permission_checker


def require_role(roles: list[str]):
    """
    Dependency factory for role-based access control.
    
    Usage:
        @router.get("/admin-only", dependencies=[Depends(require_role(["admin"]))])
        async def admin_endpoint(): ...
    """
    async def role_checker(
        current_user: Annotated[User, Depends(get_current_user)],
    ) -> User:
        # Superusers bypass role check
        if current_user.is_superuser:
            return current_user
        
        # Check user's roles from organization memberships
        user_roles: set[str] = set()
        for membership in current_user.organization_memberships:
            if membership.role:
                user_roles.add(membership.role.code)
        
        # Check if user has any of the required roles
        if not user_roles.intersection(set(roles)):
            raise ForbiddenError(f"Required role: {', '.join(roles)}")
        
        return current_user
    
    return role_checker


# Type aliases for dependency injection
CurrentUser = Annotated[User, Depends(get_current_user)]
CurrentActiveUser = Annotated[User, Depends(get_current_active_user)]
CurrentSuperuser = Annotated[User, Depends(get_current_superuser)]
TenantContextDep = Annotated[TenantContext, Depends(get_tenant_context)]
AuthServiceDep = Annotated[AuthService, Depends(get_auth_service)]
Auth0UserDep = Annotated[Auth0User, Depends(get_current_user_auth0)]
