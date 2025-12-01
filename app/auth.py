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
    """

    @wraps(f)
    def decorated(*args, **kwargs):
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
