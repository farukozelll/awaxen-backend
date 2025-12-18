"""
Pytest Configuration and Fixtures.

Tüm testlerde kullanılan ortak fixture'lar burada tanımlanır.
"""
import os
import pytest
from typing import Generator

# Test environment variables - PostgreSQL kullan (JSONB desteği için)
# Docker'da test DB çalışıyorsa onu kullan, yoksa ana DB'yi kullan
os.environ["DATABASE_URL"] = os.environ.get(
    "TEST_DATABASE_URL",
    "postgresql://awaxen:gizli_sifre_123@localhost:5432/awaxen_test"
)
os.environ["FLASK_ENV"] = "testing"
os.environ["CELERY_BROKER_URL"] = "memory://"
os.environ["CELERY_RESULT_BACKEND"] = "cache+memory://"

from app import create_app
from app.extensions import db
from app.models import (
    Organization, User, Role, Permission,
    SmartDevice, SmartAsset, Integration, Gateway,
    Automation, Wallet
)


@pytest.fixture(scope="session")
def app():
    """Create application for testing."""
    app = create_app()
    app.config.update({
        "TESTING": True,
        "WTF_CSRF_ENABLED": False,
    })
    
    with app.app_context():
        # Tüm tabloları temizle ve yeniden oluştur
        db.drop_all()
        db.create_all()
        # Seed default roles
        Role.seed_default_roles()
        db.session.commit()
    
    yield app
    
    # Cleanup
    with app.app_context():
        db.drop_all()


@pytest.fixture(scope="function")
def client(app):
    """Create test client."""
    return app.test_client()


@pytest.fixture(scope="function")
def db_session(app):
    """Create database session for testing with transaction rollback."""
    with app.app_context():
        # Her test için temiz başla
        yield db.session
        
        # Test sonrası rollback
        db.session.rollback()
        
        # Test verilerini temizle (roller hariç)
        from app.models import (
            Organization, User, SmartDevice, SmartAsset,
            Automation, AutomationLog, Wallet, WalletTransaction,
            MarketPrice, Notification, AuditLog, Gateway, Integration
        )
        
        # Sıralı silme (foreign key constraints)
        AutomationLog.query.delete()
        Automation.query.delete()
        WalletTransaction.query.delete()
        Wallet.query.delete()
        Notification.query.delete()
        AuditLog.query.delete()
        SmartAsset.query.delete()
        SmartDevice.query.delete()
        Gateway.query.delete()
        Integration.query.delete()
        User.query.delete()
        Organization.query.delete()
        MarketPrice.query.delete()
        db.session.commit()


@pytest.fixture
def sample_organization(db_session) -> Organization:
    """Create a sample organization."""
    org = Organization(
        name="Test Organization",
        slug="test-org",
        type="home",
        timezone="Europe/Istanbul"
    )
    db_session.add(org)
    db_session.commit()
    return org


@pytest.fixture
def sample_user(db_session, sample_organization) -> User:
    """Create a sample user."""
    admin_role = Role.get_by_code("admin")
    user = User(
        organization_id=sample_organization.id,
        auth0_id="auth0|test123",
        email="test@example.com",
        full_name="Test User",
        role_id=admin_role.id if admin_role else None
    )
    db_session.add(user)
    db_session.commit()
    return user


@pytest.fixture
def sample_device(db_session, sample_organization) -> SmartDevice:
    """Create a sample device."""
    device = SmartDevice(
        organization_id=sample_organization.id,
        external_id="test-device-001",
        name="Test Device",
        brand="shelly",
        model="plug-s",
        device_type="relay",
        is_sensor=True,
        is_actuator=True,
        is_online=True
    )
    db_session.add(device)
    db_session.commit()
    return device


@pytest.fixture
def sample_asset(db_session, sample_organization, sample_device) -> SmartAsset:
    """Create a sample asset."""
    asset = SmartAsset(
        organization_id=sample_organization.id,
        device_id=sample_device.id,
        name="Test Asset",
        type="hvac",
        nominal_power_watt=2000
    )
    db_session.add(asset)
    db_session.commit()
    return asset


@pytest.fixture
def sample_automation(db_session, sample_organization, sample_asset, sample_user) -> Automation:
    """Create a sample automation."""
    automation = Automation(
        organization_id=sample_organization.id,
        asset_id=sample_asset.id,
        created_by=sample_user.id,
        name="Test Automation",
        description="Test automation for unit tests",
        rules={
            "trigger": {"type": "price", "operator": "<", "value": 2.0},
            "action": {"type": "turn_on"}
        },
        is_active=True
    )
    db_session.add(automation)
    db_session.commit()
    return automation


@pytest.fixture
def auth_headers(sample_user) -> dict:
    """
    Create mock authentication headers.
    
    Note: In real tests, you'd mock the JWT validation.
    """
    return {
        "Authorization": "Bearer mock-jwt-token",
        "Content-Type": "application/json"
    }


class MockJWTPayload:
    """Mock JWT payload for testing."""
    
    def __init__(self, user: User):
        self.sub = user.auth0_id
        self.email = user.email
        self.name = user.full_name
    
    def get(self, key, default=None):
        return getattr(self, key, default)
