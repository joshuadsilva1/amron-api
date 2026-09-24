from flask import Blueprint, request, jsonify
from app import db
from app.models.whatsapp import WhatsAppConfig, ReportSubscription
from app.models.department import Department
from app.core.decorators import jwt_required, permission_required
from app.core.whatsapp import send_whatsapp_message, normalize_number, get_config as _get_config, PROVIDERS
from app.core.daily_report import TIME_RE, build_report, send_report
from app.core.audit import log_audit

whatsapp_bp = Blueprint('whatsapp', __name__)


@whatsapp_bp.route('/config', methods=['GET', 'OPTIONS'], strict_slashes=False)
@jwt_required
@permission_required('admin_access')
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
@permission_required('admin_access')
def save_config():
    if request.method == 'OPTIONS':
        return jsonify({}), 200

    data = request.get_json(silent=True) or {}
    provider = (data.get('provider') or 'gupshup').lower()
    api_key = data.get('api_key')
    app_name = data.get('app_name')
    sender_number = data.get('sender_number')

    if provider not in PROVIDERS:
        return jsonify({"error": f"provider must be one of: {', '.join(PROVIDERS)}"}), 400
    if not api_key or not sender_number:
        label = "your WhatsApp number" if provider == 'callmebot' else "sender_number"
        return jsonify({"error": f"api_key and {label} are required"}), 400
    try:
        # CallMeBot: `sender_number` holds the owner's activated number, which
        # is also the only number it can message — store it normalized so the
        # recipient check compares like with like.
        if provider == 'callmebot':
            sender_number = normalize_number(sender_number)
    except ValueError as e:
        return jsonify({"error": str(e)}), 400

    config = _get_config()
    is_new = not config
    before = None if is_new else {"provider": config.provider, "sender_number": config.sender_number}
    if is_new:
        config = WhatsAppConfig()
        db.session.add(config)

    config.provider = provider
    config.api_key = api_key
    config.app_name = app_name
    config.sender_number = sender_number
    config.is_active = 1

    # Never write the actual key to the audit trail — only that it changed.
    log_audit(
        'whatsapp.config.update', 'whatsapp_config', None,
        payload_before=before,
        payload_after={"provider": provider, "sender_number": sender_number, "api_key": "***redacted***"},
    )

    try:
        db.session.commit()
        return jsonify({"status": "success", "message": "WhatsApp settings saved"}), 200
    except Exception as e:
        db.session.rollback()
        return jsonify({"error": str(e)}), 500


@whatsapp_bp.route('/test', methods=['POST', 'OPTIONS'], strict_slashes=False)
@jwt_required
@permission_required('admin_access')
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


# ==========================================
# DAILY REPORTS — who gets which report, and when. The actual sending at
# the chosen time is done by the scheduled job (`flask send-daily-reports`,
# see core/daily_report.py and render.yaml); these endpoints manage the
# settings and let a person send/preview one on demand.
# ==========================================

def _dept_arg():
    return request.args.get('department_id') or None


def _find_subscription(department_id):
    q = ReportSubscription.query
    q = q.filter(ReportSubscription.department_id.is_(None)) if department_id is None else q.filter_by(department_id=department_id)
    return q.first()


def _serialize_subscription(sub):
    if not sub:
        return None
    return {
        "recipient_number": sub.recipient_number,
        "send_time": sub.send_time,
        "is_enabled": bool(sub.is_enabled),
        "last_sent_on": sub.last_sent_on.isoformat() if sub.last_sent_on else None,
        "last_status": sub.last_status,
        "last_error": sub.last_error,
    }


@whatsapp_bp.route('/reports', methods=['GET', 'OPTIONS'], strict_slashes=False)
@jwt_required
@permission_required('manage_reports')
def list_report_sections():
    """Every report that can be scheduled (whole factory + each active
    department) with its current subscription, if any."""
    if request.method == 'OPTIONS':
        return jsonify({}), 200

    subs = {sub.department_id: sub for sub in ReportSubscription.query.all()}
    sections = [{"department_id": None, "name": "Whole Factory", "subscription": _serialize_subscription(subs.get(None))}]
    for d in Department.query.filter_by(is_active=1).order_by(Department.department_code).all():
        sections.append({"department_id": d.id, "name": d.name, "subscription": _serialize_subscription(subs.get(d.id))})
    return jsonify({"status": "success", "data": sections}), 200


@whatsapp_bp.route('/reports', methods=['PUT', 'OPTIONS'], strict_slashes=False)
@jwt_required
@permission_required('manage_reports')
def save_report_subscription():
    """Body: {department_id (null = whole factory), recipient_number,
    send_time "HH:MM", is_enabled}"""
    if request.method == 'OPTIONS':
        return jsonify({}), 200

    data = request.get_json(silent=True) or {}
    department_id = data.get('department_id') or None
    send_time = (data.get('send_time') or '').strip()

    if department_id and not Department.query.get(department_id):
        return jsonify({"error": "Department not found"}), 404
    if not TIME_RE.match(send_time):
        return jsonify({"error": "send_time must be 24-hour HH:MM, e.g. 08:30"}), 400
    try:
        number = normalize_number(data.get('recipient_number'))
    except ValueError as e:
        return jsonify({"error": str(e)}), 400

    sub = _find_subscription(department_id)
    if not sub:
        sub = ReportSubscription(department_id=department_id)
        db.session.add(sub)
    elif sub.recipient_number != number or sub.send_time != send_time:
        sub.last_sent_on = None  # new number/time — let it go out today if that time is still ahead

    sub.recipient_number = number
    sub.send_time = send_time
    sub.is_enabled = 1 if data.get('is_enabled', True) else 0

    try:
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        return jsonify({"error": str(e)}), 500
    return jsonify({"status": "success", "data": _serialize_subscription(sub)}), 200


@whatsapp_bp.route('/reports/preview', methods=['GET', 'OPTIONS'], strict_slashes=False)
@jwt_required
@permission_required('manage_reports')
def preview_report():
    if request.method == 'OPTIONS':
        return jsonify({}), 200
    try:
        return jsonify({"status": "success", "text": build_report(_dept_arg())}), 200
    except LookupError as e:
        return jsonify({"error": str(e)}), 404


@whatsapp_bp.route('/reports/send-now', methods=['POST', 'OPTIONS'], strict_slashes=False)
@jwt_required
@permission_required('manage_reports')
def send_report_now():
    """Sends a report immediately. Body: {department_id (null = whole
    factory), to_number (optional — defaults to that report's saved
    recipient)}. Doesn't touch the daily schedule."""
    if request.method == 'OPTIONS':
        return jsonify({}), 200

    data = request.get_json(silent=True) or {}
    department_id = data.get('department_id') or None
    to_number = data.get('to_number')
    if not to_number:
        sub = _find_subscription(department_id)
        to_number = sub.recipient_number if sub else None
    if not to_number:
        return jsonify({"error": "No recipient — enter a number or set one for this report first."}), 400

    try:
        text = send_report(department_id, to_number)
        return jsonify({"status": "success", "message": "Report sent.", "text": text}), 200
    except LookupError as e:
        return jsonify({"error": str(e)}), 404
    except ValueError as e:
        return jsonify({"error": str(e)}), 400
    except RuntimeError as e:
        return jsonify({"error": str(e)}), 502
