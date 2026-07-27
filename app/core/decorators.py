from functools import wraps

from flask import request, jsonify, g

from app.models.user import User
from app.core.jwt import decode_token


def jwt_required(f):

    @wraps(f)
    def decorated(*args, **kwargs):

        auth_header = request.headers.get("Authorization")

        if not auth_header:
            return jsonify({"message": "Authorization header missing"}), 401

        if not auth_header.startswith("Bearer "):
            return jsonify({"message": "Invalid Authorization header"}), 401

        token = auth_header.split(" ")[1]

        try:

            payload = decode_token(token)

            from app import db

            user = db.session.get(User, payload["user_id"])

            if not user:
                return jsonify({"message": "User not found"}), 401

            g.current_user = user

            return f(*args, **kwargs)

        except Exception as e:
            print(e)
            return jsonify({"message": "Invalid or expired token"}), 401

    return decorated

from functools import wraps
from flask import jsonify, g


def roles_required(*roles):

    def wrapper(f):

        @wraps(f)
        def decorated(*args, **kwargs):

            if g.current_user.role not in roles:

                return jsonify({
                    "message": "Permission denied"
                }), 403

            return f(*args, **kwargs)

        return decorated

    return wrapper