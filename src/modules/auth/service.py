"""
Auth Module - Business Logic Service
NEVER put business logic in Routers. Routers only parse requests and call Services.
"""
import uuid
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from src.core.exceptions import ConflictError, NotFoundError, UnauthorizedError
from src.core.logging import get_logger
from src.core.security import get_password_hash, verify_password, create_access_token
from src.modules.auth.models import Organization, OrganizationUser, Role, User
from src.modules.auth.schemas import (
    Auth0SyncRequest,
    Auth0SyncResponse,
    LoginRequest,
    MeResponse,
    OrganizationCreate,
    OrganizationResponse,
    OrganizationUpdate,
    ProfileUpdateRequest,
    ProfileUpdateResponse,
    RegisterRequest,
    RoleCreate,
    RoleInfo,
    Token,
    UserCreate,
    UserUpdate,
)

logger = get_logger(__name__)


class AuthService:
    """Authentication and authorization service."""
    
    def __init__(self, db: AsyncSession):
        self.db = db
    
    async def authenticate(self, email: str, password: str) -> User | None:
        """Authenticate user by email and password."""
        user = await self.get_user_by_email(email)
        if not user:
            return None
        if not verify_password(password, user.hashed_password):
            return None
        return user
    
    async def login(self, request: LoginRequest) -> Token:
        """Login and return JWT token."""
        user = await self.authenticate(request.email, request.password)
        if not user:
            raise UnauthorizedError("Invalid email or password")
        
        if not user.is_active:
            raise UnauthorizedError("User account is disabled")
        
        # Update last login
        user.last_login = datetime.now(timezone.utc)
        await self.db.commit()
        
        # Get default organization
        default_org_id = None
        for membership in user.organization_memberships:
            if membership.is_default:
                default_org_id = membership.organization_id
                break
        
        # Create token with org context
        token = create_access_token(
            subject=str(user.id),
            extra_claims={"org_id": str(default_org_id) if default_org_id else None},
        )
        
        logger.info("User logged in", user_id=str(user.id), email=user.email)
        return Token(access_token=token)
    
    async def register(self, request: RegisterRequest) -> User:
        """Register a new user."""
        # Check if email exists
        existing = await self.get_user_by_email(request.email)
        if existing:
            raise ConflictError(f"User with email {request.email} already exists")
        
        # Create user
        user = User(
            email=request.email,
            hashed_password=get_password_hash(request.password),
            full_name=request.full_name,
            phone=request.phone,
            is_active=True,
            is_verified=False,
        )
        self.db.add(user)
        await self.db.flush()
        
        # Create organization if requested
        if request.organization_name:
            org = await self._create_organization_for_user(
                user=user,
                org_name=request.organization_name,
            )
            logger.info(
                "Organization created during registration",
                org_id=str(org.id),
                user_id=str(user.id),
            )
        
        await self.db.commit()
        await self.db.refresh(user)
        
        logger.info("User registered", user_id=str(user.id), email=user.email)
        return user
    
    async def _create_organization_for_user(
        self,
        user: User,
        org_name: str,
    ) -> Organization:
        """Create an organization and add user as admin."""
        # Generate slug from name
        slug = org_name.lower().replace(" ", "-")
        
        # Check if slug exists
        existing = await self.get_organization_by_slug(slug)
        if existing:
            slug = f"{slug}-{uuid.uuid4().hex[:6]}"
        
        org = Organization(name=org_name, slug=slug, is_active=True)
        self.db.add(org)
        await self.db.flush()
        
        # Get or create admin role
        admin_role = await self._get_or_create_admin_role()
        
        # Add user as org admin
        membership = OrganizationUser(
            user_id=user.id,
            organization_id=org.id,
            role_id=admin_role.id,
            is_default=True,
            joined_at=datetime.now(timezone.utc),
        )
        self.db.add(membership)
        
        return org
    
    async def _get_or_create_admin_role(self) -> Role:
        """
        Get or create the admin role for new users.
        
        Rol Hiyerarşisi:
        1. super_admin - Tam sistem yetkisi (tüm organizasyonlar)
        2. admin - Organizasyon yönetimi (kendi org'unda tam yetki)
        3. operator - Cihaz kontrolü
        4. user - Salt okunur erişim
        5. agent - Kiracı bulma, sözleşme yönetimi
        """
        # Önce admin rolünü ara
        stmt = select(Role).where(Role.code == "admin")
        result = await self.db.execute(stmt)
        role = result.scalar_one_or_none()
        
        if not role:
            # Admin rolü yoksa oluştur
            role = Role(
                name="Admin",
                code="admin",
                description="Full access to organization resources",
                permissions=["*"],
                is_system=True,
            )
            self.db.add(role)
            await self.db.flush()
        
        return role
    
    # ============== User Operations ==============
    
    async def get_user_by_id(self, user_id: uuid.UUID) -> User | None:
        """Get user by ID."""
        stmt = select(User).where(User.id == user_id)
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()
    
    async def get_user_by_email(self, email: str) -> User | None:
        """Get user by email."""
        stmt = (
            select(User)
            .options(selectinload(User.organization_memberships))
            .where(User.email == email)
        )
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()
    
    async def create_user(self, data: UserCreate) -> User:
        """Create a new user."""
        existing = await self.get_user_by_email(data.email)
        if existing:
            raise ConflictError(f"User with email {data.email} already exists")
        
        user = User(
            email=data.email,
            hashed_password=get_password_hash(data.password),
            full_name=data.full_name,
            phone=data.phone,
        )
        self.db.add(user)
        await self.db.commit()
        await self.db.refresh(user)
        return user
    
    async def update_user(self, user_id: uuid.UUID, data: UserUpdate) -> User:
        """Update user."""
        user = await self.get_user_by_id(user_id)
        if not user:
            raise NotFoundError("User", user_id)
        
        update_data = data.model_dump(exclude_unset=True)
        if "password" in update_data:
            update_data["hashed_password"] = get_password_hash(update_data.pop("password"))
        
        for field, value in update_data.items():
            setattr(user, field, value)
        
        await self.db.commit()
        await self.db.refresh(user)
        return user
    
    # ============== Organization Operations ==============
    
    async def get_organization_by_id(self, org_id: uuid.UUID) -> Organization | None:
        """Get organization by ID."""
        stmt = select(Organization).where(Organization.id == org_id)
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()
    
    async def get_organization_by_slug(self, slug: str) -> Organization | None:
        """Get organization by slug."""
        stmt = select(Organization).where(Organization.slug == slug)
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()
    
    async def create_organization(
        self,
        data: OrganizationCreate,
        owner_id: uuid.UUID,
    ) -> Organization:
        """Create a new organization."""
        existing = await self.get_organization_by_slug(data.slug)
        if existing:
            raise ConflictError(f"Organization with slug {data.slug} already exists")
        
        org = Organization(**data.model_dump())
        self.db.add(org)
        await self.db.flush()
        
        # Add owner as admin
        admin_role = await self._get_or_create_admin_role()
        membership = OrganizationUser(
            user_id=owner_id,
            organization_id=org.id,
            role_id=admin_role.id,
            is_default=True,
            joined_at=datetime.now(timezone.utc),
        )
        self.db.add(membership)
        
        await self.db.commit()
        await self.db.refresh(org)
        return org
    
    async def update_organization(
        self,
        org_id: uuid.UUID,
        data: OrganizationUpdate,
    ) -> Organization:
        """Update organization."""
        org = await self.get_organization_by_id(org_id)
        if not org:
            raise NotFoundError("Organization", org_id)
        
        update_data = data.model_dump(exclude_unset=True)
        for field, value in update_data.items():
            setattr(org, field, value)
        
        await self.db.commit()
        await self.db.refresh(org)
        return org
    
    async def list_user_organizations(self, user_id: uuid.UUID) -> list[Organization]:
        """List organizations a user belongs to."""
        stmt = (
            select(Organization)
            .join(OrganizationUser)
            .where(OrganizationUser.user_id == user_id)
        )
        result = await self.db.execute(stmt)
        return list(result.scalars().all())
    
    # ============== Role Operations ==============
    
    async def create_role(self, data: RoleCreate) -> Role:
        """Create a new role."""
        role = Role(**data.model_dump())
        self.db.add(role)
        await self.db.commit()
        await self.db.refresh(role)
        return role
    
    async def list_roles(self) -> list[Role]:
        """List all roles."""
        stmt = select(Role).order_by(Role.name)
        result = await self.db.execute(stmt)
        return list(result.scalars().all())
    
    # ============== Auth0 Operations ==============
    
    async def get_user_by_auth0_id(self, auth0_id: str) -> User | None:
        """Get user by Auth0 ID."""
        stmt = (
            select(User)
            .options(selectinload(User.organization_memberships))
            .where(User.auth0_id == auth0_id)
        )
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()
    
    async def sync_auth0_user(self, request: Auth0SyncRequest) -> Auth0SyncResponse:
        """
        Auth0 kullanıcısını Postgres ile senkronize et (Upsert).
        İlk girişte kullanıcı, organizasyon ve cüzdan oluşturulur.
        """
        # Mevcut kullanıcıyı kontrol et
        user = await self.get_user_by_auth0_id(request.auth0_id)
        is_new = user is None
        
        if is_new:
            # Email ile de kontrol et (Auth0 olmadan kayıtlı olabilir)
            user = await self.get_user_by_email(request.email)
            
            if user:
                # Mevcut kullanıcıya Auth0 ID ekle
                user.auth0_id = request.auth0_id
                if request.name and not user.full_name:
                    user.full_name = request.name
            else:
                # Yeni kullanıcı oluştur
                user = User(
                    auth0_id=request.auth0_id,
                    email=request.email,
                    full_name=request.name,
                    is_active=True,
                    is_verified=True,  # Auth0 ile doğrulanmış
                )
                self.db.add(user)
                await self.db.flush()
                
                # Varsayılan organizasyon oluştur
                org_name = request.name or request.email.split("@")[0]
                org = await self._create_organization_for_user(
                    user=user,
                    org_name=f"{org_name}'s Organization",
                )
                
                logger.info(
                    "New user created via Auth0 sync",
                    user_id=str(user.id),
                    auth0_id=request.auth0_id,
                )
        else:
            # Mevcut kullanıcıyı güncelle
            if request.name and request.name != user.full_name:
                user.full_name = request.name
        
        # Rol güncelle (eğer belirtilmişse)
        if request.role:
            await self._update_user_role(user, request.role)
        
        # Son giriş zamanını güncelle
        user.last_login = datetime.now(timezone.utc)
        
        await self.db.commit()
        await self.db.refresh(user)
        
        # Response oluştur
        me_response = await self._build_me_response(user)
        org_response = await self._get_default_organization_response(user)
        
        return Auth0SyncResponse(
            status="created" if is_new else "synced",
            message="Yeni kullanıcı oluşturuldu" if is_new else "Kullanıcı senkronize edildi",
            user=me_response,
            organization=org_response,
        )
    
    async def _update_user_role(self, user: User, role_code: str) -> None:
        """Kullanıcının varsayılan organizasyondaki rolünü güncelle."""
        # Rolü bul
        stmt = select(Role).where(Role.code == role_code)
        result = await self.db.execute(stmt)
        role = result.scalar_one_or_none()
        
        if not role:
            logger.warning("Role not found", role_code=role_code)
            return
        
        # Varsayılan organizasyon üyeliğini güncelle
        for membership in user.organization_memberships:
            if membership.is_default:
                membership.role_id = role.id
                break
    
    async def get_me(self, user: User) -> MeResponse:
        """Token'daki kullanıcının profil bilgisini döner."""
        return await self._build_me_response(user)
    
    async def update_profile(
        self, 
        user: User, 
        request: ProfileUpdateRequest,
    ) -> ProfileUpdateResponse:
        """Kullanıcı profilini güncelle."""
        update_data = request.model_dump(exclude_unset=True)
        
        # Alan isimlerini eşleştir
        field_mapping = {
            "phone_number": "phone",
        }
        
        for request_field, model_field in field_mapping.items():
            if request_field in update_data:
                update_data[model_field] = update_data.pop(request_field)
        
        for field, value in update_data.items():
            if hasattr(user, field):
                setattr(user, field, value)
        
        await self.db.commit()
        await self.db.refresh(user)
        
        me_response = await self._build_me_response(user)
        
        return ProfileUpdateResponse(
            message="Profil güncellendi",
            user=me_response,
        )
    
    async def _build_me_response(self, user: User) -> MeResponse:
        """MeResponse oluştur."""
        role_info = None
        permissions: list[str] = []
        org_response = None
        
        # Varsayılan organizasyon ve rol bilgisini al
        for membership in user.organization_memberships:
            if membership.is_default:
                if membership.role:
                    role_info = RoleInfo(
                        code=membership.role.code,
                        name=membership.role.name,
                    )
                    permissions = membership.role.permissions or []
                
                # Organizasyon bilgisi
                org = await self.get_organization_by_id(membership.organization_id)
                if org:
                    org_response = OrganizationResponse.model_validate(org)
                break
        
        return MeResponse(
            id=user.id,
            auth0_id=user.auth0_id,
            email=user.email,
            full_name=user.full_name,
            phone=user.phone,
            telegram_username=user.telegram_username,
            role=role_info,
            permissions=permissions,
            organization=org_response,
            is_active=user.is_active,
            created_at=user.created_at,
        )
    
    async def _get_default_organization_response(self, user: User) -> OrganizationResponse | None:
        """Kullanıcının varsayılan organizasyonunu döner."""
        for membership in user.organization_memberships:
            if membership.is_default:
                org = await self.get_organization_by_id(membership.organization_id)
                if org:
                    return OrganizationResponse.model_validate(org)
        return None
