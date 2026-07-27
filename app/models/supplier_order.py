from app import db
from app.core.utils import generate_uuid
from datetime import datetime

class SupplierOrder(db.Model):
    """Outgoing orders to your suppliers for raw materials"""
    __tablename__ = 'supplier_orders'
    
    id = db.Column(db.String(36), primary_key=True, default=generate_uuid)
    supplier_id = db.Column(db.String(36), db.ForeignKey('suppliers.id'), nullable=False)
    department_id = db.Column(db.String(36)) 
    
    status = db.Column(db.String(50), default='Pending') 
    notes = db.Column(db.Text)
    is_urgent = db.Column(db.Integer, default=0)
    
    # New: Photographic proof of the supplier's bill
    bill_image_url = db.Column(db.String(255))
    
    order_date = db.Column(db.DateTime, default=datetime.utcnow)
    required_date = db.Column(db.DateTime)
    is_active = db.Column(db.Integer, default=1)
    
    items = db.relationship('SupplierOrderItem', backref='supplier_order', lazy=True)

class SupplierOrderItem(db.Model):
    __tablename__ = 'supplier_order_items'
    
    id = db.Column(db.String(36), primary_key=True, default=generate_uuid)
    supplier_order_id = db.Column(db.String(36), db.ForeignKey('supplier_orders.id'), nullable=False)
    
    # Raw materials link directly to internal products
    product_id = db.Column(db.String(36), db.ForeignKey('internal_products.id'), nullable=False)
    
    ordered_qty = db.Column(db.Integer, nullable=False)
    received_qty = db.Column(db.Integer, default=0)