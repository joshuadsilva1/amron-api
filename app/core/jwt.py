import os
import jwt

from datetime import datetime, timedelta


def generate_token(user):

    payload = {
        "user_id": user.id,
        "exp": datetime.utcnow() + timedelta(
            days=int(os.getenv("JWT_EXPIRY_DAYS", 7))
        )
    }

    return jwt.encode(
        payload,
        os.getenv("SECRET_KEY"),
        algorithm="HS256"
    )


def decode_token(token):

    return jwt.decode(
        token,
        os.getenv("SECRET_KEY"),
        algorithms=["HS256"]
    )