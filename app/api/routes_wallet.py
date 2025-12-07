"""
Wallet (Cüzdan) API - Oyunlaştırma ve Ödül Sistemi.

Awaxen Coin (AWX) yönetimi, işlem geçmişi ve seviye sistemi.
"""
from decimal import Decimal
from flask import jsonify, request

from . import api_bp
from .helpers import get_current_user, get_pagination_params, paginate_response
from app.extensions import db
from app.models import Wallet, WalletTransaction, User
from app.auth import requires_auth


@api_bp.route('/wallet', methods=['GET'])
@requires_auth
def get_my_wallet():
    """
    Kullanıcının cüzdan bilgilerini getir.
    ---
    tags:
      - Wallet
    security:
      - bearerAuth: []
    responses:
      200:
        description: Cüzdan bilgileri
        schema:
          type: object
          properties:
            id:
              type: string
              format: uuid
            balance:
              type: number
              example: 150.50
            currency:
              type: string
              example: AWX
            level:
              type: integer
              example: 3
            xp:
              type: integer
              example: 450
            lifetime_earned:
              type: number
              example: 500.00
            lifetime_spent:
              type: number
              example: 349.50
            next_level_xp:
              type: integer
              example: 500
              description: Sonraki seviye için gereken XP
      401:
        description: Yetkisiz erişim
    """
    user = get_current_user()
    if not user:
        return jsonify({"error": "Unauthorized"}), 401
    
    # Cüzdan yoksa oluştur
    wallet = Wallet.query.filter_by(user_id=user.id).first()
    if not wallet:
        wallet = Wallet(user_id=user.id)
        db.session.add(wallet)
        db.session.commit()
    
    result = wallet.to_dict()
    
    # Seviye sistemi bilgileri
    result["next_level_xp"] = _get_next_level_xp(wallet.level)
    result["level_progress"] = _get_level_progress(wallet.xp, wallet.level)
    
    return jsonify(result)


@api_bp.route('/wallet/transactions', methods=['GET'])
@requires_auth
def get_wallet_transactions():
    """
    Cüzdan işlem geçmişini listele.
    ---
    tags:
      - Wallet
    security:
      - bearerAuth: []
    parameters:
      - name: page
        in: query
        type: integer
        default: 1
        description: Sayfa numarası
      - name: pageSize
        in: query
        type: integer
        default: 20
        description: Sayfa başına kayıt (max 100)
      - name: type
        in: query
        type: string
        enum: [reward, penalty, withdrawal, bonus, referral]
        description: İşlem tipine göre filtrele
      - name: category
        in: query
        type: string
        enum: [energy_saving, automation, challenge, manual]
        description: Kategoriye göre filtrele
    responses:
      200:
        description: İşlem listesi
        schema:
          type: object
          properties:
            data:
              type: array
              items:
                $ref: '#/definitions/WalletTransaction'
            pagination:
              $ref: '#/definitions/Pagination'
      401:
        description: Yetkisiz erişim
    definitions:
      WalletTransaction:
        type: object
        properties:
          id:
            type: string
            format: uuid
          amount:
            type: number
            example: 10.00
          balance_after:
            type: number
            example: 160.50
          transaction_type:
            type: string
            example: reward
          category:
            type: string
            example: energy_saving
          description:
            type: string
            example: Enerji tasarrufu ödülü
          created_at:
            type: string
            format: date-time
    """
    user = get_current_user()
    if not user:
        return jsonify({"error": "Unauthorized"}), 401
    
    wallet = Wallet.query.filter_by(user_id=user.id).first()
    if not wallet:
        return jsonify(paginate_response([], 0, 1, 20))
    
    page, page_size = get_pagination_params()
    tx_type = request.args.get('type')
    category = request.args.get('category')
    
    query = WalletTransaction.query.filter_by(wallet_id=wallet.id)
    
    if tx_type:
        query = query.filter_by(transaction_type=tx_type)
    if category:
        query = query.filter_by(category=category)
    
    query = query.order_by(WalletTransaction.created_at.desc())
    
    total = query.count()
    transactions = query.offset((page - 1) * page_size).limit(page_size).all()
    
    return jsonify(paginate_response(
        [t.to_dict() for t in transactions],
        total, page, page_size
    ))


