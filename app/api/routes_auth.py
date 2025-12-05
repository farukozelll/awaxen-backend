"""Kullanıcı kimlik doğrulama ve profil endpoint'leri."""
from flask import jsonify, request

from . import api_bp
from .helpers import get_or_create_user
from .. import db
from ..models import User
from ..auth import requires_auth


@api_bp.route('/me', methods=['GET'])
@requires_auth
def get_my_profile():
    """
    Token'daki kullanıcının profil bilgisini döner.
    ---
    tags:
      - Kullanıcı
    security:
      - bearerAuth: []
    responses:
      200:
        description: Kullanıcı profili
    """
    user = get_or_create_user()
    if not user:
        return jsonify({"error": "Kullanıcı bulunamadı"}), 401

    return jsonify({
        "id": user.id,
        "auth0_id": user.auth0_id,
        "email": user.email,
        "full_name": user.full_name,
        "role": user.role,
    })


@api_bp.route('/sync-user', methods=['POST'])
def sync_user():
    """
    Auth0 kullanıcısını Postgres ile senkronize et.
    ---
    tags:
      - Kullanıcı
    consumes:
      - application/json
    parameters:
      - in: header
        name: X-Auth0-Id
        required: false
        type: string
      - in: body
        name: payload
        required: true
        schema:
          type: object
          properties:
            auth0_id:
              type: string
              example: google-oauth2|123
            email:
              type: string
              example: user@awaxen.com
            name:
              type: string
              example: Awaxen User
            role:
              type: string
              example: farmer-user
    responses:
      200:
        description: Kullanıcı bilgileri güncellendi
    """
    payload = request.get_json(force=True, silent=True) or {}

    auth0_id = request.headers.get('X-Auth0-Id') or payload.get('auth0_id')
    email = request.headers.get('X-Auth0-Email') or payload.get('email')
    full_name = request.headers.get('X-Auth0-Name') or payload.get('name')
    role = request.headers.get('X-Auth0-Role') or payload.get('role', 'viewer')

    if not auth0_id:
        return jsonify({"error": "auth0_id eksik"}), 400

    user = User.query.filter_by(auth0_id=auth0_id).first()
    created = False

    if not user:
        user = User(
            auth0_id=auth0_id,
            email=email,
            full_name=full_name or 'Yeni Kullanıcı',
            role=role or 'viewer',
        )
        db.session.add(user)
        created = True
    else:
        user.email = email or user.email
        user.full_name = full_name or user.full_name
        if role:
            user.role = role

    db.session.commit()

    return jsonify({
        "message": "Kullanıcı senkronize edildi",
        "created": created,
        "user": {
            "id": user.id,
            "auth0_id": user.auth0_id,
            "email": user.email,
            "full_name": user.full_name,
            "role": user.role,
        },
    }), 200
