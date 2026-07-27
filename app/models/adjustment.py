from app import db
from app.core.utils import generate_uuid
from datetime import datetime

class InventoryAdjustment(db.Model):
    """Audit log for manual stock corrections, scrap, and damage"""
    __tablename__ = 'inventory_adjustments'
    __table_args__ = {'extend_existing': True}
    
    id = db.Column(db.String(36), primary_key=True, default=generate_uuid)
    
    item_id = db.Column(db.String(36), db.ForeignKey('internal_products.id'), nullable=False)
    department_id = db.Column(db.String(36), db.ForeignKey('departments.id'), nullable=False)
    
    # How much was added (+) or removed (-)
    adjustment_qty = db.Column(db.Float, nullable=False)
    reason = db.Column(db.String(255), nullable=False) # e.g., "Dropped and broken"
    
    # If a specific physical bin was damaged
    qr_code_string = db.Column(db.String(100), nullable=True) 
    
    reported_by = db.Column(db.String(100), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)