@api_bp.route('/wallet/reward', methods=['POST'])
@requires_auth
def add_reward():
    """
    Kullanıcıya ödül ekle (Admin/System).
    ---
    tags:
      - Wallet
    security:
      - bearerAuth: []
    consumes:
      - application/json
    parameters:
      - name: body
        in: body
        required: true
        schema:
          type: object
          required:
            - amount
            - description
          properties:
            user_id:
              type: string
              format: uuid
              description: Hedef kullanıcı (admin için). Belirtilmezse kendi cüzdanı.
            amount:
              type: number
              example: 10.0
              description: Ödül miktarı (pozitif)
            category:
              type: string
              enum: [energy_saving, automation, challenge, manual, referral]
              example: energy_saving
            description:
              type: string
              example: Enerji tasarrufu ödülü
            reference_id:
              type: string
              description: İlişkili kayıt ID
            reference_type:
              type: string
              enum: [automation, challenge, device, manual]
    responses:
      201:
        description: Ödül eklendi
        schema:
          type: object
          properties:
            message:
              type: string
            transaction:
              $ref: '#/definitions/WalletTransaction'
            new_balance:
              type: number
      400:
        description: Geçersiz miktar
      401:
        description: Yetkisiz erişim
    """
    user = get_current_user()
    if not user:
        return jsonify({"error": "Unauthorized"}), 401
    
    data = request.get_json() or {}
    
    amount = data.get("amount")
    if not amount or float(amount) <= 0:
        return jsonify({"error": "Amount must be positive"}), 400
    
    description = data.get("description")
    if not description:
        return jsonify({"error": "Description is required"}), 400
    
    # Hedef kullanıcı (admin için)
    target_user_id = data.get("user_id") or user.id
    
    # Admin kontrolü (kendi dışında birine ödül vermek için)
    user_role_code = user.role.code if user.role else None
    if str(target_user_id) != str(user.id) and user_role_code not in ["admin", "super_admin"]:
        return jsonify({"error": "Forbidden"}), 403
    
    # Cüzdanı bul veya oluştur
    wallet = Wallet.query.filter_by(user_id=target_user_id).first()
    if not wallet:
        wallet = Wallet(user_id=target_user_id)
        db.session.add(wallet)
        db.session.flush()
    
    # İşlem oluştur
    amount_decimal = Decimal(str(amount))
    new_balance = Decimal(str(wallet.balance or 0)) + amount_decimal
    
    transaction = WalletTransaction(
        wallet_id=wallet.id,
        amount=amount_decimal,
        balance_after=new_balance,
        transaction_type="reward",
        category=data.get("category", "manual"),
        description=description,
        reference_id=data.get("reference_id"),
        reference_type=data.get("reference_type"),
    )
    
    # Cüzdanı güncelle
    wallet.balance = new_balance
    wallet.lifetime_earned = Decimal(str(wallet.lifetime_earned or 0)) + amount_decimal
    
    # XP ekle (her 1 AWX = 10 XP)
    xp_earned = int(float(amount) * 10)
    wallet.xp = (wallet.xp or 0) + xp_earned
    
    # Seviye kontrolü
    _check_level_up(wallet)
    
    db.session.add(transaction)
    db.session.commit()
    
    return jsonify({
        "message": "Reward added successfully",
        "transaction": transaction.to_dict(),
        "new_balance": float(new_balance),
        "xp_earned": xp_earned,
        "level": wallet.level,
    }), 201


@api_bp.route('/wallet/stats', methods=['GET'])
@requires_auth
def get_wallet_stats():
    """
    Cüzdan istatistiklerini getir.
    ---
    tags:
      - Wallet
    security:
      - bearerAuth: []
    responses:
      200:
        description: Cüzdan istatistikleri
        schema:
          type: object
          properties:
            total_earned_this_month:
              type: number
            total_transactions_this_month:
              type: integer
            top_category:
              type: string
            streak_days:
              type: integer
              description: Ardışık aktif gün sayısı
      401:
        description: Yetkisiz erişim
    """
    from datetime import datetime, timedelta
    from sqlalchemy import func
    
    user = get_current_user()
    if not user:
        return jsonify({"error": "Unauthorized"}), 401
    
    wallet = Wallet.query.filter_by(user_id=user.id).first()
    if not wallet:
        return jsonify({
            "total_earned_this_month": 0,
            "total_transactions_this_month": 0,
            "top_category": None,
            "streak_days": 0,
        })
    
    # Bu ay başlangıcı
    now = datetime.utcnow()
    month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    
    # Bu ayki toplam kazanç
    monthly_earned = db.session.query(func.sum(WalletTransaction.amount)).filter(
        WalletTransaction.wallet_id == wallet.id,
        WalletTransaction.transaction_type == "reward",
        WalletTransaction.created_at >= month_start
    ).scalar() or 0
    
    # Bu ayki işlem sayısı
    monthly_count = WalletTransaction.query.filter(
        WalletTransaction.wallet_id == wallet.id,
        WalletTransaction.created_at >= month_start
    ).count()
    
    # En çok ödül alınan kategori
    top_category = db.session.query(
        WalletTransaction.category,
        func.sum(WalletTransaction.amount).label('total')
    ).filter(
        WalletTransaction.wallet_id == wallet.id,
        WalletTransaction.transaction_type == "reward"
    ).group_by(WalletTransaction.category).order_by(
        func.sum(WalletTransaction.amount).desc()
    ).first()
    
    # Streak hesaplama: Ardışık gün sayısı (ödül alınan)
    streak_days = _calculate_streak_days(wallet.id)
    
    return jsonify({
        "total_earned_this_month": float(monthly_earned),
        "total_transactions_this_month": monthly_count,
        "top_category": top_category[0] if top_category else None,
        "streak_days": streak_days,
    })


def _calculate_streak_days(wallet_id) -> int:
    """
    Ardışık gün sayısını hesapla (son kaç gündür ödül alınmış).
    
    Örnek: Bugün, dün ve önceki gün ödül aldıysa streak = 3
    """
    from datetime import date, timedelta
    
    today = date.today()
    streak = 0
    
    # Son 365 günü kontrol et (makul bir limit)
    for i in range(365):
        check_date = today - timedelta(days=i)
        day_start = datetime.combine(check_date, datetime.min.time())
        day_end = datetime.combine(check_date, datetime.max.time())
        
        # O gün ödül var mı?
        has_reward = WalletTransaction.query.filter(
            WalletTransaction.wallet_id == wallet_id,
            WalletTransaction.transaction_type == "reward",
            WalletTransaction.amount > 0,
            WalletTransaction.created_at >= day_start,
            WalletTransaction.created_at <= day_end
        ).first()
        
        if has_reward:
            streak += 1
        else:
            # Bugün değilse streak kırıldı
            if i > 0:
                break
            # Bugün ödül yoksa streak 0
    
    return streak


@api_bp.route('/wallet/leaderboard', methods=['GET'])
@requires_auth
def get_leaderboard():
    """
    Organizasyon liderlik tablosu.
    ---
    tags:
      - Wallet
    security:
      - bearerAuth: []
    parameters:
      - name: limit
        in: query
        type: integer
        default: 10
        description: Kaç kullanıcı gösterilsin
    responses:
      200:
        description: Liderlik tablosu
        schema:
          type: object
          properties:
            leaderboard:
              type: array
              items:
                type: object
                properties:
                  rank:
                    type: integer
                  user_name:
                    type: string
                  balance:
                    type: number
                  level:
                    type: integer
            my_rank:
              type: integer
      401:
        description: Yetkisiz erişim
    """
    user = get_current_user()
    if not user or not user.organization_id:
        return jsonify({"error": "Unauthorized"}), 401
    
    limit = request.args.get('limit', 10, type=int)
    limit = min(limit, 50)  # Max 50
    
    # Organizasyondaki kullanıcıların cüzdanları
    leaderboard_query = db.session.query(
        Wallet, User
    ).join(User).filter(
        User.organization_id == user.organization_id,
        Wallet.is_active == True
    ).order_by(Wallet.balance.desc()).limit(limit).all()
    
    leaderboard = []
    for rank, (wallet, u) in enumerate(leaderboard_query, 1):
        leaderboard.append({
            "rank": rank,
            "user_id": str(u.id),
            "user_name": u.full_name or u.email.split("@")[0],
            "balance": float(wallet.balance) if wallet.balance else 0,
            "level": wallet.level,
        })
    
    # Kullanıcının sırası
    my_wallet = Wallet.query.filter_by(user_id=user.id).first()
    my_rank = None
    if my_wallet:
        higher_count = Wallet.query.join(User).filter(
            User.organization_id == user.organization_id,
            Wallet.balance > (my_wallet.balance or 0)
        ).count()
        my_rank = higher_count + 1
    
    return jsonify({
        "leaderboard": leaderboard,
        "my_rank": my_rank,
    })


# ==========================================
# HELPER FUNCTIONS
# ==========================================

def _get_next_level_xp(current_level: int) -> int:
    """Sonraki seviye için gereken toplam XP."""
    # Seviye formülü: level^2 * 100
    return (current_level + 1) ** 2 * 100


def _get_level_progress(xp: int, level: int) -> float:
    """Mevcut seviyedeki ilerleme yüzdesi."""
    current_level_xp = level ** 2 * 100
    next_level_xp = (level + 1) ** 2 * 100
    
    if xp <= current_level_xp:
        return 0.0
    
    progress = (xp - current_level_xp) / (next_level_xp - current_level_xp)
    return min(progress * 100, 100.0)


def _check_level_up(wallet: Wallet):
    """Seviye atlama kontrolü."""
    while wallet.xp >= _get_next_level_xp(wallet.level):
        wallet.level += 1
