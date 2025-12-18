"""
Billing & Subscription API Endpoints - v6.0.

Stripe/Iyzico entegrasyonu için ödeme ve abonelik yönetimi.
"""
import os
import hmac
import hashlib
from datetime import datetime, timezone, timedelta
from flask import Blueprint, jsonify, request, current_app
from flasgger import swag_from

from app.extensions import db
from app.auth import requires_auth
from app.api.helpers import get_current_user, get_pagination_params, paginate_response
from app.models import (
    Organization, User,
    SubscriptionPlan, Subscription, Invoice, PaymentMethod
)

billing_bp = Blueprint("billing", __name__)


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


# ==========================================
# Subscription Plans
# ==========================================

@billing_bp.route("/plans", methods=["GET", "OPTIONS"])
@swag_from({
    "tags": ["Billing"],
    "summary": "Mevcut abonelik planlarını listele",
    "responses": {
        200: {
            "description": "Plan listesi",
            "schema": {
                "type": "array",
                "items": {"$ref": "#/definitions/SubscriptionPlan"}
            }
        }
    }
})
def list_plans():
    """Aktif abonelik planlarını listele."""
    plans = SubscriptionPlan.query.filter_by(is_active=True).order_by(SubscriptionPlan.sort_order).all()
    return jsonify([p.to_dict() for p in plans])


@billing_bp.route("/plans/<plan_code>", methods=["GET", "OPTIONS"])
@swag_from({
    "tags": ["Billing"],
    "summary": "Plan detayını getir",
    "parameters": [
        {"name": "plan_code", "in": "path", "type": "string", "required": True}
    ],
    "responses": {
        200: {"description": "Plan detayı"},
        404: {"description": "Plan bulunamadı"}
    }
})
def get_plan(plan_code):
    """Belirli bir planın detayını getir."""
    plan = SubscriptionPlan.query.filter_by(code=plan_code, is_active=True).first()
    if not plan:
        return jsonify({"error": "Plan not found"}), 404
    return jsonify(plan.to_dict())


# ==========================================
# Checkout & Payment
# ==========================================

@billing_bp.route("/checkout-session", methods=["POST", "OPTIONS"])
@requires_auth
@swag_from({
    "tags": ["Billing"],
    "summary": "Ödeme sayfası linki oluştur",
    "description": "Stripe/Iyzico checkout session oluşturur ve redirect URL döner.",
    "parameters": [
        {
            "name": "body",
            "in": "body",
            "required": True,
            "schema": {
                "type": "object",
                "properties": {
                    "plan_code": {"type": "string", "example": "pro"},
                    "billing_cycle": {"type": "string", "enum": ["monthly", "yearly"], "default": "monthly"},
                    "success_url": {"type": "string", "example": "https://app.awaxen.com/billing/success"},
                    "cancel_url": {"type": "string", "example": "https://app.awaxen.com/billing/cancel"}
                },
                "required": ["plan_code"]
            }
        }
    ],
    "responses": {
        200: {
            "description": "Checkout session oluşturuldu",
            "schema": {
                "type": "object",
                "properties": {
                    "checkout_url": {"type": "string"},
                    "session_id": {"type": "string"}
                }
            }
        },
        400: {"description": "Geçersiz istek"},
        404: {"description": "Plan bulunamadı"}
    }
})
def create_checkout_session():
    """Stripe/Iyzico checkout session oluştur."""
    user = get_current_user()
    if not user or not user.organization_id:
        return jsonify({"error": "Unauthorized"}), 401
    
    data = request.get_json()
    plan_code = data.get("plan_code")
    billing_cycle = data.get("billing_cycle", "monthly")
    success_url = data.get("success_url", os.getenv("FRONTEND_URL", "http://localhost:3005") + "/billing/success")
    cancel_url = data.get("cancel_url", os.getenv("FRONTEND_URL", "http://localhost:3005") + "/billing/cancel")
    
    # Plan kontrolü
    plan = SubscriptionPlan.query.filter_by(code=plan_code, is_active=True).first()
    if not plan:
        return jsonify({"error": "Plan not found"}), 404
    
    org = Organization.query.get(user.organization_id)
    if not org:
        return jsonify({"error": "Organization not found"}), 404
    
    # Fiyat hesapla
    price = plan.price_yearly if billing_cycle == "yearly" else plan.price_monthly
    
    # Ödeme sağlayıcı seçimi
    payment_provider = os.getenv("PAYMENT_PROVIDER", "stripe")
    
    if payment_provider == "stripe":
        return _create_stripe_session(org, plan, billing_cycle, price, success_url, cancel_url)
    elif payment_provider == "iyzico":
        return _create_iyzico_session(org, plan, billing_cycle, price, success_url, cancel_url)
    else:
        # Demo mode - gerçek ödeme yok
        return jsonify({
            "checkout_url": f"{success_url}?session_id=demo_{org.id}_{plan.code}",
            "session_id": f"demo_{org.id}_{plan.code}",
            "demo_mode": True,
            "message": "Payment provider not configured. Demo mode active."
        })


