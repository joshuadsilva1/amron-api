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


class SupplierItem(db.Model):
    """Which supplier(s) a raw material/component can be sourced from —
    used by MRP to group shortage suggestions by supplier. An item can
    have more than one linked supplier."""
    __tablename__ = 'supplier_items'

    id = db.Column(db.String(36), primary_key=True, default=generate_uuid)
    supplier_id = db.Column(db.String(36), db.ForeignKey('suppliers.id'), nullable=False)
    item_id = db.Column(db.String(36), db.ForeignKey('internal_products.id'), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    __table_args__ = (
        db.UniqueConstraint('supplier_id', 'item_id', name='uq_supplier_item'),
    )