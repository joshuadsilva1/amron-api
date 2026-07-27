from app import db
from app.core.utils import generate_uuid
from datetime import datetime

class PurchaseOrder(db.Model):
    """Incoming Customer POs"""
    __tablename__ = 'purchase_orders'
    
    id = db.Column(db.String(36), primary_key=True, default=generate_uuid)
    client_id = db.Column(db.String(36), db.ForeignKey('clients.id'), nullable=False)
    
    status = db.Column(db.String(50), default='Pending') # Pending, Clubbed, In_Production, Dispatched
    notes = db.Column(db.Text)
    challan_number = db.Column(db.String(100))
    
    is_urgent = db.Column(db.Integer, default=0)
    order_date = db.Column(db.DateTime, default=datetime.utcnow)
    required_date = db.Column(db.DateTime)
    
    edit_counter = db.Column(db.Integer, default=0)
    is_active = db.Column(db.Integer, default=1)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    # Relationship to line items
    items = db.relationship('POLineItem', backref='purchase_order', lazy=True)

class POLineItem(db.Model):
    """Items inside the PO. Links to the OEM Mapping, NOT the internal product directly."""
    __tablename__ = 'po_line_items'
    
    id = db.Column(db.String(36), primary_key=True, default=generate_uuid)
    order_id = db.Column(db.String(36), db.ForeignKey('purchase_orders.id'), nullable=False)
    
    # This is the crucial link to the OEMCompanyCode table
    mapping_id = db.Column(db.String(36), db.ForeignKey('oem_company_codes.id'), nullable=False)
    
    quantity = db.Column(db.Integer, nullable=False)
    dispatched_qty = db.Column(db.Integer, default=0)