def _create_stripe_session(org, plan, billing_cycle, price, success_url, cancel_url):
    """Stripe Checkout Session oluştur."""
    try:
        import stripe
        stripe.api_key = os.getenv("STRIPE_SECRET_KEY")
        
        if not stripe.api_key:
            return jsonify({"error": "Stripe not configured"}), 500
        
        # Stripe customer oluştur veya getir
        existing_sub = Subscription.query.filter_by(
            organization_id=org.id,
            payment_provider="stripe"
        ).first()
        
        customer_id = existing_sub.provider_customer_id if existing_sub else None
        
        if not customer_id:
            customer = stripe.Customer.create(
                email=org.users.first().email if org.users.first() else None,
                name=org.name,
                metadata={"organization_id": str(org.id)}
            )
            customer_id = customer.id
        
        # Checkout session oluştur
        session = stripe.checkout.Session.create(
            customer=customer_id,
            payment_method_types=["card"],
            line_items=[{
                "price_data": {
                    "currency": plan.currency.lower(),
                    "product_data": {
                        "name": f"{plan.name} - {billing_cycle.capitalize()}",
                        "description": plan.description,
                    },
                    "unit_amount": int(float(price) * 100),  # Kuruş cinsinden
                    "recurring": {
                        "interval": "year" if billing_cycle == "yearly" else "month"
                    }
                },
                "quantity": 1
            }],
            mode="subscription",
            success_url=f"{success_url}?session_id={{CHECKOUT_SESSION_ID}}",
            cancel_url=cancel_url,
            metadata={
                "organization_id": str(org.id),
                "plan_code": plan.code,
                "billing_cycle": billing_cycle
            }
        )
        
        return jsonify({
            "checkout_url": session.url,
            "session_id": session.id
        })
        
    except ImportError:
        return jsonify({"error": "Stripe library not installed"}), 500
    except Exception as e:
        current_app.logger.error(f"Stripe error: {e}")
        return jsonify({"error": str(e)}), 500


def _create_iyzico_session(org, plan, billing_cycle, price, success_url, cancel_url):
    """Iyzico ödeme formu oluştur."""
    try:
        import iyzipay
        
        options = {
            'api_key': os.getenv("IYZICO_API_KEY"),
            'secret_key': os.getenv("IYZICO_SECRET_KEY"),
            'base_url': os.getenv("IYZICO_BASE_URL", "https://sandbox-api.iyzipay.com")
        }
        
        if not options['api_key']:
            return jsonify({"error": "Iyzico not configured"}), 500
        
        # Iyzico checkout form request
        request_data = {
            'locale': 'tr',
            'conversationId': str(org.id),
            'price': str(price),
            'paidPrice': str(price),
            'currency': 'TRY',
            'basketId': f"{org.id}_{plan.code}",
            'paymentGroup': 'SUBSCRIPTION',
            'callbackUrl': success_url,
            'enabledInstallments': [1],
            'buyer': {
                'id': str(org.id),
                'name': org.name[:30],
                'surname': 'Organization',
                'email': org.users.first().email if org.users.first() else 'noemail@awaxen.com',
                'identityNumber': '11111111111',
                'registrationAddress': 'Turkey',
                'city': 'Istanbul',
                'country': 'Turkey'
            },
            'billingAddress': {
                'contactName': org.name,
                'city': 'Istanbul',
                'country': 'Turkey',
                'address': 'Turkey'
            },
            'basketItems': [{
                'id': plan.code,
                'name': f"{plan.name} - {billing_cycle.capitalize()}",
                'category1': 'Subscription',
                'itemType': 'VIRTUAL',
                'price': str(price)
            }]
        }
        
        checkout_form = iyzipay.CheckoutFormInitialize().create(request_data, options)
        result = checkout_form.read()
        
        if result.get('status') == 'success':
            return jsonify({
                "checkout_url": result.get('paymentPageUrl'),
                "session_id": result.get('token')
            })
        else:
            return jsonify({"error": result.get('errorMessage', 'Iyzico error')}), 500
            
    except ImportError:
        return jsonify({"error": "Iyzico library not installed"}), 500
    except Exception as e:
        current_app.logger.error(f"Iyzico error: {e}")
        return jsonify({"error": str(e)}), 500


