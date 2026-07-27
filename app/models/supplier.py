from app import db
from app.core.utils import generate_uuid
from datetime import datetime

class Supplier(db.Model):
    """Master registry for vendors who supply raw materials"""
    __tablename__ = 'suppliers'
    __table_args__ = {'extend_existing': True}
    
    id = db.Column(db.String(36), primary_key=True, default=generate_uuid)
    name = db.Column(db.String(100), unique=True, nullable=False)
    
    contact_email = db.Column(db.String(100), nullable=True)
    phone = db.Column(db.String(20), nullable=True)
    address = db.Column(db.Text, nullable=True)
    
    is_active = db.Column(db.Integer, default=1)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)