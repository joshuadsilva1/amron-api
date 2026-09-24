from functools import wraps
from flask import request, jsonify, g
from sqlalchemy.exc import SQLAlchemyError
from app.models.user import User
from app.core.jwt import decode_token
from app import db

def jwt_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if request.method == 'OPTIONS':
            return jsonify({}), 200

        auth_header = request.headers.get("Authorization")

        if not auth_header:
            return jsonify({"message": "Authorization header missing"}), 401

        if not auth_header.startswith("Bearer "):
            return jsonify({"message": "Invalid Authorization header"}), 401

        token = auth_header.split(" ")[1]

        # ONLY wrap the token decoding and user fetching in the try-except.
        # A dropped DB connection (SQLAlchemyError) is NOT an auth failure —
        # the frontend force-logs-out on any 401 (see services/api.ts), so
        # mislabeling a transient DB blip as "invalid token" was wiping real
        # users' sessions for something pool_pre_ping (see app/__init__.py)
        # should now mostly prevent anyway. Only an actual bad/expired token
        # or missing user gets 401; a DB error gets 503 so the client can
        # retry instead of logging out.
        try:
            payload = decode_token(token)
        except Exception as e:
            print(f"Token error: {e}")
            return jsonify({"message": "Invalid or expired token"}), 401

        try:
            user = db.session.get(User, payload["user_id"])
        except SQLAlchemyError as e:
            db.session.rollback()
            print(f"DB error while resolving user from token: {e}")
            return jsonify({"message": "Service temporarily unavailable, please retry"}), 503

        if not user:
            return jsonify({"message": "User not found"}), 401

        g.current_user = user

        # EXECUTE THE ROUTE OUTSIDE THE TRY-EXCEPT!
        # Now, if the database crashes, it returns a 500 instead of a fake 401
        return f(*args, **kwargs)

    return decorated


def user_has_permission(user, permission_name):
    """True if `user`'s role carries `permission_name` or the '*' wildcard
    (ADMIN, per seed.py). Safe to call on a role-less/pending user."""
    if not user or not user.role_data:
        return False
    perm_names = {p.name for p in user.role_data.permissions}
    return '*' in perm_names or permission_name in perm_names


def permission_required(*permission_names):
    """Gate a route behind one of `permission_names` (any current user
    permission matching ANY of them passes). Must sit under @jwt_required
    so g.current_user is already set. The '*' wildcard (ADMIN) always
    passes, matching user_has_permission."""
    def wrapper(f):
        @wraps(f)
        def decorated(*args, **kwargs):
            if request.method == 'OPTIONS':
                return jsonify({}), 200

            user = getattr(g, 'current_user', None)
            if not any(user_has_permission(user, name) for name in permission_names):
                return jsonify({"message": "Permission denied"}), 403

            return f(*args, **kwargs)

        return decorated

    return wrapper