# ==========================================
# Webhooks
# ==========================================

@billing_bp.route("/webhook/stripe", methods=["POST"])
def stripe_webhook():
    """
    Stripe webhook endpoint.
    
    Ödeme başarılı/başarısız olduğunda Stripe buraya bildirim gönderir.
    """
    payload = request.data
    sig_header = request.headers.get("Stripe-Signature")
    webhook_secret = os.getenv("STRIPE_WEBHOOK_SECRET")
    
    if not webhook_secret:
        current_app.logger.warning("Stripe webhook secret not configured")
        return jsonify({"error": "Webhook not configured"}), 500
    
    try:
        import stripe
        event = stripe.Webhook.construct_event(payload, sig_header, webhook_secret)
    except ImportError:
        return jsonify({"error": "Stripe library not installed"}), 500
    except ValueError:
        return jsonify({"error": "Invalid payload"}), 400
    except stripe.error.SignatureVerificationError:
        return jsonify({"error": "Invalid signature"}), 400
    
    # Event işle
    event_type = event["type"]
    data = event["data"]["object"]
    
    current_app.logger.info(f"Stripe webhook: {event_type}")
    
    if event_type == "checkout.session.completed":
        _handle_checkout_completed(data)
    elif event_type == "invoice.paid":
        _handle_invoice_paid(data)
    elif event_type == "invoice.payment_failed":
        _handle_payment_failed(data)
    elif event_type == "customer.subscription.updated":
        _handle_subscription_updated(data)
    elif event_type == "customer.subscription.deleted":
        _handle_subscription_cancelled(data)
    
    return jsonify({"received": True})


@billing_bp.route("/webhook/iyzico", methods=["POST"])
def iyzico_webhook():
    """
    Iyzico webhook endpoint.
    
    Ödeme sonucu Iyzico buraya bildirim gönderir.
    """
    data = request.get_json() or request.form.to_dict()
    
    current_app.logger.info(f"Iyzico webhook: {data}")
    
    token = data.get("token")
    if not token:
        return jsonify({"error": "Missing token"}), 400
    
    try:
        import iyzipay
        
        options = {
            'api_key': os.getenv("IYZICO_API_KEY"),
            'secret_key': os.getenv("IYZICO_SECRET_KEY"),
            'base_url': os.getenv("IYZICO_BASE_URL", "https://sandbox-api.iyzipay.com")
        }
        
        # Ödeme sonucunu sorgula
        request_data = {'locale': 'tr', 'token': token}
        checkout_form = iyzipay.CheckoutForm().retrieve(request_data, options)
        result = checkout_form.read()
        
        if result.get('paymentStatus') == 'SUCCESS':
            org_id = result.get('basketId', '').split('_')[0]
            plan_code = result.get('basketId', '').split('_')[1] if '_' in result.get('basketId', '') else 'pro'
            
            _activate_subscription(org_id, plan_code, "iyzico", result.get('paymentId'))
            
        return jsonify({"received": True})
        
    except Exception as e:
        current_app.logger.error(f"Iyzico webhook error: {e}")
        return jsonify({"error": str(e)}), 500


def _handle_checkout_completed(data):
    """Checkout tamamlandığında aboneliği aktifleştir."""
    metadata = data.get("metadata", {})
    org_id = metadata.get("organization_id")
    plan_code = metadata.get("plan_code")
    billing_cycle = metadata.get("billing_cycle", "monthly")
    
    if not org_id or not plan_code:
        return
    
    _activate_subscription(
        org_id, plan_code, "stripe",
        data.get("subscription"),
        data.get("customer"),
        billing_cycle
    )


