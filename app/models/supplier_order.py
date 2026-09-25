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
    materials = db.relationship('SupplierOrderMaterial', backref='supplier_order', lazy=True)

class SupplierOrderItem(db.Model):
    __tablename__ = 'supplier_order_items'
    
    id = db.Column(db.String(36), primary_key=True, default=generate_uuid)
    supplier_order_id = db.Column(db.String(36), db.ForeignKey('supplier_orders.id'), nullable=False)
    
    # Raw materials link directly to internal products
    product_id = db.Column(db.String(36), db.ForeignKey('internal_products.id'), nullable=False)
    
    # Float: raw materials are often ordered by weight (e.g. 3.6 kg powder).
    ordered_qty = db.Column(db.Float, nullable=False)
    received_qty = db.Column(db.Float, default=0)


class SupplierOrderMaterial(db.Model):
    """Job work: material WE send to the supplier so they can make the
    ordered part — e.g. ordering 300 moulded caps from an outside moulder
    means sending them 300 x (powder per cap from the cap's recipe).
    Worked out from the ordered item's active recipe when the order is
    placed (see supplier_api.materials_to_send), so the quantity stays as
    it was even if the recipe changes later."""
    __tablename__ = 'supplier_order_materials'

    id = db.Column(db.String(36), primary_key=True, default=generate_uuid)
    supplier_order_id = db.Column(db.String(36), db.ForeignKey('supplier_orders.id'), nullable=False)
    product_id = db.Column(db.String(36), db.ForeignKey('internal_products.id'), nullable=False)
    # Which ordered item this material is for.
    for_product_id = db.Column(db.String(36), db.ForeignKey('internal_products.id'), nullable=True)
    quantity = db.Column(db.Float, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)