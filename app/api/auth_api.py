from flask import Blueprint, request, jsonify, g
from app import db
from app.models.user import User, AppModule
from app.core.firebase import verify_firebase_token
from app.core.jwt import generate_token
from app.core.decorators import jwt_required
from app.core.utils import normalize_phone_number

auth_bp = Blueprint("auth", __name__)


def _compute_allowed_modules(user):
    """The dynamic module list the sidebar filters against — every active
    AppModule whose required_permission the user's role carries (or the
    '*' wildcard). Shared by /login and /me so a permission/module change
    an admin makes shows up the next time either is called, not just on
    the next fresh login."""
    user_permissions = []
    if user.role_data:
        user_permissions = [p.name for p in user.role_data.permissions]

    allowed_modules = []
    for mod in AppModule.query.filter_by(is_active=True).all():
        if "*" in user_permissions or mod.required_permission.name in user_permissions:
            allowed_modules.append({
                "name": mod.name,
                "route": mod.route,
                "icon": mod.icon,
                "description": mod.description,
            })
    return allowed_modules


@auth_bp.route("/me", methods=["GET"])
@jwt_required
def me():
    user = g.current_user

    # Translate the integer ID into the string name for the frontend
    role_name = user.role_data.name if user.role_data else "PENDING"

    return jsonify({
        "user": {
            "id": user.id,
            "phone_number": user.phone_number,
            "full_name": user.full_name,
            "role": role_name, # Sending the STRING, not the integer
            "department_id": user.department_id,
            "is_active": user.is_active,
            "modules": _compute_allowed_modules(user),
        }
    }), 200


@auth_bp.route("/login", methods=["POST"])
def login():
    firebase_token = request.json.get("firebase_token") if request.is_json else None
    if not firebase_token:
        return jsonify({"message": "Firebase token missing"}), 400

    decoded = verify_firebase_token(firebase_token)
    if not decoded:
        return jsonify({"message": "Invalid Firebase token"}), 401

    phone = normalize_phone_number(decoded["phone_number"])
    user = User.query.filter_by(phone_number=phone).first()

    if not user:
        user = User(phone_number=phone)
        db.session.add(user)
        db.session.commit()

    token = generate_token(user)

    role_name = user.role_data.name if user.role_data else "USER"

    # Send the exact UI structure to the frontend
    return jsonify({
        "access_token": token,
        "user": {
            "id": user.id,
            "phone": user.phone_number,
            "name": user.full_name,
            "role": role_name,
            "department_id": user.department_id,
            "is_active": user.is_active,
            "modules": _compute_allowed_modules(user), # <--- Dynamically pulled from DB!
        }
    }), 200