def _handle_invoice_paid(data):
    """Fatura ödendiğinde kaydet."""
    customer_id = data.get("customer")
    
    sub = Subscription.query.filter_by(
        provider_customer_id=customer_id,
        payment_provider="stripe"
    ).first()
    
    if not sub:
        return
    
    # Fatura oluştur
    invoice = Invoice(
        organization_id=sub.organization_id,
        subscription_id=sub.id,
        invoice_number=data.get("number", f"INV-{datetime.now().strftime('%Y%m%d%H%M%S')}"),
        amount=data.get("subtotal", 0) / 100,
        tax_amount=data.get("tax", 0) / 100,
        total_amount=data.get("total", 0) / 100,
        currency=data.get("currency", "try").upper(),
        status="paid",
        paid_at=utcnow(),
        payment_provider="stripe",
        provider_invoice_id=data.get("id"),
        line_items=[{
            "description": line.get("description"),
            "amount": line.get("amount", 0) / 100
        } for line in data.get("lines", {}).get("data", [])],
        pdf_url=data.get("invoice_pdf")
    )
    db.session.add(invoice)
    db.session.commit()


def _handle_payment_failed(data):
    """Ödeme başarısız olduğunda aboneliği askıya al."""
    customer_id = data.get("customer")
    
    sub = Subscription.query.filter_by(
        provider_customer_id=customer_id,
        payment_provider="stripe"
    ).first()
    
    if sub:
        sub.status = "past_due"
        db.session.commit()


def _handle_subscription_updated(data):
    """Abonelik güncellendiğinde kaydet."""
    sub = Subscription.query.filter_by(
        provider_subscription_id=data.get("id"),
        payment_provider="stripe"
    ).first()
    
    if sub:
        sub.current_period_start = datetime.fromtimestamp(data.get("current_period_start", 0), tz=timezone.utc)
        sub.current_period_end = datetime.fromtimestamp(data.get("current_period_end", 0), tz=timezone.utc)
        sub.cancel_at_period_end = data.get("cancel_at_period_end", False)
        db.session.commit()


def _handle_subscription_cancelled(data):
    """Abonelik iptal edildiğinde güncelle."""
    sub = Subscription.query.filter_by(
        provider_subscription_id=data.get("id"),
        payment_provider="stripe"
    ).first()
    
    if sub:
        sub.status = "cancelled"
        sub.cancelled_at = utcnow()
        
        # Organization'ı free plana düşür
        org = Organization.query.get(sub.organization_id)
        if org:
            org.subscription_status = "cancelled"
            org.subscription_plan = "free"
        
        db.session.commit()


def _activate_subscription(org_id, plan_code, provider, subscription_id=None, customer_id=None, billing_cycle="monthly"):
    """Aboneliği aktifleştir."""
    plan = SubscriptionPlan.query.filter_by(code=plan_code).first()
    if not plan:
        return
    
    org = Organization.query.get(org_id)
    if not org:
        return
    
    # Mevcut aktif aboneliği bul veya yeni oluştur
    sub = Subscription.query.filter_by(
        organization_id=org_id,
        status="active"
    ).first()
    
    if not sub:
        sub = Subscription(organization_id=org_id)
        db.session.add(sub)
    
    sub.plan_id = plan.id
    sub.status = "active"
    sub.billing_cycle = billing_cycle
    sub.payment_provider = provider
    sub.provider_subscription_id = subscription_id
    sub.provider_customer_id = customer_id
    sub.current_period_start = utcnow()
    sub.current_period_end = utcnow() + timedelta(days=365 if billing_cycle == "yearly" else 30)
    
    # Organization'ı güncelle
    org.subscription_status = "active"
    org.subscription_plan = plan_code
    
    db.session.commit()


# ==========================================
# Subscription Management
# ==========================================

@billing_bp.route("/subscription", methods=["GET", "OPTIONS"])
@requires_auth
@swag_from({
    "tags": ["Billing"],
    "summary": "Mevcut abonelik bilgisini getir",
    "responses": {
        200: {"description": "Abonelik bilgisi"},
        404: {"description": "Abonelik bulunamadı"}
    }
})
def get_subscription():
    """Organizasyonun mevcut aboneliğini getir."""
    user = get_current_user()
    if not user or not user.organization_id:
        return jsonify({"error": "Unauthorized"}), 401
    
    sub = Subscription.query.filter_by(
        organization_id=user.organization_id
    ).order_by(Subscription.created_at.desc()).first()
    
    if not sub:
        # Free plan varsayılan
        org = Organization.query.get(user.organization_id)
        return jsonify({
            "plan": {"code": "free", "name": "Free Plan"},
            "status": org.subscription_status if org else "active",
            "is_free": True
        })
    
    return jsonify(sub.to_dict())


