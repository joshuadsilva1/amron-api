from app import db
from app.core.utils import generate_uuid
from datetime import datetime

# Fulfillment is never a manual rubber-stamp — it only advances because
# log_production actually applied produced quantity to an item (see
# transaction_api.py's log_production). There is deliberately no
# "Approved" status a person can just click.
DEPARTMENT_PO_STATUSES = ['Pending', 'In_Progress', 'Fulfilled']


class DepartmentPO(db.Model):
    """An internal request to a production department (Moulding, Brasspart,
    etc.) for the components a customer PO's finished goods need directly
    from that department — e.g. a customer PO for product X (built from Y,
    Z from Moulding and L from Brasspart) raises one DepartmentPO for
    Moulding (Y, Z) and one for Brasspart (L). Raised explicitly by a
    production manager reviewing the PO (see department_po_api.generate),
    not silently/automatically on PO creation.
    """
    __tablename__ = 'department_pos'

    id = db.Column(db.String(36), primary_key=True, default=generate_uuid)

    department_id = db.Column(db.String(36), db.ForeignKey('departments.id'), nullable=False)
    # The customer PO this traces back to — nullable because a department
    # can, in principle, be topped up ahead of demand, but the normal path
    # always sets this (see department_po_api.generate).
    source_po_id = db.Column(db.String(36), db.ForeignKey('purchase_orders.id'), nullable=True)

    status = db.Column(db.String(20), default='Pending')
    is_urgent = db.Column(db.Integer, default=0)
    notes = db.Column(db.Text, nullable=True)

    created_by = db.Column(db.String(36), db.ForeignKey('users.id'), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    fulfilled_at = db.Column(db.DateTime, nullable=True)

    items = db.relationship('DepartmentPOItem', backref='department_po', lazy=True, cascade='all, delete-orphan')


class DepartmentPOItem(db.Model):
    """One component + quantity a DepartmentPO is asking for.
    quantity_fulfilled only ever moves via log_production crediting real
    production against it — never set directly by a user action."""
    __tablename__ = 'department_po_items'

    id = db.Column(db.String(36), primary_key=True, default=generate_uuid)
    department_po_id = db.Column(db.String(36), db.ForeignKey('department_pos.id'), nullable=False)
    component_id = db.Column(db.String(36), db.ForeignKey('internal_products.id'), nullable=False)

    quantity_requested = db.Column(db.Float, nullable=False)
    quantity_fulfilled = db.Column(db.Float, default=0.0)
