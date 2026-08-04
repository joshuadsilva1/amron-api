# from functools import wraps
# from flask import request, jsonify, g
# from app.models.user import User
# from app.core.jwt import decode_token
# from app import db

# def jwt_required(f):
#     @wraps(f)
#     def decorated(*args, **kwargs):
#         # 1. CATCH CORS PREFLIGHT REQUESTS IMMEDIATELY
#         # Let OPTIONS requests pass with a 200 OK without checking for a token
#         if request.method == 'OPTIONS':
#             return jsonify({}), 200

#         auth_header = request.headers.get("Authorization")

#         if not auth_header:
#             return jsonify({"message": "Authorization header missing"}), 401

#         if not auth_header.startswith("Bearer "):
#             return jsonify({"message": "Invalid Authorization header"}), 401

#         token = auth_header.split(" ")[1]

#         try:
#             payload = decode_token(token)

#             user = db.session.get(User, payload["user_id"])

#             if not user:
#                 return jsonify({"message": "User not found"}), 401

#             g.current_user = user

#             return f(*args, **kwargs)

#         except Exception as e:
#             print(e)
#             return jsonify({"message": "Invalid or expired token"}), 401

#     return decorated


# def roles_required(*roles):
#     def wrapper(f):
#         @wraps(f)
#         def decorated(*args, **kwargs):
#             # Also safely bypass role checks if an OPTIONS request somehow trickles down
#             if request.method == 'OPTIONS':
#                 return jsonify({}), 200

#             if g.current_user.role not in roles:
#                 return jsonify({
#                     "message": "Permission denied"
#                 }), 403

#             return f(*args, **kwargs)

#         return decorated

#     return wrapper


from functools import wraps
from flask import request, jsonify, g
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

        # ONLY wrap the token decoding and user fetching in the try-except
        try:
            payload = decode_token(token)
            user = db.session.get(User, payload["user_id"])

            if not user:
                return jsonify({"message": "User not found"}), 401

            g.current_user = user
            
        except Exception as e:
            print(f"Token error: {e}")
            return jsonify({"message": "Invalid or expired token"}), 401

        # EXECUTE THE ROUTE OUTSIDE THE TRY-EXCEPT!
        # Now, if the database crashes, it returns a 500 instead of a fake 401
        return f(*args, **kwargs)

    return decorated