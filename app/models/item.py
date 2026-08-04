from app import db
from app.core.utils import generate_uuid
from datetime import datetime

class InternalProduct(db.Model):
    __tablename__ = 'internal_products'
    
    id = db.Column(db.String(36), primary_key=True, default=generate_uuid)
    item_code = db.Column(db.String(50), unique=True, nullable=True) 
    oem_company_code = db.Column(db.String(100), nullable=True)
    name = db.Column(db.String(150), nullable=False)
    
    # --- NORMALIZED DEPARTMENT LINK ---
    department_id = db.Column(db.String(36), db.ForeignKey('departments.id'), nullable=True)
    department = db.relationship('Department', backref='items')
    
    category = db.Column(db.String(50), nullable=False) 
    subcategory = db.Column(db.String(100), nullable=True)
    
    unit_of_measure = db.Column(db.String(20), nullable=False, default='pcs')
    pcs_per_scan = db.Column(db.Integer, default=1)

    price = db.Column(db.Float, default=0.0)
    box_qty = db.Column(db.Integer, default=0)
    carton_qty = db.Column(db.Integer, default=0)

    current_stock = db.Column(db.Float, default=0.0)
    reorder_level = db.Column(db.Float, default=0.0)
    
    is_active = db.Column(db.Integer, default=1)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

# --- NEW INVENTORY BRIDGE TABLE ---
class DepartmentStock(db.Model):
    """Tracks exactly how much of an item is currently sitting in a specific department"""
    __tablename__ = 'department_stock'
    
    id = db.Column(db.String(36), primary_key=True, default=generate_uuid)
    
    item_id = db.Column(db.String(36), db.ForeignKey('internal_products.id'), nullable=False)
    department_id = db.Column(db.String(36), db.ForeignKey('departments.id'), nullable=False)
    
    # The actual amount currently in this specific room
    quantity = db.Column(db.Float, default=0.0)
    
    # Auto-updates whenever stock changes
    last_updated = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Safety net: Only one record allowed per item-department combo
    __table_args__ = (
        db.UniqueConstraint('item_id', 'department_id', name='uq_item_department_stock'),
    )

class BoxMapping(db.Model):
    """How many pieces of a given finished-good product fit into one unit
    of a given box. Many-to-many: the same box can hold different
    quantities of different products (e.g. 10 pcs of Rockers, 20 pcs of
    Plain switches, both in the same box type) — mirrors ProductBOM's
    shape, just for packaging instead of manufacturing."""
    __tablename__ = 'box_mappings'

    id = db.Column(db.String(36), primary_key=True, default=generate_uuid)
    box_item_id = db.Column(db.String(36), db.ForeignKey('internal_products.id'), nullable=False)
    product_id = db.Column(db.String(36), db.ForeignKey('internal_products.id'), nullable=False)
    pcs_per_box = db.Column(db.Integer, nullable=False)

    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    __table_args__ = (
        db.UniqueConstraint('box_item_id', 'product_id', name='uq_box_mapping_box_product'),
    )

class OEMCompanyCode(db.Model):
    __tablename__ = 'oem_company_codes'
    
    id = db.Column(db.String(36), primary_key=True, default=generate_uuid)
    client_id = db.Column(db.String(36), db.ForeignKey('clients.id'), nullable=False)
    internal_product_id = db.Column(db.String(36), db.ForeignKey('internal_products.id'), nullable=False)
    
    # Core OEM Details
    client_product_code = db.Column(db.String(100), nullable=False) # e.g., 'HA101'
    client_product_name = db.Column(db.String(255), nullable=True)
    
    # --- REPLACED packaging_instructions WITH STRUCTURED FIELDS ---
    box_type = db.Column(db.String(100), nullable=True)
    pieces_per_box = db.Column(db.Integer, nullable=True)
    
    pouch_type = db.Column(db.String(100), nullable=True)
    pieces_per_pouch = db.Column(db.Integer, nullable=True)
    
    carton_type = db.Column(db.String(100), nullable=True)
    pieces_per_carton = db.Column(db.Integer, nullable=True)
    
    label_type = db.Column(db.String(100), nullable=True)
    
    created_at = db.Column(db.DateTime, default=datetime.utcnow)