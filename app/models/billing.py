"""
Awaxen Models - Billing & Subscription.

Gerçek para (TL/USD) ile ödeme ve abonelik yönetimi.
Stripe/Iyzico entegrasyonu için hazır.
"""
from datetime import datetime, timezone
from typing import Optional
import uuid

from sqlalchemy.dialects.postgresql import JSONB, UUID

from app.extensions import db
from app.models.base import TimestampMixin


def utcnow() -> datetime:
    """Timezone-aware UTC datetime döndür."""
    return datetime.now(timezone.utc)


class SubscriptionPlan(db.Model):
    """
    Abonelik planları tanımı.
    
    Örnek: Free, Starter, Pro, Enterprise
    """
    __tablename__ = "subscription_plans"

    id = db.Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    code = db.Column(db.String(50), unique=True, nullable=False, index=True)  # free, starter, pro, enterprise
    name = db.Column(db.String(100), nullable=False)
    description = db.Column(db.Text)
    
    # Fiyatlandırma
    price_monthly = db.Column(db.Numeric(10, 2), default=0)  # Aylık fiyat (TL)
    price_yearly = db.Column(db.Numeric(10, 2), default=0)   # Yıllık fiyat (TL)
    currency = db.Column(db.String(3), default="TRY")
    
    # Limitler
    max_devices = db.Column(db.Integer, default=5)
    max_users = db.Column(db.Integer, default=1)
    max_automations = db.Column(db.Integer, default=10)
    max_integrations = db.Column(db.Integer, default=2)
    
    # Özellikler
    features = db.Column(JSONB, default=dict)  # {"advanced_analytics": true, "api_access": true, ...}
    
    is_active = db.Column(db.Boolean, default=True)
    sort_order = db.Column(db.Integer, default=0)
    
    created_at = db.Column(db.DateTime(timezone=True), default=utcnow)
    updated_at = db.Column(db.DateTime(timezone=True), default=utcnow, onupdate=utcnow)

    def to_dict(self) -> dict:
        return {
            "id": str(self.id),
            "code": self.code,
            "name": self.name,
            "description": self.description,
            "price_monthly": float(self.price_monthly) if self.price_monthly else 0,
            "price_yearly": float(self.price_yearly) if self.price_yearly else 0,
            "currency": self.currency,
            "max_devices": self.max_devices,
            "max_users": self.max_users,
            "max_automations": self.max_automations,
            "max_integrations": self.max_integrations,
            "features": self.features or {},
            "is_active": self.is_active,
        }


class Subscription(db.Model):
    """
    Organizasyon abonelik kaydı.
    
    Bir organizasyonun aktif aboneliği ve geçmişi.
    """
    __tablename__ = "subscriptions"

    id = db.Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    organization_id = db.Column(UUID(as_uuid=True), db.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True)
    plan_id = db.Column(UUID(as_uuid=True), db.ForeignKey("subscription_plans.id"), nullable=False)
    
    # Durum
    status = db.Column(db.String(20), default="active", index=True)  # active, trial, past_due, cancelled, expired
    
    # Dönem
    billing_cycle = db.Column(db.String(10), default="monthly")  # monthly, yearly
    current_period_start = db.Column(db.DateTime(timezone=True))
    current_period_end = db.Column(db.DateTime(timezone=True))
    trial_end = db.Column(db.DateTime(timezone=True))
    
    # Ödeme sağlayıcı bilgileri
    payment_provider = db.Column(db.String(20))  # stripe, iyzico, paytr
    provider_subscription_id = db.Column(db.String(255))  # Stripe subscription ID
    provider_customer_id = db.Column(db.String(255))  # Stripe customer ID
    
    # İptal bilgileri
    cancel_at_period_end = db.Column(db.Boolean, default=False)
    cancelled_at = db.Column(db.DateTime(timezone=True))
    
    created_at = db.Column(db.DateTime(timezone=True), default=utcnow)
    updated_at = db.Column(db.DateTime(timezone=True), default=utcnow, onupdate=utcnow)

    # İlişkiler
    organization = db.relationship("Organization", backref=db.backref("subscriptions", lazy="dynamic"))
    plan = db.relationship("SubscriptionPlan", backref="subscriptions")

    __table_args__ = (
        db.Index('idx_subscription_org_status', 'organization_id', 'status'),
    )

    def to_dict(self) -> dict:
        return {
            "id": str(self.id),
            "organization_id": str(self.organization_id),
            "plan": self.plan.to_dict() if self.plan else None,
            "status": self.status,
            "billing_cycle": self.billing_cycle,
            "current_period_start": self.current_period_start.isoformat() if self.current_period_start else None,
            "current_period_end": self.current_period_end.isoformat() if self.current_period_end else None,
            "trial_end": self.trial_end.isoformat() if self.trial_end else None,
            "cancel_at_period_end": self.cancel_at_period_end,
            "cancelled_at": self.cancelled_at.isoformat() if self.cancelled_at else None,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }

    def is_active(self) -> bool:
        """Abonelik aktif mi?"""
        return self.status in ["active", "trial"]


