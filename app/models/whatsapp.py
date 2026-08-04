from app import db
from app.core.utils import generate_uuid
from datetime import datetime

class WhatsAppConfig(db.Model):
    """Single-row settings for the business's WhatsApp sending account
    (Gupshup today; `provider` exists so this doesn't need a schema change
    if that ever switches)."""
    __tablename__ = 'whatsapp_config'

    id = db.Column(db.String(36), primary_key=True, default=generate_uuid)
    provider = db.Column(db.String(50), default='gupshup')

    api_key = db.Column(db.String(255), nullable=True)
    app_name = db.Column(db.String(100), nullable=True)
    sender_number = db.Column(db.String(20), nullable=True)

    is_active = db.Column(db.Integer, default=0)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
