import os
import requests

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_SERVICE_ROLE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY")
SUPABASE_STORAGE_BUCKET = os.getenv("SUPABASE_STORAGE_BUCKET", "uploads")


def upload_file(file_storage, subfolder, filename):
    """Uploads a werkzeug FileStorage to Supabase Storage and returns its
    public URL. Used in place of local-disk saves under uploads/<subfolder>/
    because Render's filesystem is ephemeral — anything written to disk is
    lost on every redeploy/restart.
    """
    path = f"{subfolder}/{filename}"
    url = f"{SUPABASE_URL}/storage/v1/object/{SUPABASE_STORAGE_BUCKET}/{path}"
    headers = {
        "Authorization": f"Bearer {SUPABASE_SERVICE_ROLE_KEY}",
        "apikey": SUPABASE_SERVICE_ROLE_KEY,
        "Content-Type": file_storage.mimetype or "application/octet-stream",
        "x-upsert": "true",
    }
    resp = requests.post(url, headers=headers, data=file_storage.read())
    resp.raise_for_status()
    return f"{SUPABASE_URL}/storage/v1/object/public/{SUPABASE_STORAGE_BUCKET}/{path}"
