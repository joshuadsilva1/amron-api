import firebase_admin

from firebase_admin import credentials
from firebase_admin import auth


if not firebase_admin._apps:
    import os
    import json

    # On Render there's no gitignored serviceAccount.json on disk, so the
    # credential is passed as a raw JSON string via env var instead. Local
    # dev keeps using the file for convenience.
    service_account_json = os.getenv("FIREBASE_SERVICE_ACCOUNT_JSON")
    if service_account_json:
        cred = credentials.Certificate(json.loads(service_account_json))
    else:
        BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../"))
        cred = credentials.Certificate(
            os.path.join(BASE_DIR, "serviceAccount.json")
        )
    firebase_admin.initialize_app(cred)


def verify_firebase_token(id_token: str):

    try:
        decoded_token = auth.verify_id_token(id_token)
        return decoded_token

    except Exception as e:
        print(f"Firebase verification failed: {e}")
        return None