from app import db
from app.core.utils import generate_uuid
from datetime import datetime

class Client(db.Model):
    """Master registry for all B2B customers receiving your finished goods"""
    __tablename__ = 'clients'
    __table_args__ = {'extend_existing': True}
    
    id = db.Column(db.String(36), primary_key=True, default=generate_uuid)
    name = db.Column(db.String(100), unique=True, nullable=False)
    
    # Optional contact details
    contact_email = db.Column(db.String(100), nullable=True)
    phone = db.Column(db.String(20), nullable=True)
    shipping_address = db.Column(db.Text, nullable=True)
    
    is_active = db.Column(db.Integer, default=1)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)