class Invoice(db.Model):
    """
    Fatura kaydı.
    
    Ödeme geçmişi ve fatura bilgileri.
    """
    __tablename__ = "invoices"

    id = db.Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    organization_id = db.Column(UUID(as_uuid=True), db.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True)
    subscription_id = db.Column(UUID(as_uuid=True), db.ForeignKey("subscriptions.id", ondelete="SET NULL"))
    
    # Fatura numarası
    invoice_number = db.Column(db.String(50), unique=True, nullable=False)
    
    # Tutar
    amount = db.Column(db.Numeric(10, 2), nullable=False)
    tax_amount = db.Column(db.Numeric(10, 2), default=0)
    total_amount = db.Column(db.Numeric(10, 2), nullable=False)
    currency = db.Column(db.String(3), default="TRY")
    
    # Durum
    status = db.Column(db.String(20), default="pending", index=True)  # pending, paid, failed, refunded, cancelled
    
    # Dönem
    period_start = db.Column(db.DateTime(timezone=True))
    period_end = db.Column(db.DateTime(timezone=True))
    due_date = db.Column(db.DateTime(timezone=True))
    paid_at = db.Column(db.DateTime(timezone=True))
    
    # Ödeme sağlayıcı
    payment_provider = db.Column(db.String(20))
    provider_invoice_id = db.Column(db.String(255))
    provider_payment_intent_id = db.Column(db.String(255))
    
    # Fatura detayları
    line_items = db.Column(JSONB, default=list)  # [{"description": "Pro Plan - Monthly", "amount": 299}]
    billing_details = db.Column(JSONB, default=dict)  # Fatura adresi, vergi no vs.
    
    # PDF
    pdf_url = db.Column(db.String(500))
    
    created_at = db.Column(db.DateTime(timezone=True), default=utcnow)
    updated_at = db.Column(db.DateTime(timezone=True), default=utcnow, onupdate=utcnow)

    # İlişkiler
    organization = db.relationship("Organization", backref=db.backref("invoices", lazy="dynamic"))
    subscription = db.relationship("Subscription", backref="invoices")

    __table_args__ = (
        db.Index('idx_invoice_org_status', 'organization_id', 'status'),
        db.Index('idx_invoice_created', 'created_at'),
    )

    def to_dict(self) -> dict:
        return {
            "id": str(self.id),
            "organization_id": str(self.organization_id),
            "invoice_number": self.invoice_number,
            "amount": float(self.amount),
            "tax_amount": float(self.tax_amount) if self.tax_amount else 0,
            "total_amount": float(self.total_amount),
            "currency": self.currency,
            "status": self.status,
            "period_start": self.period_start.isoformat() if self.period_start else None,
            "period_end": self.period_end.isoformat() if self.period_end else None,
            "due_date": self.due_date.isoformat() if self.due_date else None,
            "paid_at": self.paid_at.isoformat() if self.paid_at else None,
            "line_items": self.line_items or [],
            "pdf_url": self.pdf_url,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


class PaymentMethod(db.Model):
    """
    Kayıtlı ödeme yöntemi.
    
    Kredi kartı, banka kartı vs.
    """
    __tablename__ = "payment_methods"

    id = db.Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    organization_id = db.Column(UUID(as_uuid=True), db.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True)
    
    # Tip
    type = db.Column(db.String(20), default="card")  # card, bank_transfer
    
    # Kart bilgileri (masked)
    card_brand = db.Column(db.String(20))  # visa, mastercard, amex
    card_last4 = db.Column(db.String(4))
    card_exp_month = db.Column(db.Integer)
    card_exp_year = db.Column(db.Integer)
    
    # Ödeme sağlayıcı
    payment_provider = db.Column(db.String(20))
    provider_payment_method_id = db.Column(db.String(255))
    
    is_default = db.Column(db.Boolean, default=False)
    is_active = db.Column(db.Boolean, default=True)
    
    created_at = db.Column(db.DateTime(timezone=True), default=utcnow)
    updated_at = db.Column(db.DateTime(timezone=True), default=utcnow, onupdate=utcnow)

    # İlişkiler
    organization = db.relationship("Organization", backref=db.backref("payment_methods", lazy="dynamic"))

    def to_dict(self) -> dict:
        return {
            "id": str(self.id),
            "type": self.type,
            "card_brand": self.card_brand,
            "card_last4": self.card_last4,
            "card_exp_month": self.card_exp_month,
            "card_exp_year": self.card_exp_year,
            "is_default": self.is_default,
            "is_active": self.is_active,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }
