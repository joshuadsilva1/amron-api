from app import db
from app.core.utils import generate_uuid
from datetime import datetime


class QRCodeRegistry(db.Model):
    """The digital twin for a physical bin/box on the factory floor"""
    __tablename__ = 'qr_code_registry'
    __table_args__ = {'extend_existing': True}
    
    id = db.Column(db.String(36), primary_key=True, default=generate_uuid)
    qr_code_string = db.Column(db.String(100), unique=True, nullable=False) 
    item_id = db.Column(db.String(36), db.ForeignKey('internal_products.id'), nullable=False)
    department_id = db.Column(db.String(36), db.ForeignKey('departments.id'), nullable=False)
    quantity = db.Column(db.Float, nullable=False)
    is_active = db.Column(db.Integer, default=1) 
    
    # ADD THIS LINE:
    qc_status = db.Column(db.String(20), default='Pending') # Pending, Passed, or Rejected
    
    created_at = db.Column(db.DateTime, default=datetime.utcnow)