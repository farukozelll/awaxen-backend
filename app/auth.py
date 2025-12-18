"""
Auth0 JWT Token doğrulama decorator'ı.
Frontend'den gelen Bearer Token'ı çözer ve kullanıcı bilgisini request'e ekler.
"""

import os
from functools import wraps

import jwt
from flask import request, jsonify, g
from jwt import PyJWKClient

# Auth0 ayarları (.env'den okunacak)
AUTH0_DOMAIN = os.getenv("AUTH0_DOMAIN", "dev-xxxxx.us.auth0.com")
AUTH0_AUDIENCE = os.getenv("AUTH0_AUDIENCE", "https://api.awaxen.com")
ALGORITHMS = ["RS256"]


def get_token_from_header():
    """Authorization header'dan Bearer token'ı çıkarır."""
    auth_header = request.headers.get("Authorization", None)

    if not auth_header:
        return None

    parts = auth_header.split()

    if parts[0].lower() != "bearer" or len(parts) != 2:
        return None

    return parts[1]


def requires_auth(f):
    """
    Token doğrulama decorator'ı.
    Bu decorator'ı kullanan endpoint'ler sadece geçerli token ile erişilebilir.
    Token'dan çıkan kullanıcı bilgisi g.current_user'a yazılır.
    
    Not: OPTIONS istekleri (CORS preflight) auth gerektirmez.
    """

    @wraps(f)
    def decorated(*args, **kwargs):
        # CORS preflight isteklerini bypass et
        if request.method == "OPTIONS":
            return "", 200
        
        token = get_token_from_header()

        if not token:
            return jsonify({"error": "Token bulunamadı", "code": "missing_token"}), 401

        try:
            # Auth0'un public key'lerini al
            jwks_url = f"https://{AUTH0_DOMAIN}/.well-known/jwks.json"
            jwks_client = PyJWKClient(jwks_url)
            signing_key = jwks_client.get_signing_key_from_jwt(token)

            # Token'ı doğrula ve decode et
            payload = jwt.decode(
                token,
                signing_key.key,
                algorithms=ALGORITHMS,
                audience=AUTH0_AUDIENCE,
                issuer=f"https://{AUTH0_DOMAIN}/",
            )

            # Kullanıcı bilgisini request context'e ekle
            g.current_user = payload

        except jwt.ExpiredSignatureError:
            return jsonify({"error": "Token süresi dolmuş", "code": "token_expired"}), 401
        except jwt.InvalidAudienceError:
            return jsonify({"error": "Geçersiz audience", "code": "invalid_audience"}), 401
        except jwt.InvalidIssuerError:
            return jsonify({"error": "Geçersiz issuer", "code": "invalid_issuer"}), 401
        except Exception as e:
            return jsonify({"error": f"Token doğrulanamadı: {str(e)}", "code": "invalid_token"}), 401

        return f(*args, **kwargs)

    return decorated


def get_current_user_id():
    """Token'dan auth0_id'yi döndürür."""
    if hasattr(g, "current_user") and g.current_user:
        return g.current_user.get("sub")
    return None


def requires_role(*allowed_roles):
    """
    Rol bazlı yetkilendirme decorator'ı.
    
    Kullanım:
        @requires_auth
        @requires_role('admin', 'super_admin')
        def admin_only_endpoint():
            ...
    
    Args:
        *allowed_roles: İzin verilen rol kodları (örn: 'admin', 'super_admin', 'viewer')
    
    Not: Bu decorator @requires_auth'dan SONRA kullanılmalıdır.
    """
    def decorator(f):
        @wraps(f)
        def decorated(*args, **kwargs):
            # Lazy import to avoid circular dependency
            from app.models import User
            
            auth0_id = get_current_user_id()
            if not auth0_id:
                return jsonify({"error": "Kullanıcı bulunamadı", "code": "user_not_found"}), 401
            
            user = User.query.filter_by(auth0_id=auth0_id).first()
            if not user:
                return jsonify({"error": "Kullanıcı veritabanında bulunamadı", "code": "user_not_in_db"}), 401
            
            # Rol kontrolü (RBAC - role tablosundan)
            user_role_code = user.role.code if user.role else None
            if user_role_code not in allowed_roles:
                return jsonify({
                    "error": "Bu işlem için yetkiniz yok",
                    "code": "forbidden",
                    "required_roles": list(allowed_roles),
                    "your_role": user_role_code
                }), 403
            
            # Kullanıcıyı g'ye ekle (endpoint'te tekrar sorgu yapılmasın)
            g.db_user = user
            
            return f(*args, **kwargs)
        return decorated
    return decorator


def requires_permission(*required_permissions):
    """
    Yetki bazlı yetkilendirme decorator'ı (Granüler kontrol).
    
    Kullanım:
        @requires_auth
        @requires_permission('can_edit_devices', 'can_delete_devices')
        def device_management_endpoint():
            ...
    
    Args:
        *required_permissions: Gerekli yetki kodları (herhangi biri yeterli)
    
    Not: Bu decorator @requires_auth'dan SONRA kullanılmalıdır.
    """
    def decorator(f):
        @wraps(f)
        def decorated(*args, **kwargs):
            from app.models import User
            
            auth0_id = get_current_user_id()
            if not auth0_id:
                return jsonify({"error": "Kullanıcı bulunamadı", "code": "user_not_found"}), 401
            
            user = User.query.filter_by(auth0_id=auth0_id).first()
            if not user:
                return jsonify({"error": "Kullanıcı veritabanında bulunamadı", "code": "user_not_in_db"}), 401
            
            # Yetki kontrolü (herhangi biri yeterli)
            if not user.has_any_permission(*required_permissions):
                return jsonify({
                    "error": "Bu işlem için yetkiniz yok",
                    "code": "forbidden",
                    "required_permissions": list(required_permissions),
                    "your_permissions": [p.code for p in user.role.permissions] if user.role else []
                }), 403
            
            g.db_user = user
            return f(*args, **kwargs)
        return decorated
    return decorator


def get_db_user():
    """
    requires_role/requires_permission decorator'ı tarafından cache'lenen kullanıcıyı döndür.
    Eğer yoksa veritabanından çeker.
    """
    if hasattr(g, 'db_user') and g.db_user:
        return g.db_user
    
    # Fallback: veritabanından çek
    from app.models import User
    auth0_id = get_current_user_id()
    if auth0_id:
        return User.query.filter_by(auth0_id=auth0_id).first()
    return None
