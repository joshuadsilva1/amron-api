from flask import Blueprint, request, jsonify, g
from app import db
from app.models.notification import Notification
from app.core.decorators import jwt_required

notification_bp = Blueprint('notifications', __name__)

@notification_bp.route('/', methods=['GET', 'OPTIONS'], strict_slashes=False)
@jwt_required
def get_notifications():
    """Fetches notifications, newest first. Users tied to a specific
    department only see that department's notifications plus factory-wide
    ones (department_id is null, e.g. low-stock alerts); users with no
    department (admins, managers) see everything, unfiltered."""
    if request.method == 'OPTIONS':
        return jsonify({}), 200

    query = Notification.query
    if g.current_user.department_id:
        query = query.filter(
            db.or_(
                Notification.department_id == g.current_user.department_id,
                Notification.department_id.is_(None),
            )
        )

    notes = query.order_by(Notification.created_at.desc()).limit(100).all()
    result = []

    for n in notes:
        result.append({
            "id": n.id,
            "title": n.title,
            "message": n.message,
            "is_read": bool(n.is_read),
            "created_at": n.created_at.isoformat()
        })

    return jsonify({"status": "success", "data": result}), 200

@notification_bp.route('/mark-read', methods=['POST', 'OPTIONS'], strict_slashes=False)
@jwt_required
def mark_all_read():
    """Marks all notifications as read"""
    if request.method == 'OPTIONS':
        return jsonify({}), 200

    try:
        Notification.query.update({Notification.is_read: 1})
        db.session.commit()
        return jsonify({"status": "success", "message": "All marked as read"}), 200
    except Exception as e:
        db.session.rollback()
        return jsonify({"error": str(e)}), 500
