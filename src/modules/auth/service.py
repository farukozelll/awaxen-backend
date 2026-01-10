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
from src.modules.auth.models import (
    Organization, OrganizationUser, OrganizationModule, Role, User, 
    RoleType, Permission, ROLE_PERMISSIONS, ModuleType, MODULE_PERMISSIONS
)
from src.modules.auth.schemas import (
    AddUserToOrganizationRequest,
    AddUserToOrganizationResponse,
    AssignModulesRequest,
    AssignPermissionsRequest,
    AssignRoleRequest,
    Auth0SyncRequest,
    Auth0SyncResponse,
    AvailableModulesResponse,
    AvailablePermissionsResponse,
    AvailableRolesResponse,
    CreateOrganizationStep1Request,
    CreateOrganizationStep1Response,
    CreateOrganizationStep2Request,
    CreateOrganizationStep2Response,
    CreateOrganizationWithUserRequest,
    CreateOrganizationWithUserResponse,
    LoginRequest,
    MeResponse,
    ModuleInfo,
    OnboardingRequest,
    OnboardingResponse,
    OrganizationCreate,
    OrganizationModuleResponse,
    OrganizationResponse,
    OrganizationUpdate,
    OrganizationWithModulesResponse,
    ProfileUpdateRequest,
    ProfileUpdateResponse,
    RegisterRequest,
    RoleCreate,
    RoleInfo,
    RoleResponse,
    Token,
    UserCreate,
    UserResponse,
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
        
        # Get role and permissions for token
        role_code = None
        permissions: list[str] = []
        for membership in user.organization_memberships:
            if membership.is_default and membership.role:
                role_code = membership.role.code
                permissions = membership.role.permissions or []
                break
        
        # Create token with org context, role and permissions
        token = create_access_token(
            subject=str(user.id),
            extra_claims={
                "org_id": str(default_org_id) if default_org_id else None,
                "role": role_code,
                "permissions": permissions,
            },
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
        
        # Get or create tenant role (organization owner)
        tenant_role = await self._get_or_create_tenant_role()
        
        # Add user as org tenant (owner)
        membership = OrganizationUser(
            user_id=user.id,
            organization_id=org.id,
            role_id=tenant_role.id,
            is_default=True,
            joined_at=datetime.now(timezone.utc),
        )
        self.db.add(membership)
        
        return org
    
    async def _get_or_create_role(self, role_code: str) -> Role:
        """
        Get or create a role by code.
        
        Rol Hiyerarşisi:
        1. admin - Sistem yöneticisi (tüm yetkiler)
        2. tenant - Organizasyon yöneticisi (kendi org'unda tam yetki)
        3. user - Normal kullanıcı (salt okunur)
        4. device - Telemetri erişimi
        """
        stmt = select(Role).where(Role.code == role_code)
        result = await self.db.execute(stmt)
        role = result.scalar_one_or_none()
        
        if not role:
            # Rol yoksa oluştur
            role_names = {
                RoleType.ADMIN.value: "Admin",
                RoleType.TENANT.value: "Tenant",
                RoleType.USER.value: "User",
                RoleType.DEVICE.value: "Device",
            }
            role_descriptions = {
                RoleType.ADMIN.value: "Sistem yöneticisi - tüm yetkiler",
                RoleType.TENANT.value: "Organizasyon yöneticisi",
                RoleType.USER.value: "Normal kullanıcı - salt okunur",
                RoleType.DEVICE.value: "Cihaz/Telemetri erişimi",
            }
            
            role = Role(
                name=role_names.get(role_code, role_code.title()),
                code=role_code,
                description=role_descriptions.get(role_code, ""),
                permissions=ROLE_PERMISSIONS.get(role_code, []),
                is_system=True,
            )
            self.db.add(role)
            await self.db.flush()
        
        return role
    
    async def _get_or_create_tenant_role(self) -> Role:
        """Get or create the tenant role for new organization owners."""
        return await self._get_or_create_role(RoleType.TENANT.value)
    
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
        
        # Add owner as tenant
        tenant_role = await self._get_or_create_tenant_role()
        membership = OrganizationUser(
            user_id=owner_id,
            organization_id=org.id,
            role_id=tenant_role.id,
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
        modules: list[str] = []
        org_id = None
        
        # Varsayılan organizasyon ve rol bilgisini al
        for membership in user.organization_memberships:
            if membership.is_default:
                org_id = membership.organization_id
                
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
        
        # Organizasyonun aktif modüllerini al
        if org_id:
            modules = await self.get_organization_modules(org_id)
        
        return MeResponse(
            id=user.id,
            auth0_id=user.auth0_id,
            email=user.email,
            full_name=user.full_name,
            first_name=user.first_name,
            last_name=user.last_name,
            phone=user.phone,
            telegram_username=user.telegram_username,
            role=role_info,
            permissions=permissions,
            organization=org_response,
            modules=modules,
            onboarding_completed=user.onboarding_completed,
            onboarding_step=user.onboarding_step,
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
    
    # ============== Admin Operations ==============
    
    async def create_organization_with_user(
        self,
        request: CreateOrganizationWithUserRequest,
    ) -> CreateOrganizationWithUserResponse:
        """
        Admin tarafından organizasyon ve kullanıcı birlikte oluşturma.
        Organizasyon oluşturulur ve belirtilen kullanıcı atanan rolle eklenir.
        """
        # Slug oluştur
        slug = request.organization_slug
        if not slug:
            slug = request.organization_name.lower().replace(" ", "-").replace("'", "")
        
        # Slug kontrolü
        existing_org = await self.get_organization_by_slug(slug)
        if existing_org:
            slug = f"{slug}-{uuid.uuid4().hex[:6]}"
        
        # Email kontrolü
        existing_user = await self.get_user_by_email(request.user_email)
        if existing_user:
            raise ConflictError(f"User with email {request.user_email} already exists")
        
        # Organizasyon oluştur
        org = Organization(
            name=request.organization_name,
            slug=slug,
            description=request.organization_description,
            email=request.organization_email,
            phone=request.organization_phone,
            address=request.organization_address,
            is_active=True,
        )
        self.db.add(org)
        await self.db.flush()
        
        # Kullanıcı oluştur
        user = User(
            email=request.user_email,
            full_name=request.user_full_name,
            phone=request.user_phone,
            is_active=True,
            is_verified=False,
        )
        self.db.add(user)
        await self.db.flush()
        
        # Rol al veya oluştur
        role = await self._get_or_create_role(request.user_role)
        
        # Ek yetkiler varsa role ekle (custom permissions)
        if request.user_permissions:
            # Role'un permission'larını kopyala ve ek yetkileri ekle
            all_permissions = list(set(role.permissions + request.user_permissions))
            role.permissions = all_permissions
        
        # Kullanıcıyı organizasyona ekle
        membership = OrganizationUser(
            user_id=user.id,
            organization_id=org.id,
            role_id=role.id,
            is_default=True,
            joined_at=datetime.now(timezone.utc),
        )
        self.db.add(membership)
        
        await self.db.commit()
        await self.db.refresh(org)
        await self.db.refresh(user)
        await self.db.refresh(role)
        
        logger.info(
            "Organization and user created by admin",
            org_id=str(org.id),
            user_id=str(user.id),
            role=request.user_role,
        )
        
        return CreateOrganizationWithUserResponse(
            message="Organizasyon ve kullanıcı başarıyla oluşturuldu",
            organization=OrganizationResponse.model_validate(org),
            user=UserResponse.model_validate(user),
            role=RoleResponse.model_validate(role),
        )
    
    async def assign_role(self, request: AssignRoleRequest) -> dict:
        """Kullanıcıya rol ata."""
        # Kullanıcıyı kontrol et
        user = await self.get_user_by_id(request.user_id)
        if not user:
            raise NotFoundError("User", request.user_id)
        
        # Organizasyonu kontrol et
        org = await self.get_organization_by_id(request.organization_id)
        if not org:
            raise NotFoundError("Organization", request.organization_id)
        
        # Rolü al veya oluştur
        role = await self._get_or_create_role(request.role_code)
        
        # Ek yetkiler varsa ekle
        if request.additional_permissions:
            all_permissions = list(set(role.permissions + request.additional_permissions))
            role.permissions = all_permissions
            await self.db.flush()
        
        # Mevcut üyeliği kontrol et
        stmt = select(OrganizationUser).where(
            OrganizationUser.user_id == request.user_id,
            OrganizationUser.organization_id == request.organization_id,
        )
        result = await self.db.execute(stmt)
        membership = result.scalar_one_or_none()
        
        if membership:
            # Mevcut üyeliği güncelle
            membership.role_id = role.id
        else:
            # Yeni üyelik oluştur
            membership = OrganizationUser(
                user_id=request.user_id,
                organization_id=request.organization_id,
                role_id=role.id,
                is_default=False,
                joined_at=datetime.now(timezone.utc),
            )
            self.db.add(membership)
        
        await self.db.commit()
        
        logger.info(
            "Role assigned",
            user_id=str(request.user_id),
            org_id=str(request.organization_id),
            role=request.role_code,
        )
        
        return {
            "message": "Rol başarıyla atandı",
            "user_id": str(request.user_id),
            "organization_id": str(request.organization_id),
            "role": request.role_code,
        }
    
    async def assign_permissions(self, request: AssignPermissionsRequest) -> dict:
        """Kullanıcıya yetki ata."""
        # Kullanıcıyı kontrol et
        user = await self.get_user_by_id(request.user_id)
        if not user:
            raise NotFoundError("User", request.user_id)
        
        # Organizasyonu kontrol et
        org = await self.get_organization_by_id(request.organization_id)
        if not org:
            raise NotFoundError("Organization", request.organization_id)
        
        # Mevcut üyeliği kontrol et
        stmt = select(OrganizationUser).where(
            OrganizationUser.user_id == request.user_id,
            OrganizationUser.organization_id == request.organization_id,
        )
        result = await self.db.execute(stmt)
        membership = result.scalar_one_or_none()
        
        if not membership:
            raise NotFoundError("Membership", f"{request.user_id}/{request.organization_id}")
        
        if not membership.role:
            raise ConflictError("User has no role assigned")
        
        # Mevcut rol yetkilerine ek yetkileri ekle
        current_permissions = membership.role.permissions or []
        new_permissions = list(set(current_permissions + request.permissions))
        membership.role.permissions = new_permissions
        
        await self.db.commit()
        
        logger.info(
            "Permissions assigned",
            user_id=str(request.user_id),
            org_id=str(request.organization_id),
            permissions=request.permissions,
        )
        
        return {
            "message": "Yetkiler başarıyla atandı",
            "user_id": str(request.user_id),
            "organization_id": str(request.organization_id),
            "permissions": new_permissions,
        }
    
    def get_available_roles(self) -> AvailableRolesResponse:
        """Sistemdeki tüm rolleri döner."""
        roles = [
            {
                "code": RoleType.ADMIN.value,
                "name": "Admin",
                "description": "Sistem yöneticisi - tüm yetkiler",
                "permissions": ROLE_PERMISSIONS[RoleType.ADMIN.value],
            },
            {
                "code": RoleType.TENANT.value,
                "name": "Tenant",
                "description": "Organizasyon yöneticisi",
                "permissions": ROLE_PERMISSIONS[RoleType.TENANT.value],
            },
            {
                "code": RoleType.USER.value,
                "name": "User",
                "description": "Normal kullanıcı - salt okunur",
                "permissions": ROLE_PERMISSIONS[RoleType.USER.value],
            },
            {
                "code": RoleType.DEVICE.value,
                "name": "Device",
                "description": "Cihaz/Telemetri erişimi",
                "permissions": ROLE_PERMISSIONS[RoleType.DEVICE.value],
            },
        ]
        return AvailableRolesResponse(roles=roles)
    
    def get_available_permissions(self) -> AvailablePermissionsResponse:
        """Sistemdeki tüm yetkileri döner."""
        permissions = [
            {"code": p.value, "description": p.value.replace(":", " ").replace("_", " ").title()}
            for p in Permission
        ]
        return AvailablePermissionsResponse(permissions=permissions)
    
    # ============== Module Operations ==============
    
    def get_available_modules(self) -> AvailableModulesResponse:
        """Sistemdeki tüm modülleri döner."""
        module_names = {
            ModuleType.CORE.value: "Core",
            ModuleType.ASSET_MANAGEMENT.value: "Asset Management",
            ModuleType.IOT.value: "IoT",
            ModuleType.TELEMETRY.value: "Telemetry",
            ModuleType.ENERGY.value: "Energy",
            ModuleType.REWARDS.value: "Rewards",
            ModuleType.BILLING.value: "Billing",
            ModuleType.COMPLIANCE.value: "Compliance",
            ModuleType.NOTIFICATIONS.value: "Notifications",
            ModuleType.DASHBOARD.value: "Dashboard",
        }
        
        module_descriptions = {
            ModuleType.CORE.value: "Temel özellikler (auth, org, user)",
            ModuleType.ASSET_MANAGEMENT.value: "Asset ve Zone yönetimi",
            ModuleType.IOT.value: "Gateway ve cihaz yönetimi",
            ModuleType.TELEMETRY.value: "Telemetri verileri",
            ModuleType.ENERGY.value: "EPİAŞ, Recommendation, Core Loop",
            ModuleType.REWARDS.value: "AWX puan sistemi, Ledger",
            ModuleType.BILLING.value: "Cüzdan ve işlemler",
            ModuleType.COMPLIANCE.value: "KVKK/GDPR, Audit logs",
            ModuleType.NOTIFICATIONS.value: "Push, Telegram, Email bildirimleri",
            ModuleType.DASHBOARD.value: "Analitik ve raporlar",
        }
        
        modules = [
            ModuleInfo(
                code=m.value,
                name=module_names.get(m.value, m.value),
                description=module_descriptions.get(m.value),
                permissions=MODULE_PERMISSIONS.get(m.value, []),
            )
            for m in ModuleType
        ]
        return AvailableModulesResponse(modules=modules)
    
    async def create_organization_step1(
        self,
        request: CreateOrganizationStep1Request,
    ) -> CreateOrganizationStep1Response:
        """
        Step 1: Organizasyon oluştur.
        Admin UI'dan organizasyon bilgilerini girer.
        """
        # Slug oluştur
        slug = request.slug
        if not slug:
            slug = request.name.lower().replace(" ", "-").replace("'", "")
        
        # Slug kontrolü
        existing_org = await self.get_organization_by_slug(slug)
        if existing_org:
            slug = f"{slug}-{uuid.uuid4().hex[:6]}"
        
        # Organizasyon oluştur
        org = Organization(
            name=request.name,
            slug=slug,
            description=request.description,
            email=request.email,
            phone=request.phone,
            address=request.address,
            is_active=True,
        )
        self.db.add(org)
        await self.db.commit()
        await self.db.refresh(org)
        
        logger.info("Organization created (Step 1)", org_id=str(org.id), name=request.name)
        
        return CreateOrganizationStep1Response(
            message="Organizasyon oluşturuldu. Şimdi modülleri atayın.",
            organization=OrganizationResponse.model_validate(org),
        )
    
    async def create_organization_step2(
        self,
        request: CreateOrganizationStep2Request,
    ) -> CreateOrganizationStep2Response:
        """
        Step 2: Organizasyona modül ata.
        Admin organizasyona hangi modüllerin aktif olacağını seçer.
        """
        # Organizasyonu kontrol et
        org = await self.get_organization_by_id(request.organization_id)
        if not org:
            raise NotFoundError("Organization", request.organization_id)
        
        # Core modülü her zaman ekle
        modules_to_add = set(request.modules)
        modules_to_add.add(ModuleType.CORE.value)
        
        # Modülleri ekle
        now = datetime.now(timezone.utc)
        for module_code in modules_to_add:
            # Modül kodu geçerli mi kontrol et
            if module_code not in [m.value for m in ModuleType]:
                logger.warning("Invalid module code", module_code=module_code)
                continue
            
            # Mevcut modül var mı kontrol et
            stmt = select(OrganizationModule).where(
                OrganizationModule.organization_id == org.id,
                OrganizationModule.module_code == module_code,
            )
            result = await self.db.execute(stmt)
            existing = result.scalar_one_or_none()
            
            if not existing:
                org_module = OrganizationModule(
                    organization_id=org.id,
                    module_code=module_code,
                    is_active=True,
                    activated_at=now,
                )
                self.db.add(org_module)
        
        await self.db.commit()
        await self.db.refresh(org)
        
        # Modülleri yeniden yükle
        stmt = select(OrganizationModule).where(
            OrganizationModule.organization_id == org.id
        )
        result = await self.db.execute(stmt)
        org_modules = result.scalars().all()
        
        logger.info(
            "Modules assigned to organization (Step 2)",
            org_id=str(org.id),
            modules=[m.module_code for m in org_modules],
        )
        
        return CreateOrganizationStep2Response(
            message="Modüller atandı. Şimdi kullanıcı ekleyebilirsiniz.",
            organization=OrganizationWithModulesResponse(
                id=org.id,
                name=org.name,
                slug=org.slug,
                modules=[OrganizationModuleResponse.model_validate(m) for m in org_modules],
            ),
        )
    
    async def add_user_to_organization(
        self,
        request: AddUserToOrganizationRequest,
    ) -> AddUserToOrganizationResponse:
        """
        Organizasyona kullanıcı ekle.
        Admin birden fazla kullanıcı ekleyebilir.
        """
        # Organizasyonu kontrol et
        org = await self.get_organization_by_id(request.organization_id)
        if not org:
            raise NotFoundError("Organization", request.organization_id)
        
        # Email kontrolü - mevcut kullanıcı var mı?
        existing_user = await self.get_user_by_email(request.email)
        
        if existing_user:
            # Kullanıcı zaten bu organizasyonda mı?
            stmt = select(OrganizationUser).where(
                OrganizationUser.user_id == existing_user.id,
                OrganizationUser.organization_id == org.id,
            )
            result = await self.db.execute(stmt)
            existing_membership = result.scalar_one_or_none()
            
            if existing_membership:
                raise ConflictError(f"User {request.email} is already a member of this organization")
            
            user = existing_user
        else:
            # Yeni kullanıcı oluştur
            user = User(
                email=request.email,
                full_name=request.full_name,
                phone=request.phone,
                is_active=True,
                is_verified=False,
                onboarding_completed=False,
            )
            self.db.add(user)
            await self.db.flush()
        
        # Rol al veya oluştur
        role = await self._get_or_create_role(request.role)
        
        # Kullanıcıyı organizasyona ekle
        membership = OrganizationUser(
            user_id=user.id,
            organization_id=org.id,
            role_id=role.id,
            is_default=not existing_user,  # Yeni kullanıcı için varsayılan org
            joined_at=datetime.now(timezone.utc),
        )
        self.db.add(membership)
        
        await self.db.commit()
        await self.db.refresh(user)
        
        logger.info(
            "User added to organization",
            user_id=str(user.id),
            org_id=str(org.id),
            role=request.role,
        )
        
        return AddUserToOrganizationResponse(
            message="Kullanıcı organizasyona eklendi",
            user=UserResponse.model_validate(user),
            organization=OrganizationResponse.model_validate(org),
            role=request.role,
        )
    
    # ============== Onboarding Operations ==============
    
    async def complete_onboarding(
        self,
        user: User,
        request: OnboardingRequest,
    ) -> OnboardingResponse:
        """
        Kullanıcı onboarding bilgilerini tamamla.
        Auth0 sync sonrası kullanıcı bu bilgileri doldurur.
        """
        # Kişisel bilgileri güncelle
        if request.first_name:
            user.first_name = request.first_name
        if request.last_name:
            user.last_name = request.last_name
        if request.first_name and request.last_name:
            user.full_name = f"{request.first_name} {request.last_name}"
        if request.phone:
            user.phone = request.phone
        if request.telegram_username:
            user.telegram_username = request.telegram_username
        
        # Adres bilgilerini güncelle
        if request.address:
            user.country = request.address.country
            user.city = request.address.city
            user.district = request.address.district
            user.address = request.address.address
            user.postal_code = request.address.postal_code
        
        # Bildirim ayarlarını güncelle
        if request.notification_settings:
            user.notification_settings = request.notification_settings.model_dump()
        
        # KVKK onaylarını güncelle
        if request.consent_settings:
            user.consent_settings = request.consent_settings.model_dump()
        
        # FCM token güncelle
        if request.fcm_token:
            user.fcm_token = request.fcm_token
        
        # Onboarding tamamlandı
        user.onboarding_completed = True
        user.onboarding_step = None
        
        await self.db.commit()
        await self.db.refresh(user)
        
        logger.info("Onboarding completed", user_id=str(user.id))
        
        me_response = await self._build_me_response(user)
        
        return OnboardingResponse(
            message="Onboarding tamamlandı",
            onboarding_completed=True,
            onboarding_step=None,
            user=me_response,
        )
    
    async def update_onboarding_step(
        self,
        user: User,
        step: int,
    ) -> dict:
        """Onboarding adımını güncelle."""
        user.onboarding_step = step
        await self.db.commit()
        
        return {"message": "Onboarding step updated", "step": step}
    
    async def get_organization_modules(
        self,
        organization_id: uuid.UUID,
    ) -> list[str]:
        """Organizasyonun aktif modüllerini döner."""
        stmt = select(OrganizationModule).where(
            OrganizationModule.organization_id == organization_id,
            OrganizationModule.is_active == True,
        )
        result = await self.db.execute(stmt)
        modules = result.scalars().all()
        
        return [m.module_code for m in modules]
    
    # ============== Admin Operations ==============
    
    async def list_all_organizations(
        self,
        page: int = 1,
        page_size: int = 20,
        search: str | None = None,
        is_active: bool | None = None,
    ):
        """Tüm organizasyonları listele (Admin için)."""
        from sqlalchemy import func
        from src.modules.auth.schemas import AdminOrganizationListItem, AdminOrganizationListResponse
        
        # Base query
        stmt = select(Organization)
        count_stmt = select(func.count(Organization.id))
        
        # Filters
        if search:
            stmt = stmt.where(
                (Organization.name.ilike(f"%{search}%")) |
                (Organization.slug.ilike(f"%{search}%"))
            )
            count_stmt = count_stmt.where(
                (Organization.name.ilike(f"%{search}%")) |
                (Organization.slug.ilike(f"%{search}%"))
            )
        
        if is_active is not None:
            stmt = stmt.where(Organization.is_active == is_active)
            count_stmt = count_stmt.where(Organization.is_active == is_active)
        
        # Total count
        total_result = await self.db.execute(count_stmt)
        total = total_result.scalar() or 0
        
        # Pagination
        offset = (page - 1) * page_size
        stmt = stmt.offset(offset).limit(page_size).order_by(Organization.created_at.desc())
        
        result = await self.db.execute(stmt)
        organizations = result.scalars().all()
        
        # Build response with counts
        items = []
        for org in organizations:
            # User count
            user_count_stmt = select(func.count(OrganizationUser.id)).where(
                OrganizationUser.organization_id == org.id
            )
            user_count_result = await self.db.execute(user_count_stmt)
            user_count = user_count_result.scalar() or 0
            
            # Modules
            modules = await self.get_organization_modules(org.id)
            
            items.append(AdminOrganizationListItem(
                id=org.id,
                name=org.name,
                slug=org.slug,
                email=org.email,
                is_active=org.is_active,
                created_at=org.created_at,
                user_count=user_count,
                device_count=0,  # TODO: Device count
                modules=modules,
            ))
        
        return AdminOrganizationListResponse(
            organizations=items,
            total=total,
            page=page,
            page_size=page_size,
        )
    
    async def get_organization_detail(self, org_id: str):
        """Organizasyon detayını getir (Admin için)."""
        from src.modules.auth.schemas import (
            AdminOrganizationDetailResponse,
            AdminUserListItem,
            OrganizationResponse,
            RoleInfo,
        )
        
        org = await self.get_organization_by_id(uuid.UUID(org_id))
        if not org:
            raise NotFoundError("Organization not found")
        
        # Get users
        stmt = (
            select(OrganizationUser)
            .options(selectinload(OrganizationUser.user), selectinload(OrganizationUser.role))
            .where(OrganizationUser.organization_id == org.id)
        )
        result = await self.db.execute(stmt)
        memberships = result.scalars().all()
        
        users = []
        for m in memberships:
            if m.user:
                role_info = None
                if m.role:
                    role_info = RoleInfo(code=m.role.code, name=m.role.name)
                
                users.append(AdminUserListItem(
                    id=m.user.id,
                    email=m.user.email,
                    full_name=m.user.full_name,
                    phone=m.user.phone,
                    is_active=m.user.is_active,
                    created_at=m.user.created_at,
                    last_login=m.user.last_login,
                    role=role_info,
                    organization=None,
                ))
        
        # Modules
        modules = await self.get_organization_modules(org.id)
        
        return AdminOrganizationDetailResponse(
            organization=OrganizationResponse.model_validate(org),
            users=users,
            modules=modules,
            device_count=0,
            gateway_count=0,
            asset_count=0,
        )
    
    async def list_all_users(
        self,
        page: int = 1,
        page_size: int = 20,
        search: str | None = None,
        role: str | None = None,
        organization_id: str | None = None,
        is_active: bool | None = None,
    ):
        """Tüm kullanıcıları listele (Admin için)."""
        from sqlalchemy import func
        from src.modules.auth.schemas import AdminUserListItem, AdminUserListResponse, RoleInfo, OrganizationResponse
        
        # Base query with eager loading
        stmt = (
            select(User)
            .options(
                selectinload(User.organization_memberships)
                .selectinload(OrganizationUser.role),
                selectinload(User.organization_memberships)
                .selectinload(OrganizationUser.organization),
            )
        )
        count_stmt = select(func.count(User.id))
        
        # Filters
        if search:
            stmt = stmt.where(
                (User.email.ilike(f"%{search}%")) |
                (User.full_name.ilike(f"%{search}%"))
            )
            count_stmt = count_stmt.where(
                (User.email.ilike(f"%{search}%")) |
                (User.full_name.ilike(f"%{search}%"))
            )
        
        if is_active is not None:
            stmt = stmt.where(User.is_active == is_active)
            count_stmt = count_stmt.where(User.is_active == is_active)
        
        # Total count
        total_result = await self.db.execute(count_stmt)
        total = total_result.scalar() or 0
        
        # Pagination
        offset = (page - 1) * page_size
        stmt = stmt.offset(offset).limit(page_size).order_by(User.created_at.desc())
        
        result = await self.db.execute(stmt)
        users = result.scalars().all()
        
        # Build response
        items = []
        for user in users:
            role_info = None
            org_response = None
            
            for m in user.organization_memberships:
                if m.is_default:
                    if m.role:
                        role_info = RoleInfo(code=m.role.code, name=m.role.name)
                    if m.organization:
                        org_response = OrganizationResponse.model_validate(m.organization)
                    break
            
            items.append(AdminUserListItem(
                id=user.id,
                email=user.email,
                full_name=user.full_name,
                phone=user.phone,
                is_active=user.is_active,
                created_at=user.created_at,
                last_login=user.last_login,
                role=role_info,
                organization=org_response,
            ))
        
        return AdminUserListResponse(
            users=items,
            total=total,
            page=page,
            page_size=page_size,
        )
    
    async def list_all_roles(self):
        """Tüm rolleri listele (Admin için)."""
        from src.modules.auth.schemas import AdminRoleListResponse, RoleResponse
        
        stmt = select(Role).order_by(Role.code)
        result = await self.db.execute(stmt)
        roles = result.scalars().all()
        
        return AdminRoleListResponse(
            roles=[RoleResponse.model_validate(r) for r in roles],
            total=len(roles),
        )
    
    async def list_all_permissions(self):
        """Tüm yetkileri listele (Admin için)."""
        from src.modules.auth.schemas import AdminPermissionListResponse
        
        permissions = [p.value for p in Permission]
        
        return AdminPermissionListResponse(
            permissions=permissions,
            total=len(permissions),
        )
    
    async def assign_role_to_user(self, user_id: str, request):
        """Kullanıcıya rol ata (Admin için)."""
        from src.modules.auth.schemas import AssignRoleToUserResponse, RoleInfo
        
        user = await self.get_user_by_id(uuid.UUID(user_id))
        if not user:
            raise NotFoundError("User not found")
        
        # Get role
        role = await self._get_or_create_role(request.role_code)
        
        # Find membership
        target_org_id = request.organization_id
        membership = None
        
        for m in user.organization_memberships:
            if target_org_id:
                if m.organization_id == target_org_id:
                    membership = m
                    break
            elif m.is_default:
                membership = m
                target_org_id = m.organization_id
                break
        
        if not membership:
            raise NotFoundError("User membership not found")
        
        # Update role
        membership.role_id = role.id
        await self.db.commit()
        
        return AssignRoleToUserResponse(
            message=f"Rol '{request.role_code}' kullanıcıya atandı",
            user_id=user.id,
            role=RoleInfo(code=role.code, name=role.name),
            organization_id=target_org_id,
        )
    
    async def add_user_to_organization_direct(self, org_id: str, request):
        """Organizasyona doğrudan kullanıcı ekle (Admin için)."""
        from src.modules.auth.schemas import AddUserToOrgDirectResponse, AdminUserListItem, RoleInfo
        
        org = await self.get_organization_by_id(uuid.UUID(org_id))
        if not org:
            raise NotFoundError("Organization not found")
        
        # Get or create user
        if request.user_id:
            user = await self.get_user_by_id(request.user_id)
            if not user:
                raise NotFoundError("User not found")
        else:
            user = await self.get_user_by_email(request.email)
            if not user:
                # Create new user
                user = User(
                    email=request.email,
                    full_name=request.full_name,
                    is_active=True,
                )
                self.db.add(user)
                await self.db.flush()
        
        # Get role
        role = await self._get_or_create_role(request.role_code)
        
        # Check if already member
        existing = None
        for m in user.organization_memberships:
            if m.organization_id == org.id:
                existing = m
                break
        
        if existing:
            # Update role
            existing.role_id = role.id
        else:
            # Add membership
            membership = OrganizationUser(
                user_id=user.id,
                organization_id=org.id,
                role_id=role.id,
                is_default=len(user.organization_memberships) == 0,
                joined_at=datetime.now(timezone.utc),
            )
            self.db.add(membership)
        
        await self.db.commit()
        await self.db.refresh(user)
        
        role_info = RoleInfo(code=role.code, name=role.name)
        
        return AddUserToOrgDirectResponse(
            message=f"Kullanıcı organizasyona eklendi",
            user=AdminUserListItem(
                id=user.id,
                email=user.email,
                full_name=user.full_name,
                phone=user.phone,
                is_active=user.is_active,
                created_at=user.created_at,
                last_login=user.last_login,
                role=role_info,
                organization=None,
            ),
            organization_id=org.id,
            role=request.role_code,
        )
