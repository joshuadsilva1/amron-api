from app import db
from app.core.utils import generate_uuid
from datetime import datetime




class ChallanItem(db.Model):
    """Line items for a specific challan"""
    __tablename__ = 'challan_items'
    
    id = db.Column(db.String(36), primary_key=True, default=generate_uuid)
    
    # Links back to the main Challan
    challan_id = db.Column(db.String(36), db.ForeignKey('internal_challans.id'), nullable=False)
    
    # Links to the Master Item Catalog
    item_id = db.Column(db.String(36), db.ForeignKey('internal_products.id'), nullable=False)
    
    # How much of this specific item is moving
    quantity = db.Column(db.Float, nullable=False)

class InternalChallan(db.Model):
    """The gate pass generated for any material movement"""
    __tablename__ = 'internal_challans'
    
    id = db.Column(db.String(36), primary_key=True, default=generate_uuid)
    challan_number = db.Column(db.String(100), unique=True, nullable=False)
    
    movement_type = db.Column(db.String(50)) 
    
    # UPDATED: Now strictly linked to the departments table
    from_department_id = db.Column(db.String(36), db.ForeignKey('departments.id'), nullable=False)
    to_department_id = db.Column(db.String(36), db.ForeignKey('departments.id'), nullable=False)
    
    po_id = db.Column(db.String(36), db.ForeignKey('purchase_orders.id'), nullable=True)
    supplier_id = db.Column(db.String(36), db.ForeignKey('suppliers.id'), nullable=True)
    
    status = db.Column(db.String(50), default='Pending_Verification')
    chalan_image_url = db.Column(db.String(255))
    
    created_by = db.Column(db.String(100)) 
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    # These relationships let you easily pull the department names later
    from_dept = db.relationship('Department', foreign_keys=[from_department_id])
    to_dept = db.relationship('Department', foreign_keys=[to_department_id])

class StockTransaction(db.Model):
    """The Immutable Ledger: Every stock IN or OUT goes here"""
    __tablename__ = 'stock_transactions'
    
    id = db.Column(db.String(36), primary_key=True, default=generate_uuid)
    product_id = db.Column(db.String(36), db.ForeignKey('internal_products.id'), nullable=False)
    
    # UPDATED: Strictly linked to the departments table
    department_id = db.Column(db.String(36), db.ForeignKey('departments.id'), nullable=False)
    
    transaction_type = db.Column(db.String(10), nullable=False) # 'IN' or 'OUT'
    quantity = db.Column(db.Float, nullable=False)
    
    challan_id = db.Column(db.String(36), db.ForeignKey('internal_challans.id'), nullable=True)
    qr_id = db.Column(db.String(36), db.ForeignKey('qr_code_registry.id'), nullable=True)
    
    is_manual = db.Column(db.Integer, default=0)
    reason = db.Column(db.String(255))
    reference_number = db.Column(db.String(100))
    image_url = db.Column(db.String(255), nullable=True)

    created_by = db.Column(db.String(100))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)