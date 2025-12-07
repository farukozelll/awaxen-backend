from pathlib import Path

from flask import Blueprint, current_app, jsonify
from flasgger import swag_from

from app.auth import requires_auth
from app.version import APP_VERSION, BUILD_METADATA

meta_bp = Blueprint("meta", __name__)


@meta_bp.route("/health", methods=["GET"])
@swag_from({
    "tags": ["Meta"],
    "summary": "Health check & sürüm bilgisi",
    "responses": {
        200: {
            "description": "Uygulama sağlığı",
            "schema": {
                "$ref": "#/definitions/MetaHealthResponse"
            },
        }
    },
    "definitions": {
        "MetaHealthResponse": {
            "type": "object",
            "properties": {
                "status": {"type": "string", "example": "healthy"},
                "version": {"type": "string", "example": "v6.1.0"},
                "environment": {"type": "string", "example": "production"},
            }
        }
    },
})
def health_check():
    return jsonify({
        "status": "healthy",
        "version": APP_VERSION,
        "environment": current_app.config.get("FLASK_ENV", "production"),
    })


@meta_bp.route("/version", methods=["GET"])
@swag_from({
    "tags": ["Meta"],
    "summary": "Sürüm bilgisi",
    "responses": {
        200: {
            "description": "Version",
            "schema": {"$ref": "#/definitions/MetaVersionResponse"}
        }
    },
    "definitions": {
        "MetaVersionResponse": {
            "type": "object",
            "properties": {
                "version": {"type": "string", "example": "v6.1.0"},
                "build": {
                    "type": "object",
                    "properties": {
                        "codename": {"type": "string", "example": "Orion"},
                        "released_at": {"type": "string", "format": "date-time"}
                    }
                }
            }
        }
    },
})
def get_version():
    return jsonify({
        "version": APP_VERSION,
        "build": BUILD_METADATA,
    })


@meta_bp.route("/changelog", methods=["GET"])
@requires_auth
@swag_from({
    "tags": ["Meta"],
    "summary": "Changelog listesi",
    "responses": {
        200: {
            "description": "Changelog",
            "schema": {
                "type": "array",
                "items": {"$ref": "#/definitions/ChangelogEntry"}
            }
        }
    },
    "definitions": {
        "ChangelogEntry": {
            "type": "object",
            "properties": {
                "version": {"type": "string", "example": "v6.1.0"},
                "codename": {"type": "string", "example": "Orion"},
                "released_at": {"type": "string", "format": "date-time"},
                "highlights": {
                    "type": "array",
                    "items": {"type": "string"}
                }
            }
        }
    },
})
def get_changelog():
    changelog_path = Path(current_app.root_path) / "data" / "changelog.json"
    if not changelog_path.exists():
        return jsonify([])
    import json

    with changelog_path.open("r", encoding="utf-8") as f:
        data = json.load(f)
    return jsonify(data)
