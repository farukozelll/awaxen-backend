"""
Model Import Tests - Verify all models can be imported correctly
"""
import pytest


def test_compliance_models_import():
    """Test compliance models can be imported."""
    from src.modules.compliance.models import Consent, AuditLog, ConsentType
    assert Consent is not None
    assert AuditLog is not None
    assert ConsentType is not None


def test_energy_models_import():
    """Test energy models can be imported."""
    from src.modules.energy.models import (
        Recommendation, Command, CommandProof, RewardLedger, Streak,
        RecommendationStatus, CommandStatus, CommandAction
    )
    assert Recommendation is not None
    assert Command is not None
    assert CommandProof is not None
    assert RewardLedger is not None
    assert Streak is not None


def test_marketplace_models_import():
    """Test marketplace models can be imported."""
    from src.modules.marketplace.models import (
        Alarm, Job, JobOffer, JobProof,
        AlarmSeverity, JobStatus, JobCategory
    )
    assert Alarm is not None
    assert Job is not None
    assert JobOffer is not None
    assert JobProof is not None


def test_real_estate_models_import():
    """Test real estate models can be imported."""
    from src.modules.real_estate.models import (
        Asset, Zone, Lease, AssetMembership, Tenancy, HandoverToken,
        AssetType, ZoneType, TenancyStatus
    )
    assert Asset is not None
    assert Zone is not None
    assert Lease is not None
    assert AssetMembership is not None
    assert Tenancy is not None
    assert HandoverToken is not None


def test_iot_models_import():
    """Test IoT models can be imported."""
    from src.modules.iot.models import (
        Gateway, Device, TelemetryData,
        GatewayPairingCode, DeviceAlias, DeviceStateEvent,
        SafetyProfile, DeviceStatus, GatewayStatus
    )
    assert Gateway is not None
    assert Device is not None
    assert TelemetryData is not None
    assert GatewayPairingCode is not None
    assert DeviceAlias is not None
    assert DeviceStateEvent is not None


def test_auth_models_import():
    """Test auth models can be imported."""
    from src.modules.auth.models import User, Organization, Role, OrganizationUser
    assert User is not None
    assert Organization is not None
    assert Role is not None
    assert OrganizationUser is not None


def test_billing_models_import():
    """Test billing models can be imported."""
    from src.modules.billing.models import Wallet, Transaction, Invoice
    assert Wallet is not None
    assert Transaction is not None
    assert Invoice is not None


def test_notifications_models_import():
    """Test notifications models can be imported."""
    from src.modules.notifications.models import (
        Notification, UserFCMToken, NotificationPreference
    )
    assert Notification is not None
    assert UserFCMToken is not None
    assert NotificationPreference is not None
