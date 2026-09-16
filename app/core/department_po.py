"""Fulfillment tracking for internal DepartmentPOs — the only way one ever
moves off 'Pending' is a department actually producing (stocking out)
against it via log_production. There is deliberately no manual "approve"
action; see app/models/department_po.py.
"""
from datetime import datetime
from app.models.department_po import DepartmentPO, DepartmentPOItem


def apply_production_to_department_pos(department_id, component_id, quantity_produced):
    """Credits `quantity_produced` of `component_id` toward any open
    DepartmentPOItems for `department_id` — most urgent/oldest first,
    spilling into the next one if this batch covers more than one PO
    needed. Returns the list of DepartmentPO ids touched (for the caller
    to report back, e.g. in log_production's response)."""
    remaining = quantity_produced
    if remaining <= 0:
        return []

    open_items = DepartmentPOItem.query.join(DepartmentPO).filter(
        DepartmentPOItem.component_id == component_id,
        DepartmentPO.department_id == department_id,
        DepartmentPO.status != 'Fulfilled',
    ).order_by(DepartmentPO.is_urgent.desc(), DepartmentPO.created_at.asc()).all()

    touched_po_ids = set()
    for item in open_items:
        if remaining <= 0:
            break
        outstanding = (item.quantity_requested or 0) - (item.quantity_fulfilled or 0)
        if outstanding <= 0:
            continue
        applied = min(outstanding, remaining)
        item.quantity_fulfilled = (item.quantity_fulfilled or 0) + applied
        remaining -= applied
        touched_po_ids.add(item.department_po_id)

    for dpo_id in touched_po_ids:
        dpo = DepartmentPO.query.get(dpo_id)
        if not dpo:
            continue
        all_done = all((i.quantity_fulfilled or 0) >= (i.quantity_requested or 0) for i in dpo.items)
        any_done = any((i.quantity_fulfilled or 0) > 0 for i in dpo.items)
        if all_done:
            dpo.status = 'Fulfilled'
            dpo.fulfilled_at = datetime.utcnow()
        elif any_done:
            dpo.status = 'In_Progress'

    return list(touched_po_ids)
