from flask import Blueprint, request, jsonify
import requests
from app import db
from app.models.whatsapp import WhatsAppConfig
from app.core.decorators import jwt_required

whatsapp_bp = Blueprint('whatsapp', __name__)

# Gupshup's documented WhatsApp send-message endpoint (their "Enterprise"
# API shape, form-encoded, apikey header). This is the commonly-documented
# contract as of when this was written — Gupshup's dashboard for your
# specific account is the source of truth. If the first test message fails
# with an auth/format error, check your dashboard's Quick Start page for
# the exact endpoint + payload shape and this function is the only place
# that needs to change.
GUPSHUP_SEND_URL = "https://api.gupshup.io/wa/api/v1/msg"


def _get_config():
    return WhatsAppConfig.query.first()


def send_whatsapp_message(to_number: str, message: str):
    """Sends a plain-text WhatsApp message via Gupshup. Raises ValueError if
    not configured, RuntimeError if the provider call fails. Callable from
    anywhere in the backend (e.g. low-stock alerts, daily report jobs) once
    a real config row exists."""
    config = _get_config()
    if not config or not config.is_active or not config.api_key or not config.sender_number:
        raise ValueError("WhatsApp is not configured yet — set it up in Admin > WhatsApp Settings.")

    response = requests.post(
        GUPSHUP_SEND_URL,
        headers={
            "apikey": config.api_key,
            "Content-Type": "application/x-www-form-urlencoded",
        },
        data={
            "channel": "whatsapp",
            "source": config.sender_number,
            "destination": to_number,
            "src.name": config.app_name or "",
            "message": f'{{"type":"text","text":"{message}"}}',
        },
        timeout=15,
    )

    if response.status_code >= 400:
        raise RuntimeError(f"Gupshup rejected the message ({response.status_code}): {response.text}")

    return response.json() if response.text else {}


@whatsapp_bp.route('/config', methods=['GET', 'OPTIONS'], strict_slashes=False)
@jwt_required
def get_config():
    if request.method == 'OPTIONS':
        return jsonify({}), 200

    config = _get_config()
    if not config:
        return jsonify({"status": "success", "data": None}), 200

    return jsonify({
        "status": "success",
        "data": {
            "provider": config.provider,
            "app_name": config.app_name,
            "sender_number": config.sender_number,
            "is_active": bool(config.is_active),
            # Never return the real key — just enough to confirm one is set.
            "api_key_last4": config.api_key[-4:] if config.api_key else None,
        },
    }), 200


@whatsapp_bp.route('/config', methods=['POST', 'OPTIONS'], strict_slashes=False)
@jwt_required
def save_config():
    if request.method == 'OPTIONS':
        return jsonify({}), 200

    data = request.get_json(silent=True) or {}
    api_key = data.get('api_key')
    app_name = data.get('app_name')
    sender_number = data.get('sender_number')

    if not api_key or not sender_number:
        return jsonify({"error": "api_key and sender_number are required"}), 400

    config = _get_config()
    if not config:
        config = WhatsAppConfig()
        db.session.add(config)

    config.provider = 'gupshup'
    config.api_key = api_key
    config.app_name = app_name
    config.sender_number = sender_number
    config.is_active = 1

    try:
        db.session.commit()
        return jsonify({"status": "success", "message": "WhatsApp settings saved"}), 200
    except Exception as e:
        db.session.rollback()
        return jsonify({"error": str(e)}), 500


@whatsapp_bp.route('/test', methods=['POST', 'OPTIONS'], strict_slashes=False)
@jwt_required
def send_test_message():
    if request.method == 'OPTIONS':
        return jsonify({}), 200

    data = request.get_json(silent=True) or {}
    to_number = data.get('to_number')
    if not to_number:
        return jsonify({"error": "to_number is required"}), 400

    try:
        result = send_whatsapp_message(to_number, "This is a test message from your factory app.")
        return jsonify({"status": "success", "message": "Test message sent.", "provider_response": result}), 200
    except ValueError as e:
        return jsonify({"error": str(e)}), 400
    except RuntimeError as e:
        return jsonify({"error": str(e)}), 502
