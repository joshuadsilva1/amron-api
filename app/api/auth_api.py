from flask import Blueprint, request, jsonify

from app import db

from app.models.user import User

from app.core.firebase import verify_firebase_token
from app.core.jwt import generate_token

auth_bp = Blueprint("auth", __name__)


from flask import g

from app.core.decorators import jwt_required


@auth_bp.route("/me", methods=["GET"])
@jwt_required
def me():

    user = g.current_user

    return jsonify({
    "user": {
        "id": user.id,
        "phone_number": user.phone_number,
        "full_name": user.full_name,
        "role": user.role,
        "department_id": user.department_id,
        "is_active": user.is_active,
    }
}), 200


@auth_bp.route("/login", methods=["POST"])
def login():

    print("Headers:", request.headers)
    print("JSON:", request.get_json(silent=True))
    print("Raw:", request.data)

    firebase_token = request.json.get("firebase_token") if request.is_json else None

    if not firebase_token:
        return jsonify({"message": "Firebase token missing"}), 400

    decoded = verify_firebase_token(firebase_token)

    if not decoded:
        return jsonify({"message": "Invalid Firebase token"}), 401

    phone = decoded["phone_number"]

    user = User.query.filter_by(
        phone_number=phone
    ).first()

    if not user:

        user = User(
            phone_number=phone
        )

        db.session.add(user)
        db.session.commit()

    token = generate_token(user)

    return jsonify({
    "access_token": token,
    "user": {
        "id": user.id,
        "phone": user.phone_number,
        "name": user.full_name,
        "role": user.role,
        "department_id": user.department_id,
        "is_active": user.is_active,
    }
}), 200