@billing_bp.route("/subscription/cancel", methods=["POST", "OPTIONS"])
@requires_auth
@swag_from({
    "tags": ["Billing"],
    "summary": "Aboneliği iptal et",
    "description": "Dönem sonunda iptal edilir, hemen değil.",
    "responses": {
        200: {"description": "İptal talebi alındı"},
        404: {"description": "Aktif abonelik bulunamadı"}
    }
})
def cancel_subscription():
    """Aboneliği dönem sonunda iptal et."""
    user = get_current_user()
    if not user or not user.organization_id:
        return jsonify({"error": "Unauthorized"}), 401
    
    # Admin kontrolü
    user_role = user.role.code if user.role else None
    if user_role not in ["admin", "super_admin"]:
        return jsonify({"error": "Only admins can cancel subscription"}), 403
    
    sub = Subscription.query.filter_by(
        organization_id=user.organization_id,
        status="active"
    ).first()
    
    if not sub:
        return jsonify({"error": "No active subscription found"}), 404
    
    # Stripe'da iptal et
    if sub.payment_provider == "stripe" and sub.provider_subscription_id:
        try:
            import stripe
            stripe.api_key = os.getenv("STRIPE_SECRET_KEY")
            stripe.Subscription.modify(
                sub.provider_subscription_id,
                cancel_at_period_end=True
            )
        except Exception as e:
            current_app.logger.error(f"Stripe cancel error: {e}")
    
    sub.cancel_at_period_end = True
    db.session.commit()
    
    return jsonify({
        "message": "Subscription will be cancelled at period end",
        "cancel_at": sub.current_period_end.isoformat() if sub.current_period_end else None
    })


# ==========================================
# Invoices
# ==========================================

@billing_bp.route("/invoices", methods=["GET", "OPTIONS"])
@requires_auth
@swag_from({
    "tags": ["Billing"],
    "summary": "Fatura geçmişini listele",
    "parameters": [
        {"name": "page", "in": "query", "type": "integer", "default": 1},
        {"name": "pageSize", "in": "query", "type": "integer", "default": 20}
    ],
    "responses": {
        200: {"description": "Fatura listesi"}
    }
})
def list_invoices():
    """Organizasyonun faturalarını listele."""
    user = get_current_user()
    if not user or not user.organization_id:
        return jsonify({"error": "Unauthorized"}), 401
    
    page, page_size = get_pagination_params()
    
    query = Invoice.query.filter_by(
        organization_id=user.organization_id
    ).order_by(Invoice.created_at.desc())
    
    total = query.count()
    invoices = query.offset((page - 1) * page_size).limit(page_size).all()
    
    return jsonify(paginate_response([i.to_dict() for i in invoices], total, page, page_size))


@billing_bp.route("/invoices/<uuid:invoice_id>", methods=["GET", "OPTIONS"])
@requires_auth
@swag_from({
    "tags": ["Billing"],
    "summary": "Fatura detayını getir",
    "parameters": [
        {"name": "invoice_id", "in": "path", "type": "string", "required": True}
    ],
    "responses": {
        200: {"description": "Fatura detayı"},
        404: {"description": "Fatura bulunamadı"}
    }
})
def get_invoice(invoice_id):
    """Belirli bir faturanın detayını getir."""
    user = get_current_user()
    if not user or not user.organization_id:
        return jsonify({"error": "Unauthorized"}), 401
    
    invoice = Invoice.query.filter_by(
        id=invoice_id,
        organization_id=user.organization_id
    ).first()
    
    if not invoice:
        return jsonify({"error": "Invoice not found"}), 404
    
    return jsonify(invoice.to_dict())


# ==========================================
# Payment Methods
# ==========================================

@billing_bp.route("/payment-methods", methods=["GET", "OPTIONS"])
@requires_auth
@swag_from({
    "tags": ["Billing"],
    "summary": "Kayıtlı ödeme yöntemlerini listele",
    "responses": {
        200: {"description": "Ödeme yöntemleri listesi"}
    }
})
def list_payment_methods():
    """Organizasyonun kayıtlı ödeme yöntemlerini listele."""
    user = get_current_user()
    if not user or not user.organization_id:
        return jsonify({"error": "Unauthorized"}), 401
    
    methods = PaymentMethod.query.filter_by(
        organization_id=user.organization_id,
        is_active=True
    ).all()
    
    return jsonify([m.to_dict() for m in methods])
