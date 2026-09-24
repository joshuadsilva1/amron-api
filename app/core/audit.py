"""Immutable audit trail helper — see models/audit_log.py.

Usage: call `log_audit(...)` right before the caller's own db.session.commit()
so the audit row lands in the SAME transaction as the change it records
(atomic — either both happen or neither does). This function only calls
db.session.add(); it deliberately never commits on its own.
"""
from flask import g, request
from app import db
from app.models.audit_log import AuditLog


def log_audit(action, resource_type, resource_id=None, payload_before=None, payload_after=None):
    user = getattr(g, 'current_user', None)
    db.session.add(AuditLog(
        user_id=user.id if user else None,
        user_label=(user.full_name or user.phone_number) if user else 'System',
        action=action,
        resource_type=resource_type,
        resource_id=str(resource_id) if resource_id is not None else None,
        payload_before=payload_before,
        payload_after=payload_after,
        ip_address=request.remote_addr if request else None,
    ))
