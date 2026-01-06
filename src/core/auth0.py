"""
Auth0 Integration Module
JWT verification and user authentication via Auth0.
"""
from typing import Any

import httpx
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt

from src.core.config import settings
from src.core.logging import get_logger

logger = get_logger(__name__)

# Auth0 configuration
AUTH0_DOMAIN = settings.auth0_domain
AUTH0_AUDIENCE = settings.auth0_audience
AUTH0_ALGORITHMS = ["RS256"]
AUTH0_ISSUER = f"https://{AUTH0_DOMAIN}/"

# Security scheme
auth0_scheme = HTTPBearer(auto_error=False)

# Cache for JWKS
_jwks_cache: dict[str, Any] | None = None


async def get_jwks() -> dict[str, Any]:
    """
    Fetch JSON Web Key Set from Auth0.
    Cached to avoid repeated requests.
    """
    global _jwks_cache
    
    if _jwks_cache is not None:
        return _jwks_cache
    
    if not AUTH0_DOMAIN:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Auth0 not configured",
        )
    
    jwks_url = f"https://{AUTH0_DOMAIN}/.well-known/jwks.json"
    
    async with httpx.AsyncClient() as client:
        try:
            response = await client.get(jwks_url)
            response.raise_for_status()
            _jwks_cache = response.json()
            return _jwks_cache
        except httpx.HTTPError as e:
            logger.error("Failed to fetch JWKS", error=str(e))
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to fetch authentication keys",
            )


def get_rsa_key(token: str, jwks: dict[str, Any]) -> dict[str, Any] | None:
    """
    Extract RSA key from JWKS that matches the token's key ID.
    """
    try:
        unverified_header = jwt.get_unverified_header(token)
    except JWTError:
        return None
    
    for key in jwks.get("keys", []):
        if key.get("kid") == unverified_header.get("kid"):
            return {
                "kty": key["kty"],
                "kid": key["kid"],
                "use": key["use"],
                "n": key["n"],
                "e": key["e"],
            }
    
    return None


class Auth0User:
    """Authenticated user from Auth0 token."""
    
    def __init__(self, payload: dict[str, Any]):
        self.sub: str = payload.get("sub", "")
        self.email: str | None = payload.get("email")
        self.email_verified: bool = payload.get("email_verified", False)
        self.name: str | None = payload.get("name")
        self.nickname: str | None = payload.get("nickname")
        self.picture: str | None = payload.get("picture")
        self.permissions: list[str] = payload.get("permissions", [])
        self.roles: list[str] = payload.get(f"{AUTH0_AUDIENCE}/roles", [])
        self._payload = payload
    
    @property
    def auth0_id(self) -> str:
        """Auth0 user ID (sub claim)."""
        return self.sub
    
    @property
    def is_verified(self) -> bool:
        """Check if email is verified."""
        return self.email_verified
    
    def has_permission(self, permission: str) -> bool:
        """Check if user has a specific permission."""
        return permission in self.permissions
    
    def has_role(self, role: str) -> bool:
        """Check if user has a specific role."""
        return role in self.roles
    
    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "sub": self.sub,
            "email": self.email,
            "email_verified": self.email_verified,
            "name": self.name,
            "nickname": self.nickname,
            "picture": self.picture,
            "permissions": self.permissions,
            "roles": self.roles,
        }


async def verify_token(token: str) -> Auth0User:
    """
    Verify Auth0 JWT token and return user info.
    
    Args:
        token: JWT token string
        
    Returns:
        Auth0User with decoded claims
        
    Raises:
        HTTPException: If token is invalid
    """
    jwks = await get_jwks()
    rsa_key = get_rsa_key(token, jwks)
    
    if not rsa_key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token key",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    try:
        payload = jwt.decode(
            token,
            rsa_key,
            algorithms=AUTH0_ALGORITHMS,
            audience=AUTH0_AUDIENCE,
            issuer=AUTH0_ISSUER,
        )
        return Auth0User(payload)
    except jwt.ExpiredSignatureError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token has expired",
            headers={"WWW-Authenticate": "Bearer"},
        )
    except jwt.JWTClaimsError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token claims",
            headers={"WWW-Authenticate": "Bearer"},
        )
    except JWTError as e:
        logger.error("JWT verification failed", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token",
            headers={"WWW-Authenticate": "Bearer"},
        )


async def get_current_user_auth0(
    credentials: HTTPAuthorizationCredentials | None = Depends(auth0_scheme),
) -> Auth0User:
    """
    FastAPI dependency to get current authenticated user via Auth0.
    
    Usage:
        @router.get("/protected")
        async def protected_route(user: Auth0User = Depends(get_current_user_auth0)):
            return {"user": user.email}
    """
    if not credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    return await verify_token(credentials.credentials)


async def get_optional_user_auth0(
    credentials: HTTPAuthorizationCredentials | None = Depends(auth0_scheme),
) -> Auth0User | None:
    """
    FastAPI dependency to get current user if authenticated, None otherwise.
    Useful for endpoints that work with or without authentication.
    """
    if not credentials:
        return None
    
    try:
        return await verify_token(credentials.credentials)
    except HTTPException:
        return None


def require_permission(permission: str):
    """
    Dependency factory to require a specific permission.
    
    Usage:
        @router.get("/admin")
        async def admin_route(
            user: Auth0User = Depends(require_permission("admin:read"))
        ):
            return {"admin": True}
    """
    async def check_permission(
        user: Auth0User = Depends(get_current_user_auth0),
    ) -> Auth0User:
        if not user.has_permission(permission):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Permission required: {permission}",
            )
        return user
    
    return check_permission


def require_role(role: str):
    """
    Dependency factory to require a specific role.
    
    Usage:
        @router.get("/admin")
        async def admin_route(
            user: Auth0User = Depends(require_role("admin"))
        ):
            return {"admin": True}
    """
    async def check_role(
        user: Auth0User = Depends(get_current_user_auth0),
    ) -> Auth0User:
        if not user.has_role(role):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Role required: {role}",
            )
        return user
    
    return check_role
