"""
Awaxen Models - Wallet.

Cüzdan ve işlem modelleri.
"""
from datetime import datetime, timezone
from decimal import Decimal
from typing import Optional
import uuid

from sqlalchemy.dialects.postgresql import JSONB, UUID

from app.extensions import db


def utcnow() -> datetime:
    """Timezone-aware UTC datetime döndür."""
    return datetime.now(timezone.utc)


class Wallet(db.Model):
    """
    Kullanıcı Cüzdanı - Awaxen Coin (AWX) bakiyesi.
    
    Ledger mantığı: Bakiye her zaman transactions'dan hesaplanabilir.
    
    IMPORTANT: Race condition koruması için bakiye güncellemelerinde
    db.session.refresh(wallet, with_for_update=True) kullanılmalıdır.
    """
    __tablename__ = "wallets"
    
    # CHECK constraint - bakiye negatif olamaz
    __table_args__ = (
        db.CheckConstraint('balance >= 0', name='check_wallet_balance_positive'),
        db.CheckConstraint('lifetime_earned >= 0', name='check_wallet_earned_positive'),
        db.CheckConstraint('lifetime_spent >= 0', name='check_wallet_spent_positive'),
        db.CheckConstraint('level >= 1', name='check_wallet_level_positive'),
        db.CheckConstraint('xp >= 0', name='check_wallet_xp_positive'),
    )

    id = db.Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = db.Column(UUID(as_uuid=True), db.ForeignKey("users.id"), unique=True, nullable=False, index=True)
    
    balance = db.Column(db.Numeric(12, 2), default=0.0, nullable=False)
    currency = db.Column(db.String(10), default="AWX")
    
    lifetime_earned = db.Column(db.Numeric(12, 2), default=0.0, nullable=False)
    lifetime_spent = db.Column(db.Numeric(12, 2), default=0.0, nullable=False)
    
    level = db.Column(db.Integer, default=1, nullable=False)
    xp = db.Column(db.Integer, default=0, nullable=False)
    
    is_active = db.Column(db.Boolean, default=True, index=True)
    created_at = db.Column(db.DateTime(timezone=True), default=utcnow, index=True)
    updated_at = db.Column(db.DateTime(timezone=True), default=utcnow, onupdate=utcnow)

    # İlişkiler
    user = db.relationship("User", backref=db.backref("wallet", uselist=False))
    transactions = db.relationship("WalletTransaction", backref="wallet", lazy="dynamic",
                                  cascade="all, delete-orphan")

    def to_dict(self) -> dict:
        return {
            "id": str(self.id),
            "user_id": str(self.user_id),
            "balance": float(self.balance) if self.balance else 0.0,
            "currency": self.currency,
            "lifetime_earned": float(self.lifetime_earned) if self.lifetime_earned else 0.0,
            "lifetime_spent": float(self.lifetime_spent) if self.lifetime_spent else 0.0,
            "level": self.level,
            "xp": self.xp,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }
    
    def add_balance(self, amount: Decimal) -> None:
        """Bakiye ekle."""
        self.balance = Decimal(str(self.balance or 0)) + amount
        if amount > 0:
            self.lifetime_earned = Decimal(str(self.lifetime_earned or 0)) + amount
    
    def subtract_balance(self, amount: Decimal) -> bool:
        """Bakiye çıkar. Yetersiz bakiye durumunda False döner."""
        current = Decimal(str(self.balance or 0))
        if current < amount:
            return False
        self.balance = current - amount
        self.lifetime_spent = Decimal(str(self.lifetime_spent or 0)) + amount
        return True
    
    def add_xp(self, xp_amount: int) -> None:
        """XP ekle ve seviye kontrolü yap."""
        self.xp = (self.xp or 0) + xp_amount
        self._check_level_up()
    
    def _check_level_up(self) -> None:
        """Seviye atlama kontrolü."""
        while self.xp >= self._get_next_level_xp():
            self.level += 1
    
    def _get_next_level_xp(self) -> int:
        """Sonraki seviye için gereken XP."""
        return (self.level + 1) ** 2 * 100
    
    @classmethod
    def get_or_create(cls, user_id: uuid.UUID) -> "Wallet":
        """Cüzdanı getir veya oluştur."""
        wallet = cls.query.filter_by(user_id=user_id).first()
        if not wallet:
            wallet = cls(user_id=user_id)
            db.session.add(wallet)
            db.session.commit()
        return wallet


class WalletTransaction(db.Model):
    """
    Cüzdan İşlem Geçmişi - Çift defter (Double Entry) mantığı.
    """
    __tablename__ = "wallet_transactions"

    id = db.Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    wallet_id = db.Column(UUID(as_uuid=True), db.ForeignKey("wallets.id"), nullable=False, index=True)
    
    amount = db.Column(db.Numeric(12, 2), nullable=False)
    balance_after = db.Column(db.Numeric(12, 2))
    
    transaction_type = db.Column(db.String(30), nullable=False, index=True)
    category = db.Column(db.String(50), index=True)
    
    description = db.Column(db.String(255))
    reference_id = db.Column(db.String(100))
    reference_type = db.Column(db.String(50))
    
    extra_data = db.Column(JSONB, default=dict)
    
    created_at = db.Column(db.DateTime(timezone=True), default=utcnow, index=True)

    def to_dict(self) -> dict:
        return {
            "id": str(self.id),
            "wallet_id": str(self.wallet_id),
            "amount": float(self.amount) if self.amount else 0.0,
            "balance_after": float(self.balance_after) if self.balance_after else 0.0,
            "transaction_type": self.transaction_type,
            "category": self.category,
            "description": self.description,
            "reference_id": self.reference_id,
            "reference_type": self.reference_type,
            "extra_data": self.extra_data or {},
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }
