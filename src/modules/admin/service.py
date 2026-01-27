"""
Admin Module - Service Layer (Refactored)

Bu servis artık bir "Facade" pattern kullanarak
işlemleri ilgili servislere deleg eder.

Domain Driven Design prensibi ile:
- AdminOrganizationService: Organizasyon işlemleri
- AdminUserService: Kullanıcı işlemleri  
- AdminInvitationService: Davetiye işlemleri
- AdminSystemService: Sistem işlemleri
"""
import uuid
from typing import TYPE_CHECKING

from sqlalchemy.ext.asyncio import AsyncSession

from src.core.logging import get_logger
from src.modules.auth.schemas import (
    CreateOrganizationWithUserRequest,
    CreateOrganizationWithUserResponse,
    OrganizationResponse,
    RoleResponse,
    UserResponse,
)

if TYPE_CHECKING:
    pass

logger = get_logger(__name__)


class AdminService:
    """
    Admin Service - Facade Pattern
    
    Bu servis artık işlemleri ilgili domain servislere deleg eder.
    Backward compatibility için korunmuştur.
    """
    
    def __init__(self, db: AsyncSession):
        self.db = db
        
        # Lazy loading - sadece ihtiyaç olduğunda yükle
        self._organization_service = None
        self._user_service = None
        self._invitation_service = None
        self._system_service = None
    
    @property
    def organization_service(self):
        """Get organization service (lazy loading)."""
        if self._organization_service is None:
            from src.modules.admin.services.organization_service import AdminOrganizationService
            self._organization_service = AdminOrganizationService(self.db)
        return self._organization_service
    
    @property
    def user_service(self):
        """Get user service (lazy loading)."""
        if self._user_service is None:
            from src.modules.admin.services.user_service import AdminUserService
            self._user_service = AdminUserService(self.db)
        return self._user_service
    
    @property
    def invitation_service(self):
        """Get invitation service (lazy loading)."""
        if self._invitation_service is None:
            from src.modules.admin.services.invitation_service import AdminInvitationService
            self._invitation_service = AdminInvitationService(self.db)
        return self._invitation_service
    
    @property
    def system_service(self):
        """Get system service (lazy loading)."""
        if self._system_service is None:
            from src.modules.admin.services.system_service import AdminSystemService
            self._system_service = AdminSystemService(self.db)
        return self._system_service
    
    # =========================================================================
    # ORGANIZATION OPERATIONS (Delegate to OrganizationService)
    # =========================================================================
    
    async def get_organization_by_id(self, org_id: uuid.UUID):
        """Get organization by ID."""
        return await self.organization_service.get_organization_by_id(org_id)
    
    async def get_organization_by_slug(self, slug: str):
        """Get organization by slug."""
        return await self.organization_service.get_organization_by_slug(slug)
    
    async def create_organization_with_user(
        self,
        request: CreateOrganizationWithUserRequest,
        background_tasks = None,  # BackgroundTasks for async email
    ) -> CreateOrganizationWithUserResponse:
        """
        Tab 1: Organizasyon ve ilk kullanıcı (tenant owner) birlikte oluşturma.
        
        NOT: Bu metod özel olduğu için burada kalıyor.
        Diğer organizasyon metodları organization_service'e deleg edilir.
        """
        import secrets
        from datetime import datetime, timedelta, UTC
        
        from src.modules.auth.models import (
            Invitation,
            Organization,
            OrganizationUser,
            User,
        )
        
        # Slug oluştur
        slug = request.organization_slug
        if not slug:
            slug = request.organization_name.lower().replace(" ", "-").replace("'", "")
        
        # Slug kontrolü
        existing_org = await self.organization_service.get_organization_by_slug(slug)
        if existing_org:
            slug = f"{slug}-{uuid.uuid4().hex[:6]}"
        
        # Email kontrolü
        existing_user = await self.user_service._get_user_by_email(request.user_email)
        if existing_user:
            from src.core.exceptions import ConflictError
            raise ConflictError(f"User with email {request.user_email} already exists")
        
        # Organizasyon oluştur
        org = Organization(
            name=request.organization_name,
            slug=slug,
            description=request.organization_description,
            organization_type=request.organization_type.value
            if request.organization_type else None,
            company_size=request.company_size,
            email=request.organization_email,
            phone=request.organization_phone,
            city=request.city,
            district=request.district,
            neighborhood=request.neighborhood,
            street=request.street,
            postal_code=request.postal_code,
            country=request.country,
            latitude=request.latitude,
            longitude=request.longitude,
            is_active=True,
        )
        self.db.add(org)
        await self.db.flush()
        
        # Kullanıcı oluştur
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
        
        # Rol al veya oluştur (Hardcoded 'tenant' for security)
        role = await self.organization_service._get_or_create_role("tenant")
        
        # Kullanıcıyı organizasyona ekle
        membership = OrganizationUser(
            user_id=user.id,
            organization_id=org.id,
            role_id=role.id,
            is_default=True,
            joined_at=datetime.now(UTC),
        )
        self.db.add(membership)
        
        # Davetiye oluştur (Giriş bileti)
        token = secrets.token_urlsafe(32)
        invitation = Invitation(
            email=user.email,
            token=token,
            organization_id=org.id,
            role_code="tenant",
            invited_by_id=None,  # Sistem tarafından oluşturuldu
            message="Organizasyonunuz oluşturuldu. Hesabınızı aktifleştirin.",
            expires_at=datetime.now(UTC) + timedelta(days=7),  # 7 gün süre
            is_used=False
        )
        self.db.add(invitation)
        
        # TRANSACTION'I HEMEN KAPAT - VERİYİ GARANTİYE AL
        await self.db.commit()
        await self.db.refresh(org)
        await self.db.refresh(user)
        await self.db.refresh(role)
        
        # Email'i arka plana at (connection pool'u kitleme)
        if background_tasks:
            background_tasks.add_task(
                self._send_welcome_email_background_task,
                email=user.email,
                token=token,
                org_name=org.name,
            )
            email_status = "Email gönderiliyor"
        else:
            # Fallback: Senkron gönder (test için)
            email_status = await self._send_welcome_email_background_task(
                email=user.email,
                token=token,
                org_name=org.name,
            )
        
        logger.info(
            "Organization and user created by admin with invitation",
            org_id=str(org.id),
            user_id=str(user.id),
            role="tenant",
            invitation_sent=True,
            email_status=email_status,
        )
        
        return CreateOrganizationWithUserResponse(
            message="Organizasyon ve kullanıcı başarıyla oluşturuldu. "
            "Davet e-postası gönderiliyor.",
            organization=OrganizationResponse.model_validate(org),
            user=UserResponse.model_validate(user),
            role=RoleResponse.model_validate(role),
        )
    
    async def _send_welcome_email_background_task(
        self,
        email: str,
        token: str,
        org_name: str,
    ) -> str:
        """
        Background task for sending welcome email.
        Bu metod ayrı bir transaction'da çalışır.
        """
        try:
            # Yeni database session oluştur (main transaction etkilenmesin)
            from src.core.database import get_db
            async for db in get_db():
                from src.modules.notifications.service import NotificationService
                notification_service = NotificationService(db)
                
                await notification_service.send_invitation_email(
                    email=email,
                    token=token,
                    org_name=org_name,
                    invited_by_name="Awaxen Admin"
                )
                
                logger.info(
                    "Welcome invitation email sent successfully (background)",
                    email=email,
                    org_name=org_name,
                    token=token[:8] + "...",
                )
                return "Email başarıyla gönderildi"
        except Exception as e:
            logger.error(
                f"Welcome email failed (background): {e}",
                email=email,
                org_name=org_name,
            )
            return f"Email gönderilemedi: {e!s}"
    
    async def create_organization_step2(self, request):
        """Delegate to organization service."""
        return await self.organization_service.create_organization_step2(request)
    
    async def list_all_organizations(self, page=1, page_size=20, search=None, is_active=None):
        """Delegate to organization service."""
        return await self.organization_service.list_all_organizations(page, page_size, search, is_active)
    
    async def get_organization_detail(self, org_id: str):
        """Delegate to organization service."""
        return await self.organization_service.get_organization_detail(org_id)
    
    async def get_organization_stats(self, organization_id: str):
        """Delegate to organization service."""
        return await self.organization_service.get_organization_stats(organization_id)
    
    async def suspend_organization(self, org_id: uuid.UUID, reason: str | None = None):
        """Delegate to organization service."""
        return await self.organization_service.suspend_organization(org_id, reason)
    
    async def reactivate_organization(self, org_id: uuid.UUID):
        """Delegate to organization service."""
        return await self.organization_service.reactivate_organization(org_id)
    
    async def delete_organization(self, org_id: uuid.UUID, hard_delete: bool = False):
        """Delegate to organization service."""
        return await self.organization_service.delete_organization(org_id, hard_delete)
    
    async def transfer_ownership(self, org_id: uuid.UUID, new_owner_user_id: uuid.UUID):
        """Delegate to organization service."""
        return await self.organization_service.transfer_ownership(org_id, new_owner_user_id)
    
    async def update_organization_modules(self, org_id: uuid.UUID, modules: list[str]):
        """Delegate to organization service."""
        return await self.organization_service.update_organization_modules(org_id, modules)
    
    # =========================================================================
    # USER OPERATIONS (Delegate to UserService)
    # =========================================================================
    
    async def list_all_users(self, page=1, page_size=20, search=None, role=None, organization_id=None, is_active=None):
        """Delegate to user service."""
        return await self.user_service.list_all_users(page, page_size, search, role, organization_id, is_active)
    
    async def list_organization_users(self, organization_id: str, page=1, page_size=20, search=None, role=None, is_active=None):
        """Delegate to user service."""
        return await self.user_service.list_organization_users(organization_id, page, page_size, search, role, is_active)
    
    async def add_user_to_organization(self, request):
        """Delegate to user service."""
        return await self.user_service.add_user_to_organization(request)
    
    async def remove_user_from_organization(self, organization_id: uuid.UUID, user_id: uuid.UUID):
        """Delegate to user service."""
        return await self.user_service.remove_user_from_organization(organization_id, user_id)
    
    async def assign_role_to_user(self, user_id: str, request):
        """Delegate to user service."""
        return await self.user_service.assign_role_to_user(user_id, request)
    
    async def ban_user(self, user_id: uuid.UUID, reason: str | None = None):
        """Delegate to user service."""
        return await self.user_service.ban_user(user_id, reason)
    
    async def revoke_user_sessions_enhanced(self, user_id: uuid.UUID, revoke_auth0: bool = True):
        """Delegate to user service."""
        return await self.user_service.revoke_user_sessions_enhanced(user_id, revoke_auth0)
    
    async def impersonate_user(self, admin_user, target_user_id: uuid.UUID, reason: str | None = None, duration_minutes: int = 60):
        """Delegate to user service."""
        return await self.user_service.impersonate_user(admin_user, target_user_id, reason, duration_minutes)
    
    # =========================================================================
    # INVITATION OPERATIONS (Delegate to InvitationService)
    # =========================================================================
    
    async def create_invitation(self, organization_id: uuid.UUID, email: str, role_code: str, invited_by, message: str | None = None, expires_hours: int = 48):
        """Delegate to invitation service."""
        return await self.invitation_service.create_invitation(organization_id, email, role_code, invited_by, message, expires_hours)
    
    async def get_organization_invitations(self, organization_id: uuid.UUID, include_used: bool = False):
        """Delegate to invitation service."""
        return await self.invitation_service.get_organization_invitations(organization_id, include_used)
    
    async def revoke_invitation(self, invitation_id: uuid.UUID, revoked_by):
        """Delegate to invitation service."""
        return await self.invitation_service.revoke_invitation(invitation_id, revoked_by)
    
    # =========================================================================
    # SYSTEM OPERATIONS (Delegate to SystemService)
    # =========================================================================
    
    async def list_all_roles(self):
        """Delegate to system service."""
        return await self.system_service.list_all_roles()
    
    async def get_available_roles(self):
        """Delegate to system service."""
        return await self.system_service.list_all_roles()
    
    async def get_available_permissions(self):
        """Delegate to system service."""
        return await self.system_service.list_all_permissions()
    
    async def get_available_modules(self):
        """Delegate to system service."""
        # This could be moved to system service too
        from src.modules.auth.models import ModuleType
        from src.modules.auth.schemas import AvailableModulesResponse, ModuleInfo
        
        modules = []
        for module in ModuleType:
            modules.append(ModuleInfo(
                code=module.value,
                name=module.value.title(),
                description=f"{module.value} module",
            ))
        
        return AvailableModulesResponse(modules=modules)
