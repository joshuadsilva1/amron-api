from app import db
from app.core.utils import generate_uuid
from datetime import datetime


class AuditLog(db.Model):
    """Immutable trail of sensitive, non-inventory actions (role/permission
    changes, settings edits, credential updates, ...). Inventory movements
    already have their own immutable ledger — see StockTransaction /
    InternalChallan in models/transaction.py — this is the general-purpose
    complement the spec calls for elsewhere (RBAC, config, assembly
    reconciliation). Never updated or deleted once written — only inserted
    and read (see admin_api.list_audit_logs)."""
    __tablename__ = 'audit_logs'

    id = db.Column(db.String(36), primary_key=True, default=generate_uuid)

    user_id = db.Column(db.String(36), db.ForeignKey('users.id'), nullable=True)
    # Denormalized so the log stays readable even if the user is later
    # deleted or renamed — audit trails should never go blank.
    user_label = db.Column(db.String(150), nullable=True)

    action = db.Column(db.String(100), nullable=False)          # e.g. 'role.permissions.update'
    resource_type = db.Column(db.String(100), nullable=False)   # e.g. 'role'
    resource_id = db.Column(db.String(100), nullable=True)

    payload_before = db.Column(db.JSON, nullable=True)
    payload_after = db.Column(db.JSON, nullable=True)

    ip_address = db.Column(db.String(64), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    user = db.relationship('User', foreign_keys=[user_id])
