from app import db
from app.core.utils import generate_uuid
from datetime import datetime

class DispatchChallan(db.Model):
    """Outbound challans for sending finished goods to clients"""
    __tablename__ = 'dispatch_challans'
    
    id = db.Column(db.String(36), primary_key=True, default=generate_uuid)
    challan_number = db.Column(db.String(100), unique=True, nullable=False)
    
    # Relationships (Optional in the UI)
    client_id = db.Column(db.String(36), db.ForeignKey('clients.id'), nullable=True)
    
    # If you have a specific PurchaseOrder table, you can add a ForeignKey here. 
    # Otherwise, leaving it as a String(36) works for loose coupling.
    purchase_order_id = db.Column(db.String(36), nullable=True) 
    
    status = db.Column(db.String(50), default='Pending') # 'Pending', 'Dispatched', 'Cancelled'
    notes = db.Column(db.Text, nullable=True)
    
    created_by = db.Column(db.String(100), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Easy access to all items in this challan
    items = db.relationship('DispatchChallanItem', backref='dispatch_challan', lazy=True, cascade="all, delete-orphan")


class DispatchChallanItem(db.Model):
    """The individual items inside an outbound Dispatch Challan"""
    __tablename__ = 'dispatch_challan_items'
    
    id = db.Column(db.String(36), primary_key=True, default=generate_uuid)
    dispatch_challan_id = db.Column(db.String(36), db.ForeignKey('dispatch_challans.id'), nullable=False)
    item_id = db.Column(db.String(36), db.ForeignKey('internal_products.id'), nullable=False)
    
    quantity = db.Column(db.Float, nullable=False)