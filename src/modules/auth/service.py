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
    
    async def delete_organization(
        self,
        org_id: uuid.UUID,
        hard_delete: bool = False,
    ) -> dict:
        """
        Delete organization (Admin only).
        
        Args:
            org_id: Organization ID to delete
            hard_delete: If True, permanently delete. If False, soft delete (is_active=False)
        
        Returns:
            Status dict with deleted organization info
            
        KRITIK: Bu işlem sadece Admin yetkisiyle yapılabilir.
        Soft delete varsayılan davranıştır (veri kaybını önlemek için).
        """
        org = await self.get_organization_by_id(org_id)
        if not org:
            raise NotFoundError("Organization", org_id)
        
        org_name = org.name
        org_slug = org.slug
        
        if hard_delete:
            # Hard delete - tüm ilişkili veriler cascade ile silinir
            # DİKKAT: Bu işlem geri alınamaz!
            await self.db.delete(org)
            await self.db.commit()
            
            logger.warning(
                "Organization HARD DELETED",
                org_id=str(org_id),
                org_name=org_name,
                org_slug=org_slug,
            )
            
            return {
                "status": "deleted",
                "method": "hard_delete",
                "organization_id": str(org_id),
                "organization_name": org_name,
                "message": f"Organizasyon '{org_name}' kalıcı olarak silindi",
            }
        else:
            # Soft delete - sadece is_active=False yapılır
            org.is_active = False
            await self.db.commit()
            
            logger.info(
                "Organization soft deleted",
                org_id=str(org_id),
                org_name=org_name,
            )
            
            return {
                "status": "deactivated",
                "method": "soft_delete",
                "organization_id": str(org_id),
                "organization_name": org_name,
                "message": f"Organizasyon '{org_name}' devre dışı bırakıldı",
            }
    
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
        """Get user by Auth0 ID with all relationships loaded."""
        from src.modules.auth.models import OrganizationUser, Role
        stmt = (
            select(User)
            .options(
                selectinload(User.organization_memberships)
                .selectinload(OrganizationUser.role),
                selectinload(User.organization_memberships)
                .selectinload(OrganizationUser.organization),
            )
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
        from src.modules.auth.schemas import UserWalletInfo
        
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
        
        # Kullanıcının AWX wallet bilgisini al
        wallet_info = await self._get_user_wallet_info(user.id)
        
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
            wallet=wallet_info,
            onboarding_completed=user.onboarding_completed,
            onboarding_step=user.onboarding_step,
            is_active=user.is_active,
            created_at=user.created_at,
        )
    
    async def _get_user_wallet_info(self, user_id: uuid.UUID) -> "UserWalletInfo | None":
        """Kullanıcının AWX wallet bilgisini getir."""
        from src.modules.auth.schemas import UserWalletInfo
        
        try:
            from src.modules.billing.models import Wallet, WalletType
            
            stmt = select(Wallet).where(
                Wallet.user_id == user_id,
                Wallet.wallet_type == WalletType.PERSONAL,
                Wallet.currency == "AWX",
            )
            result = await self.db.execute(stmt)
            wallet = result.scalar_one_or_none()
            
            if wallet:
                return UserWalletInfo(
                    balance=str(wallet.balance),
                    currency=wallet.currency,
                    has_wallet=True,
                )
            
            return UserWalletInfo(
                balance="0.00",
                currency="AWX",
                has_wallet=False,
            )
        except Exception as e:
            logger.warning(f"Could not get user wallet info: {e}")
            return None
    
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
        Tab 1: Organizasyon ve ilk kullanıcı (tenant owner) birlikte oluşturma.
        Organizasyon oluşturulur ve belirtilen kullanıcı tenant rolüyle eklenir.
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
        
        # Organizasyon oluştur (detaylı adres ve tip bilgileriyle)
        org = Organization(
            name=request.organization_name,
            slug=slug,
            description=request.organization_description,
            organization_type=request.organization_type.value if request.organization_type else None,
            company_size=request.company_size,
            email=request.organization_email,
            phone=request.organization_phone,
            # Detaylı adres
            city=request.city,
            district=request.district,
            neighborhood=request.neighborhood,
            street=request.street,
            postal_code=request.postal_code,
            country=request.country,
            # Koordinatlar
            latitude=request.latitude,
            longitude=request.longitude,
            is_active=True,
        )
        self.db.add(org)
        await self.db.flush()
        
        # Kullanıcı oluştur (first_name + last_name)
        full_name = f"{request.user_first_name} {request.user_last_name}"
        user = User(
            email=request.user_email,
            full_name=full_name,
            first_name=request.user_first_name,
            last_name=request.user_last_name,
            phone=request.user_phone,
            is_active=True,
            is_verified=False,
        )
        self.db.add(user)
        await self.db.flush()
        
        # Rol al veya oluştur (varsayılan: tenant)
        role = await self._get_or_create_role(request.user_role)
        
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
            
            # Device count
            try:
                from src.modules.iot.models import Device
                device_count_stmt = select(func.count(Device.id)).where(
                    Device.organization_id == org.id
                )
                device_count_result = await self.db.execute(device_count_stmt)
                device_count = device_count_result.scalar() or 0
            except Exception:
                device_count = 0
            
            items.append(AdminOrganizationListItem(
                id=org.id,
                name=org.name,
                slug=org.slug,
                email=org.email,
                is_active=org.is_active,
                created_at=org.created_at,
                user_count=user_count,
                device_count=device_count,
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
        
        # Wallet özeti
        wallet_summary = await self._get_organization_wallet_summary(org.id)
        
        return AdminOrganizationDetailResponse(
            organization=OrganizationResponse.model_validate(org),
            users=users,
            modules=modules,
            device_count=0,
            gateway_count=0,
            asset_count=0,
            wallet_summary=wallet_summary,
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
    
    async def list_organization_users(
        self,
        organization_id: str,
        page: int = 1,
        page_size: int = 20,
        search: str | None = None,
        role: str | None = None,
        is_active: bool | None = None,
    ):
        """Organizasyondaki kullanıcıları listele."""
        from sqlalchemy import func
        from src.modules.auth.schemas import AdminUserListItem, AdminUserListResponse, RoleInfo, OrganizationResponse
        
        # Base query - sadece belirtilen organizasyondaki kullanıcılar
        stmt = (
            select(User)
            .join(OrganizationUser)
            .where(OrganizationUser.organization_id == organization_id)
            .options(
                selectinload(User.organization_memberships)
                .selectinload(OrganizationUser.role),
                selectinload(User.organization_memberships)
                .selectinload(OrganizationUser.organization),
            )
        )
        count_stmt = (
            select(func.count(User.id))
            .join(OrganizationUser)
            .where(OrganizationUser.organization_id == organization_id)
        )
        
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
        
        if role:
            stmt = stmt.join(OrganizationUser.role).where(Role.code == role)
            count_stmt = count_stmt.join(OrganizationUser.role).where(Role.code == role)
        
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
            
            # Bu organizasyondaki üyeliği bul
            for m in user.organization_memberships:
                if m.organization_id == organization_id:
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
    
    async def get_organization_stats(self, organization_id: str):
        """Organizasyon istatistiklerini getir (wallet bilgileri dahil)."""
        from sqlalchemy import func
        from datetime import datetime, timedelta
        from decimal import Decimal
        
        # UUID kontrolü
        try:
            org_uuid = uuid.UUID(organization_id)
        except ValueError:
            raise NotFoundError("Invalid organization ID")
        
        # Organizasyon var mı?
        org = await self.get_organization_by_id(org_uuid)
        if not org:
            raise NotFoundError("Organization not found")
        
        # Kullanıcı istatistikleri
        total_users_stmt = (
            select(func.count(User.id))
            .join(OrganizationUser)
            .where(OrganizationUser.organization_id == org_uuid)
        )
        
        active_users_stmt = (
            select(func.count(User.id))
            .join(OrganizationUser)
            .where(
                OrganizationUser.organization_id == org_uuid,
                User.is_active == True
            )
        )
        
        # Rol bazında kullanıcı dağılımı
        role_distribution_stmt = (
            select(Role.code, func.count(User.id))
            .join(OrganizationUser, Role.id == OrganizationUser.role_id)
            .join(User, User.id == OrganizationUser.user_id)
            .where(OrganizationUser.organization_id == org_uuid)
            .group_by(Role.code)
        )
        
        # Son 30 gün aktivite
        thirty_days_ago = datetime.now(timezone.utc) - timedelta(days=30)
        recent_activity_stmt = (
            select(func.count(User.id))
            .join(OrganizationUser)
            .where(
                OrganizationUser.organization_id == org_uuid,
                User.last_login >= thirty_days_ago
            )
        )
        
        # Sorguları çalıştır
        total_users_result = await self.db.execute(total_users_stmt)
        active_users_result = await self.db.execute(active_users_stmt)
        role_dist_result = await self.db.execute(role_distribution_stmt)
        recent_activity_result = await self.db.execute(recent_activity_stmt)
        
        total_users = total_users_result.scalar() or 0
        active_users = active_users_result.scalar() or 0
        recent_activity = recent_activity_result.scalar() or 0
        
        # Rol dağılımı
        role_distribution = {}
        for row in role_dist_result:
            role_distribution[row[0]] = row[1]
        
        # Wallet bilgilerini getir
        wallet_summary = await self._get_organization_wallet_summary(org_uuid)
        
        # Device count
        try:
            from src.modules.iot.models import Device
            device_count_stmt = select(func.count(Device.id)).where(
                Device.organization_id == org_uuid
            )
            device_count_result = await self.db.execute(device_count_stmt)
            device_count = device_count_result.scalar() or 0
        except Exception:
            device_count = 0
        
        # Asset count
        try:
            from src.modules.real_estate.models import Asset
            asset_count_stmt = select(func.count(Asset.id)).where(
                Asset.organization_id == org_uuid
            )
            asset_count_result = await self.db.execute(asset_count_stmt)
            asset_count = asset_count_result.scalar() or 0
        except Exception:
            asset_count = 0
        
        return {
            "organization_id": organization_id,
            "organization_name": org.name,
            "total_users": total_users,
            "active_users": active_users,
            "inactive_users": total_users - active_users,
            "role_distribution": role_distribution,
            "recent_activity_30_days": recent_activity,
            "device_count": device_count,
            "asset_count": asset_count,
            "wallet_summary": wallet_summary,
        }
    
    async def _get_organization_wallet_summary(self, org_uuid: uuid.UUID) -> dict:
        """Organizasyonun COMPANY wallet özetini getir."""
        from sqlalchemy import func
        from decimal import Decimal
        from src.modules.auth.schemas import OrganizationWalletSummary
        
        try:
            from src.modules.billing.models import Wallet, WalletType
            
            # Sadece COMPANY wallet'ları getir
            wallet_stmt = select(Wallet).where(
                Wallet.organization_id == org_uuid,
                Wallet.wallet_type == WalletType.COMPANY,
            )
            wallet_result = await self.db.execute(wallet_stmt)
            wallets = wallet_result.scalars().all()
            
            if not wallets:
                return OrganizationWalletSummary(
                    wallet_count=0,
                    balances={},
                    total_balance_try="0.00",
                )
            
            # Bakiye özeti
            balances = {}
            total_try = Decimal("0")
            for w in wallets:
                balances[w.currency] = str(w.balance)
                if w.currency == "TRY":
                    total_try = w.balance
            
            return OrganizationWalletSummary(
                wallet_count=len(wallets),
                balances=balances,
                total_balance_try=str(total_try),
            )
        except Exception as e:
            logger.warning(f"Could not get wallet summary: {e}")
            return OrganizationWalletSummary(
                wallet_count=0,
                balances={},
                total_balance_try="0.00",
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
    
    # ============== Admin Operations (L7 Enterprise Features) ==============
    
    async def suspend_organization(
        self,
        org_id: uuid.UUID,
        reason: str | None = None,
    ) -> dict:
        """
        Suspend organization (Admin only).
        
        Faturasını ödemeyen veya TOS ihlali yapan organizasyonu askıya alır.
        Kullanıcılar giriş yapamaz ama veriler silinmez.
        """
        org = await self.get_organization_by_id(org_id)
        if not org:
            raise NotFoundError("Organization", org_id)
        
        org.status = "suspended"
        org.suspended_at = datetime.now(timezone.utc)
        org.suspended_reason = reason
        org.is_active = False
        
        await self.db.commit()
        
        logger.warning(
            "Organization suspended",
            org_id=str(org_id),
            org_name=org.name,
            reason=reason,
        )
        
        return {
            "status": "suspended",
            "organization_id": str(org_id),
            "organization_name": org.name,
            "suspended_at": org.suspended_at.isoformat(),
            "reason": reason,
            "message": f"Organizasyon '{org.name}' askıya alındı",
        }
    
    async def reactivate_organization(
        self,
        org_id: uuid.UUID,
    ) -> dict:
        """
        Reactivate suspended organization (Admin only).
        """
        org = await self.get_organization_by_id(org_id)
        if not org:
            raise NotFoundError("Organization", org_id)
        
        org.status = "active"
        org.suspended_at = None
        org.suspended_reason = None
        org.is_active = True
        
        await self.db.commit()
        
        logger.info(
            "Organization reactivated",
            org_id=str(org_id),
            org_name=org.name,
        )
        
        return {
            "status": "active",
            "organization_id": str(org_id),
            "organization_name": org.name,
            "message": f"Organizasyon '{org.name}' yeniden aktifleştirildi",
        }
    
    async def transfer_organization_ownership(
        self,
        org_id: uuid.UUID,
        new_owner_user_id: uuid.UUID,
    ) -> dict:
        """
        Transfer organization ownership to another user (Admin only).
        
        Şirketin IT müdürü işten ayrıldığında tenant admin yetkisini
        başka bir kullanıcıya devretmek için kullanılır.
        """
        org = await self.get_organization_by_id(org_id)
        if not org:
            raise NotFoundError("Organization", org_id)
        
        new_owner = await self.get_user_by_id(new_owner_user_id)
        if not new_owner:
            raise NotFoundError("User", new_owner_user_id)
        
        # Get tenant role
        tenant_role = await self._get_or_create_tenant_role()
        
        # Find current owner (tenant role with is_default=True)
        current_owner_membership = None
        new_owner_membership = None
        
        for m in org.members:
            if m.role_id == tenant_role.id and m.is_default:
                current_owner_membership = m
            if m.user_id == new_owner_user_id:
                new_owner_membership = m
        
        # Demote current owner to user role
        if current_owner_membership:
            user_role = await self._get_or_create_role(RoleType.USER.value)
            current_owner_membership.role_id = user_role.id
            current_owner_membership.is_default = False
        
        # Promote new owner to tenant role
        if new_owner_membership:
            new_owner_membership.role_id = tenant_role.id
            new_owner_membership.is_default = True
        else:
            # Add new owner to organization
            new_membership = OrganizationUser(
                user_id=new_owner_user_id,
                organization_id=org_id,
                role_id=tenant_role.id,
                is_default=True,
                joined_at=datetime.now(timezone.utc),
            )
            self.db.add(new_membership)
        
        await self.db.commit()
        
        logger.info(
            "Organization ownership transferred",
            org_id=str(org_id),
            new_owner_id=str(new_owner_user_id),
        )
        
        return {
            "status": "transferred",
            "organization_id": str(org_id),
            "organization_name": org.name,
            "new_owner_id": str(new_owner_user_id),
            "new_owner_email": new_owner.email,
            "message": f"Organizasyon sahipliği '{new_owner.email}' kullanıcısına devredildi",
        }
    
    async def revoke_user_sessions(
        self,
        user_id: uuid.UUID,
    ) -> dict:
        """
        Revoke all sessions for a user (Admin only).
        
        Kullanıcı hacklendiğinde veya cihazı çalındığında
        tüm tokenlarını iptal etmek için kullanılır.
        
        NOT: Auth0 kullanılıyorsa Auth0 Management API üzerinden
        session'lar iptal edilmelidir.
        """
        user = await self.get_user_by_id(user_id)
        if not user:
            raise NotFoundError("User", user_id)
        
        revoke_results = {
            "redis_blacklisted": False,
            "auth0_revoked": False,
        }
        
        # 1. Redis'te token'ları blacklist'e ekle
        try:
            from src.core.redis import get_redis
            redis = await get_redis()
            if redis:
                blacklist_key = f"token_blacklist:user:{user_id}"
                await redis.setex(blacklist_key, 86400, "revoked")
                revoke_results["redis_blacklisted"] = True
        except Exception as e:
            logger.warning(f"Redis blacklist failed: {e}")
        
        # 2. Auth0 Management API ile session iptal
        if user.auth0_id:
            try:
                from src.core.auth0 import get_auth0_management
                auth0_mgmt = get_auth0_management()
                if auth0_mgmt.is_configured:
                    result = await auth0_mgmt.revoke_user_sessions(user.auth0_id)
                    revoke_results["auth0_revoked"] = result.get("status") == "revoked"
            except Exception as e:
                logger.warning(f"Auth0 session revocation failed: {e}")
        
        logger.warning(
            "User sessions revoked",
            user_id=str(user_id),
            user_email=user.email,
            results=revoke_results,
        )
        
        return {
            "status": "revoked",
            "user_id": str(user_id),
            "user_email": user.email,
            "revoke_results": revoke_results,
            "message": f"'{user.email}' kullanıcısının tüm oturumları sonlandırıldı",
        }
    
    async def list_all_users_global(
        self,
        page: int = 1,
        page_size: int = 20,
        search: str | None = None,
        status: str | None = None,
        is_active: bool | None = None,
    ):
        """
        List ALL users across ALL organizations (Admin only - Global Search).
        
        Müşteri desteği için tüm sistemdeki kullanıcıları arayabilme.
        """
        from sqlalchemy import func, or_
        from src.modules.auth.schemas import AdminUserListResponse, AdminUserListItem, RoleInfo, OrganizationResponse
        
        # Base query
        base_query = select(User)
        count_query = select(func.count(User.id))
        
        # Search filter
        if search:
            search_filter = or_(
                User.email.ilike(f"%{search}%"),
                User.full_name.ilike(f"%{search}%"),
                User.phone.ilike(f"%{search}%"),
            )
            base_query = base_query.where(search_filter)
            count_query = count_query.where(search_filter)
        
        # Status filter
        if status:
            base_query = base_query.where(User.status == status)
            count_query = count_query.where(User.status == status)
        
        # Active filter
        if is_active is not None:
            base_query = base_query.where(User.is_active == is_active)
            count_query = count_query.where(User.is_active == is_active)
        
        # Get total count
        total_result = await self.db.execute(count_query)
        total = total_result.scalar() or 0
        
        # Apply pagination
        query = base_query.order_by(User.created_at.desc())
        query = query.offset((page - 1) * page_size).limit(page_size)
        query = query.options(
            selectinload(User.organization_memberships).selectinload(OrganizationUser.role),
            selectinload(User.organization_memberships).selectinload(OrganizationUser.organization),
        )
        
        result = await self.db.execute(query)
        users = result.scalars().all()
        
        # Build response
        items = []
        for user in users:
            role_info = None
            org_response = None
            
            # Get default organization and role
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
    
    async def ban_user(
        self,
        user_id: uuid.UUID,
        reason: str | None = None,
    ) -> dict:
        """
        Ban user from the system (Admin only).
        
        Kullanıcıyı sistemden kalıcı olarak yasaklar.
        """
        user = await self.get_user_by_id(user_id)
        if not user:
            raise NotFoundError("User", user_id)
        
        user.status = "banned"
        user.is_active = False
        
        await self.db.commit()
        
        # Revoke sessions
        await self.revoke_user_sessions(user_id)
        
        logger.warning(
            "User banned",
            user_id=str(user_id),
            user_email=user.email,
            reason=reason,
        )
        
        return {
            "status": "banned",
            "user_id": str(user_id),
            "user_email": user.email,
            "reason": reason,
            "message": f"'{user.email}' kullanıcısı yasaklandı",
        }
    
    # ============== Module Management (Upsell & Feature Flagging) ==============
    
    async def update_organization_modules(
        self,
        org_id: uuid.UUID,
        modules: list[dict],
    ) -> dict:
        """
        Update organization modules (Admin only).
        
        Bir müşteriye modül satışı veya deneme süresi yönetimi için kullanılır.
        - Yeni modül ekle
        - Mevcut modülü aktif/pasif yap
        - Deneme süresi ayarla
        - Modül ayarlarını güncelle
        """
        from src.modules.auth.schemas import OrganizationModulesUpdateResponse, OrganizationModuleResponse
        
        org = await self.get_organization_by_id(org_id)
        if not org:
            raise NotFoundError("Organization", org_id)
        
        now = datetime.now(timezone.utc)
        updated_modules = []
        
        for module_data in modules:
            module_code = module_data.get("module_code")
            is_active = module_data.get("is_active", True)
            trial_ends_at = module_data.get("trial_ends_at")
            settings = module_data.get("settings")
            
            # Modül kodu geçerli mi kontrol et
            if module_code not in [m.value for m in ModuleType]:
                logger.warning("Invalid module code", module_code=module_code)
                continue
            
            # Mevcut modül var mı kontrol et
            stmt = select(OrganizationModule).where(
                OrganizationModule.organization_id == org_id,
                OrganizationModule.module_code == module_code,
            )
            result = await self.db.execute(stmt)
            existing = result.scalar_one_or_none()
            
            if existing:
                # Güncelle
                existing.is_active = is_active
                if settings is not None:
                    existing.settings = settings
                updated_modules.append(existing)
            else:
                # Yeni modül ekle
                new_module = OrganizationModule(
                    organization_id=org_id,
                    module_code=module_code,
                    is_active=is_active,
                    activated_at=now,
                    settings=settings,
                )
                self.db.add(new_module)
                updated_modules.append(new_module)
        
        await self.db.commit()
        
        # Güncel modül listesini al
        stmt = select(OrganizationModule).where(
            OrganizationModule.organization_id == org_id
        )
        result = await self.db.execute(stmt)
        all_modules = result.scalars().all()
        
        active_modules = [m.module_code for m in all_modules if m.is_active]
        
        logger.info(
            "Organization modules updated",
            org_id=str(org_id),
            updated_count=len(updated_modules),
            active_modules=active_modules,
        )
        
        return OrganizationModulesUpdateResponse(
            message=f"{len(updated_modules)} modül güncellendi",
            organization_id=org_id,
            updated_modules=[OrganizationModuleResponse.model_validate(m) for m in updated_modules],
            active_modules=active_modules,
        )
    
    # ============== User Impersonation (Customer Support) ==============
    
    async def impersonate_user(
        self,
        admin_user: User,
        target_user_id: uuid.UUID,
        reason: str | None = None,
        duration_minutes: int = 60,
    ) -> dict:
        """
        Impersonate a user (Admin only).
        
        Müşteri hizmetleri için: Admin, kullanıcının gözünden sistemi görebilir.
        Geçici bir access token üretir.
        
        Security:
        - Sadece admin yapabilir
        - Audit log'a kaydedilir
        - Token süresi sınırlı (varsayılan 60 dakika, max 8 saat)
        - Token'da impersonation flag'i var
        """
        from src.modules.auth.schemas import ImpersonateUserResponse, UserResponse
        from src.core.security import create_access_token
        from datetime import timedelta
        
        target_user = await self.get_user_by_id(target_user_id)
        if not target_user:
            raise NotFoundError("User", target_user_id)
        
        if not target_user.is_active:
            raise UnauthorizedError("Cannot impersonate inactive user")
        
        # Get target user's default organization and role
        default_org_id = None
        role_code = None
        permissions: list[str] = []
        
        for membership in target_user.organization_memberships:
            if membership.is_default:
                default_org_id = membership.organization_id
                if membership.role:
                    role_code = membership.role.code
                    permissions = membership.role.permissions or []
                break
        
        # Create impersonation token with special claims
        expires_delta = timedelta(minutes=duration_minutes)
        expires_at = datetime.now(timezone.utc) + expires_delta
        
        token = create_access_token(
            subject=str(target_user.id),
            extra_claims={
                "org_id": str(default_org_id) if default_org_id else None,
                "role": role_code,
                "permissions": permissions,
                "impersonated_by": str(admin_user.id),
                "impersonation": True,
            },
            expires_delta=expires_delta,
        )
        
        logger.warning(
            "User impersonation started",
            admin_id=str(admin_user.id),
            admin_email=admin_user.email,
            target_user_id=str(target_user_id),
            target_email=target_user.email,
            reason=reason,
            duration_minutes=duration_minutes,
        )
        
        return ImpersonateUserResponse(
            message=f"'{target_user.email}' kullanıcısı olarak giriş yapıldı",
            impersonated_user=UserResponse.model_validate(target_user),
            access_token=token,
            expires_at=expires_at,
            admin_user_id=admin_user.id,
        )
    
    # ============== Enhanced Soft Delete with Cascade ==============
    
    async def delete_organization_with_cascade(
        self,
        org_id: uuid.UUID,
        hard_delete: bool = False,
    ) -> dict:
        """
        Delete organization with proper cascade handling (Admin only).
        
        Soft Delete durumunda:
        - Organizasyon is_active=False
        - Tüm kullanıcılar is_active=False (Zombi kullanıcı önleme)
        - IoT cihazları status='suspended'
        - Gateway'ler status='suspended'
        - Aktif faturalar status='cancelled'
        
        Hard Delete durumunda:
        - Tüm veriler CASCADE ile silinir (DB foreign key)
        """
        org = await self.get_organization_by_id(org_id)
        if not org:
            raise NotFoundError("Organization", org_id)
        
        org_name = org.name
        org_slug = org.slug
        
        if hard_delete:
            # Hard delete - CASCADE ile tüm ilişkili veriler silinir
            await self.db.delete(org)
            await self.db.commit()
            
            logger.warning(
                "Organization HARD DELETED with cascade",
                org_id=str(org_id),
                org_name=org_name,
            )
            
            return {
                "status": "deleted",
                "method": "hard_delete",
                "organization_id": str(org_id),
                "organization_name": org_name,
                "cascade_actions": ["all_data_deleted"],
                "message": f"Organizasyon '{org_name}' ve tüm verileri kalıcı olarak silindi",
            }
        
        # Soft delete with cascade
        cascade_results = {
            "users_deactivated": 0,
            "devices_suspended": 0,
            "gateways_suspended": 0,
        }
        
        # 1. Organizasyonu deaktif et
        org.is_active = False
        org.status = "deleted"
        
        # 2. Tüm kullanıcıları deaktif et (Zombi kullanıcı önleme)
        from sqlalchemy import update
        user_ids_stmt = select(OrganizationUser.user_id).where(
            OrganizationUser.organization_id == org_id
        )
        user_ids_result = await self.db.execute(user_ids_stmt)
        user_ids = [row[0] for row in user_ids_result.fetchall()]
        
        if user_ids:
            # Sadece bu organizasyona ait kullanıcıları deaktif et
            # (Birden fazla org'a üye olanlar için dikkatli ol)
            for user_id in user_ids:
                # Kullanıcının başka aktif organizasyonu var mı?
                other_orgs_stmt = select(OrganizationUser).where(
                    OrganizationUser.user_id == user_id,
                    OrganizationUser.organization_id != org_id,
                )
                other_orgs_result = await self.db.execute(other_orgs_stmt)
                other_orgs = other_orgs_result.scalars().all()
                
                # Başka aktif org yoksa kullanıcıyı deaktif et
                if not other_orgs:
                    user_update_stmt = (
                        update(User)
                        .where(User.id == user_id)
                        .values(is_active=False, status="org_deleted")
                    )
                    await self.db.execute(user_update_stmt)
                    cascade_results["users_deactivated"] += 1
        
        # 3. IoT cihazlarını suspend et
        try:
            from src.modules.iot.models import Device, Gateway
            
            device_update_stmt = (
                update(Device)
                .where(Device.organization_id == org_id)
                .values(status="suspended")
            )
            device_result = await self.db.execute(device_update_stmt)
            cascade_results["devices_suspended"] = device_result.rowcount
            
            gateway_update_stmt = (
                update(Gateway)
                .where(Gateway.organization_id == org_id)
                .values(status="suspended")
            )
            gateway_result = await self.db.execute(gateway_update_stmt)
            cascade_results["gateways_suspended"] = gateway_result.rowcount
        except ImportError:
            logger.debug("IoT module not available for cascade")
        
        await self.db.commit()
        
        logger.warning(
            "Organization soft deleted with cascade",
            org_id=str(org_id),
            org_name=org_name,
            cascade_results=cascade_results,
        )
        
        return {
            "status": "deactivated",
            "method": "soft_delete",
            "organization_id": str(org_id),
            "organization_name": org_name,
            "cascade_actions": cascade_results,
            "message": f"Organizasyon '{org_name}' ve ilişkili kaynaklar devre dışı bırakıldı",
        }
    
    # ============== Enhanced Revoke Sessions ==============
    
    async def revoke_user_sessions_enhanced(
        self,
        user_id: uuid.UUID,
        revoke_auth0: bool = True,
    ) -> dict:
        """
        Revoke all sessions for a user with Redis blacklist and Auth0 (Admin only).
        
        1. Redis'te refresh_token'ı blacklist'e ekle
        2. Auth0 Management API ile oturumu kapat (opsiyonel)
        3. Audit log'a kaydet
        """
        user = await self.get_user_by_id(user_id)
        if not user:
            raise NotFoundError("User", user_id)
        
        revoke_results = {
            "redis_blacklisted": False,
            "auth0_revoked": False,
            "auth0_status": None,
        }
        
        # 1. Redis'te token'ları blacklist'e ekle
        try:
            from src.core.redis import get_redis
            redis = await get_redis()
            if redis:
                # User'ın tüm token'larını invalidate etmek için
                # user_id bazlı bir blacklist key oluştur
                blacklist_key = f"token_blacklist:user:{user_id}"
                # 24 saat boyunca blacklist'te tut (access token max lifetime)
                await redis.setex(blacklist_key, 86400, "revoked")
                revoke_results["redis_blacklisted"] = True
                logger.info("User tokens blacklisted in Redis", user_id=str(user_id))
        except Exception as e:
            logger.warning(f"Redis blacklist failed: {e}")
        
        # 2. Auth0 Management API ile session iptal
        if revoke_auth0 and user.auth0_id:
            try:
                from src.core.auth0 import get_auth0_management
                auth0_mgmt = get_auth0_management()
                
                if auth0_mgmt.is_configured:
                    result = await auth0_mgmt.revoke_user_sessions(user.auth0_id)
                    revoke_results["auth0_status"] = result.get("status")
                    revoke_results["auth0_revoked"] = result.get("status") == "revoked"
                    logger.info(
                        "Auth0 session revocation completed",
                        user_id=str(user_id),
                        auth0_id=user.auth0_id,
                        result=result,
                    )
                else:
                    revoke_results["auth0_status"] = "not_configured"
                    logger.info("Auth0 Management API not configured, skipping")
            except Exception as e:
                logger.warning(f"Auth0 session revocation failed: {e}")
                revoke_results["auth0_status"] = f"error: {str(e)}"
        
        logger.warning(
            "User sessions revoked (enhanced)",
            user_id=str(user_id),
            user_email=user.email,
            results=revoke_results,
        )
        
        return {
            "status": "revoked",
            "user_id": str(user_id),
            "user_email": user.email,
            "revoke_results": revoke_results,
            "message": f"'{user.email}' kullanıcısının tüm oturumları sonlandırıldı",
        }
    
    # ============== Enhanced Transfer Ownership ==============
    
    async def transfer_organization_ownership_validated(
        self,
        org_id: uuid.UUID,
        new_owner_user_id: uuid.UUID,
    ) -> dict:
        """
        Transfer organization ownership with validation (Admin only).
        
        Validasyonlar:
        1. Yeni sahip organizasyonun mevcut üyesi mi?
        2. Yeni sahip aktif mi?
        
        İşlemler:
        1. Eski sahip tenant_admin → user rolüne düşürülür
        2. Yeni sahip → tenant_admin rolüne yükseltilir
        3. Audit log kaydı
        """
        org = await self.get_organization_by_id(org_id)
        if not org:
            raise NotFoundError("Organization", org_id)
        
        new_owner = await self.get_user_by_id(new_owner_user_id)
        if not new_owner:
            raise NotFoundError("User", new_owner_user_id)
        
        if not new_owner.is_active:
            raise UnauthorizedError("New owner must be an active user")
        
        # Yeni sahip organizasyonun üyesi mi kontrol et
        new_owner_membership = None
        for m in org.members:
            if m.user_id == new_owner_user_id:
                new_owner_membership = m
                break
        
        if not new_owner_membership:
            raise UnauthorizedError(
                f"User {new_owner.email} is not a member of organization {org.name}. "
                "New owner must be an existing member."
            )
        
        # Get tenant role
        tenant_role = await self._get_or_create_tenant_role()
        user_role = await self._get_or_create_role(RoleType.USER.value)
        
        # Find current owner
        current_owner_membership = None
        current_owner_email = None
        
        for m in org.members:
            if m.role_id == tenant_role.id:
                current_owner_membership = m
                if m.user:
                    current_owner_email = m.user.email
                break
        
        # Demote current owner to user role
        if current_owner_membership:
            current_owner_membership.role_id = user_role.id
        
        # Promote new owner to tenant role
        new_owner_membership.role_id = tenant_role.id
        new_owner_membership.is_default = True
        
        await self.db.commit()
        
        logger.info(
            "Organization ownership transferred (validated)",
            org_id=str(org_id),
            org_name=org.name,
            old_owner_email=current_owner_email,
            new_owner_email=new_owner.email,
        )
        
        return {
            "status": "transferred",
            "organization_id": str(org_id),
            "organization_name": org.name,
            "old_owner_email": current_owner_email,
            "new_owner_id": str(new_owner_user_id),
            "new_owner_email": new_owner.email,
            "message": f"Organizasyon sahipliği '{new_owner.email}' kullanıcısına devredildi",
        }


