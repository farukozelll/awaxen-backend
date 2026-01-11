"""
Test Configuration - Pytest fixtures

Bu dosya test altyapısını kurar:
1. Test veritabanı (izole, her testte sıfırlanır)
2. Auth mock (Auth0'a gitmeden test token'ları)
3. HTTP client fixtures

Kullanım:
    pytest -v                    # Tüm testleri çalıştır
    pytest -v -k "test_auth"     # Sadece auth testlerini çalıştır
    pytest -v --cov=src          # Coverage ile çalıştır
"""
import asyncio
import uuid
from datetime import datetime, timezone
from typing import AsyncGenerator

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker

from src.main import app
from src.core.database import get_db
from src.core.models import Base
from src.core.security import create_access_token


# =============================================================================
# TEST DATABASE CONFIGURATION
# =============================================================================
# SQLite in-memory for fast, isolated tests (no external DB needed)
# Production'da PostgreSQL kullanılır ama testler için SQLite yeterli
TEST_DATABASE_URL = "sqlite+aiosqlite:///:memory:"

# Test engine and session factory
test_engine = create_async_engine(
    TEST_DATABASE_URL,
    echo=False,
    future=True,
)
TestSessionLocal = async_sessionmaker(
    bind=test_engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autoflush=False,
)


# =============================================================================
# EVENT LOOP FIXTURE
# =============================================================================
@pytest.fixture(scope="session")
def event_loop():
    """Create event loop for async tests."""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


# =============================================================================
# DATABASE FIXTURES
# =============================================================================
@pytest_asyncio.fixture(scope="function")
async def db_session() -> AsyncGenerator[AsyncSession, None]:
    """
    Her test için tertemiz bir veritabanı oturumu oluşturur.
    
    Test başında tablolar oluşturulur, test bitince silinir.
    Bu sayede testler birbirini etkilemez (isolation).
    """
    # Create all tables
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    
    # Provide session to test
    async with TestSessionLocal() as session:
        yield session
    
    # Drop all tables after test
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


# =============================================================================
# HTTP CLIENT FIXTURES
# =============================================================================
@pytest_asyncio.fixture
async def client(db_session: AsyncSession) -> AsyncGenerator[AsyncClient, None]:
    """
    Test HTTP client - veritabanı bağımlılığı override edilmiş.
    
    Bu client ile yapılan istekler gerçek DB yerine test DB'ye gider.
    """
    async def override_get_db():
        yield db_session
    
    # Override the database dependency
    app.dependency_overrides[get_db] = override_get_db
    
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as ac:
        yield ac
    
    # Clear overrides after test
    app.dependency_overrides.clear()


# =============================================================================
# AUTHENTICATION FIXTURES
# =============================================================================
@pytest.fixture
def test_user_id() -> uuid.UUID:
    """Generate a consistent test user ID."""
    return uuid.UUID("11111111-1111-1111-1111-111111111111")


@pytest.fixture
def test_org_id() -> uuid.UUID:
    """Generate a consistent test organization ID."""
    return uuid.UUID("22222222-2222-2222-2222-222222222222")


@pytest.fixture
def admin_token(test_user_id: uuid.UUID) -> str:
    """
    Admin rolüne sahip test token'ı.
    
    Bu token ile admin endpoint'lerine erişilebilir.
    """
    return create_access_token(
        subject=str(test_user_id),
        extra_claims={
            "roles": ["admin"],
            "permissions": ["admin:*", "org:*", "user:*"],
            "email": "admin@test.com",
        }
    )


@pytest.fixture
def tenant_token(test_user_id: uuid.UUID, test_org_id: uuid.UUID) -> str:
    """
    Tenant (organizasyon yöneticisi) rolüne sahip test token'ı.
    
    Bu token ile kendi organizasyonundaki işlemleri yapabilir.
    """
    return create_access_token(
        subject=str(test_user_id),
        extra_claims={
            "roles": ["tenant"],
            "permissions": ["org:read", "org:write", "user:invite"],
            "email": "tenant@test.com",
            "org_id": str(test_org_id),
        }
    )


@pytest.fixture
def user_token(test_user_id: uuid.UUID, test_org_id: uuid.UUID) -> str:
    """
    Normal kullanıcı rolüne sahip test token'ı.
    
    Bu token ile sadece okuma işlemleri yapılabilir.
    """
    return create_access_token(
        subject=str(test_user_id),
        extra_claims={
            "roles": ["user"],
            "permissions": ["read:own"],
            "email": "user@test.com",
            "org_id": str(test_org_id),
        }
    )


@pytest_asyncio.fixture
async def admin_client(client: AsyncClient, admin_token: str) -> AsyncGenerator[AsyncClient, None]:
    """Admin yetkili HTTP client."""
    client.headers["Authorization"] = f"Bearer {admin_token}"
    yield client


@pytest_asyncio.fixture
async def tenant_client(client: AsyncClient, tenant_token: str) -> AsyncGenerator[AsyncClient, None]:
    """Tenant yetkili HTTP client."""
    client.headers["Authorization"] = f"Bearer {tenant_token}"
    yield client


@pytest_asyncio.fixture
async def user_client(client: AsyncClient, user_token: str) -> AsyncGenerator[AsyncClient, None]:
    """Normal kullanıcı yetkili HTTP client."""
    client.headers["Authorization"] = f"Bearer {user_token}"
    yield client


# =============================================================================
# TEST DATA FACTORIES
# =============================================================================
@pytest.fixture
def make_user():
    """
    Factory fixture: Test kullanıcısı oluşturur.
    
    Kullanım:
        user = make_user(email="test@example.com", role="tenant")
    """
    def _make_user(
        email: str = "test@example.com",
        full_name: str = "Test User",
        role: str = "user",
        is_active: bool = True,
    ) -> dict:
        return {
            "id": str(uuid.uuid4()),
            "email": email,
            "full_name": full_name,
            "role": role,
            "is_active": is_active,
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
    return _make_user


@pytest.fixture
def make_organization():
    """
    Factory fixture: Test organizasyonu oluşturur.
    
    Kullanım:
        org = make_organization(name="Awaxen Corp", slug="awaxen-corp")
    """
    def _make_organization(
        name: str = "Test Organization",
        slug: str | None = None,
        tier: str = "free",
    ) -> dict:
        if slug is None:
            slug = name.lower().replace(" ", "-")
        return {
            "id": str(uuid.uuid4()),
            "name": name,
            "slug": slug,
            "tier": tier,
            "is_active": True,
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
    return _make_organization


# =============================================================================
# AUTH0 MOCK FIXTURES
# =============================================================================
@pytest.fixture
def mock_auth0_user() -> dict:
    """
    Auth0'dan gelen kullanıcı bilgisi mock'u.
    
    /auth/sync endpoint'i test ederken kullanılır.
    """
    return {
        "auth0_id": "google-oauth2|123456789",
        "email": "newuser@example.com",
        "name": "New User",
        "email_verified": True,
    }
