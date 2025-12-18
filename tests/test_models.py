"""
Model Tests.

Test model creation, relationships, and methods.
"""
import pytest
from decimal import Decimal

from app.models import (
    Organization, User, Role, Permission,
    SmartDevice, SmartAsset, Automation,
    Wallet, WalletTransaction
)


class TestOrganization:
    """Organization model tests."""
    
    def test_create_organization(self, db_session):
        """Test organization creation."""
        org = Organization(
            name="Test Org",
            slug="test-org",
            type="home"
        )
        db_session.add(org)
        db_session.commit()
        
        assert org.id is not None
        assert org.name == "Test Org"
        assert org.is_active is True
    
    def test_organization_to_dict(self, sample_organization):
        """Test organization serialization."""
        data = sample_organization.to_dict()
        
        assert "id" in data
        assert data["name"] == "Test Organization"
        assert data["type"] == "home"


class TestUser:
    """User model tests."""
    
    def test_create_user(self, db_session, sample_organization):
        """Test user creation."""
        role = Role.get_by_code("viewer")
        user = User(
            organization_id=sample_organization.id,
            auth0_id="auth0|newuser",
            email="new@example.com",
            role_id=role.id if role else None
        )
        db_session.add(user)
        db_session.commit()
        
        assert user.id is not None
        assert user.email == "new@example.com"
    
    def test_user_has_permission(self, sample_user):
        """Test permission checking."""
        # Admin should have device permissions
        assert sample_user.has_permission("can_view_devices") is True
    
    def test_user_is_admin(self, sample_user):
        """Test admin check."""
        assert sample_user.is_admin() is True


class TestSmartDevice:
    """SmartDevice model tests."""
    
    def test_create_device(self, db_session, sample_organization):
        """Test device creation."""
        device = SmartDevice(
            organization_id=sample_organization.id,
            external_id="device-123",
            name="New Device",
            brand="shelly",
            device_type="relay"
        )
        db_session.add(device)
        db_session.commit()
        
        assert device.id is not None
        assert device.is_active is True
    
    def test_device_to_dict(self, sample_device):
        """Test device serialization."""
        data = sample_device.to_dict()
        
        assert "id" in data
        assert data["brand"] == "shelly"
        assert data["is_online"] is True


class TestAutomation:
    """Automation model tests."""
    
    def test_create_automation(self, db_session, sample_organization, sample_user):
        """Test automation creation."""
        automation = Automation(
            organization_id=sample_organization.id,
            created_by=sample_user.id,
            name="Price Automation",
            rules={
                "trigger": {"type": "price", "operator": "<", "value": 1.5},
                "action": {"type": "turn_on"}
            }
        )
        db_session.add(automation)
        db_session.commit()
        
        assert automation.id is not None
        assert automation.trigger_count == 0
    
    def test_automation_increment_trigger(self, sample_automation):
        """Test trigger count increment."""
        initial_count = sample_automation.trigger_count or 0
        sample_automation.increment_trigger_count()
        
        assert sample_automation.trigger_count == initial_count + 1
        assert sample_automation.last_triggered_at is not None


class TestWallet:
    """Wallet model tests."""
    
    def test_create_wallet(self, db_session, sample_user):
        """Test wallet creation."""
        wallet = Wallet(user_id=sample_user.id)
        db_session.add(wallet)
        db_session.commit()
        
        assert wallet.id is not None
        assert float(wallet.balance) == 0.0
        assert wallet.level == 1
    
    def test_wallet_add_balance(self, db_session, sample_user):
        """Test adding balance."""
        wallet = Wallet(user_id=sample_user.id)
        db_session.add(wallet)
        db_session.commit()
        
        wallet.add_balance(Decimal("100.00"))
        
        assert float(wallet.balance) == 100.0
        assert float(wallet.lifetime_earned) == 100.0
    
    def test_wallet_subtract_balance(self, db_session, sample_user):
        """Test subtracting balance."""
        wallet = Wallet(user_id=sample_user.id, balance=Decimal("50.00"))
        db_session.add(wallet)
        db_session.commit()
        
        # Should succeed
        result = wallet.subtract_balance(Decimal("30.00"))
        assert result is True
        assert float(wallet.balance) == 20.0
        
        # Should fail (insufficient balance)
        result = wallet.subtract_balance(Decimal("100.00"))
        assert result is False
    
    def test_wallet_level_up(self, db_session, sample_user):
        """Test XP and level system."""
        wallet = Wallet(user_id=sample_user.id)
        db_session.add(wallet)
        db_session.commit()
        
        # Level 2 requires 400 XP (2^2 * 100)
        wallet.add_xp(500)
        
        assert wallet.xp == 500
        assert wallet.level >= 2


class TestRole:
    """Role model tests."""
    
    def test_get_by_code(self, db_session):
        """Test role lookup by code."""
        admin = Role.get_by_code("admin")
        assert admin is not None
        assert admin.code == "admin"
    
    def test_role_has_permission(self, db_session):
        """Test role permission check."""
        admin = Role.get_by_code("admin")
        assert admin.has_permission("can_view_devices") is True
        assert admin.has_permission("nonexistent_permission") is False
