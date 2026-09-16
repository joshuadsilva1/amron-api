from flask import Blueprint, request, jsonify, g
from app import db

from app.models.department_po import DepartmentPO, DepartmentPOItem
from app.models.order import PurchaseOrder, PO_STATUS_PIPELINE
from app.models.item import InternalProduct, OEMCompanyCode
from app.models.recipe import BOMVersion
from app.models.department import Department
from app.core.decorators import jwt_required
from app.core.notify import create_notification

department_po_bp = Blueprint('department_pos', __name__)


def _serialize(dpo):
    items = []
    for it in dpo.items:
        comp = InternalProduct.query.get(it.component_id)
        items.append({
            "id": it.id,
            "component_id": it.component_id,
            "component_code": comp.item_code if comp else None,
            "component_name": comp.name if comp else None,
            "unit_of_measure": comp.unit_of_measure if comp else None,
            "quantity_requested": it.quantity_requested,
            "quantity_fulfilled": it.quantity_fulfilled or 0,
        })
    dept = Department.query.get(dpo.department_id)
    return {
        "id": dpo.id,
        "department_id": dpo.department_id,
        "department_name": dept.name if dept else None,
        "source_po_id": dpo.source_po_id,
        "status": dpo.status,
        "is_urgent": bool(dpo.is_urgent),
        "notes": dpo.notes,
        "created_at": dpo.created_at.isoformat() if dpo.created_at else None,
        "fulfilled_at": dpo.fulfilled_at.isoformat() if dpo.fulfilled_at else None,
        "items": items,
    }


@department_po_bp.route('/generate', methods=['POST', 'OPTIONS'], strict_slashes=False)
@jwt_required
def generate_from_po():
    """
    The "we picked up the PO, here's what Moulding/Brasspart owe it" step.
    Explodes ONE LEVEL of each PO line item's finished-good recipe — not
    the full multi-level explosion an MRP raw-material check uses. A
    department only needs to know about ITS OWN direct components; if one
    of those components itself needs raw material (e.g. a moulded part
    needing powder), that's that department's own problem — visible on
    its own Stock vs PO screen and bought via Supplier Orders, not
    something this step should be raising a cross-department ticket for.

    Aggregates by (department, component) across every line item on the
    PO, creates one DepartmentPO per department owing something, and
    notifies each department. Re-running this for the same PO tops up
    quantities on top of what's already been raised (it does not create
    duplicate DepartmentPOs for a department that already has an open one
    from this PO) — safe to call again after a late-added line item.
    Body: {"po_id": "..."}
    """
    if request.method == 'OPTIONS':
        return jsonify({}), 200

    data = request.get_json(silent=True) or {}
    po_id = data.get('po_id')
    if not po_id:
        return jsonify({"error": "po_id is required"}), 400

    po = PurchaseOrder.query.get(po_id)
    if not po or not po.is_active:
        return jsonify({"error": "Purchase order not found"}), 404

    # {(department_id, component_id): quantity}
    demand = {}
    for li in po.items:
        remaining = (li.quantity or 0) - (li.produced_qty or 0)
        if remaining <= 0:
            continue
        mapping = OEMCompanyCode.query.get(li.mapping_id)
        if not mapping:
            continue

        bom_version = BOMVersion.query.filter_by(finished_good_id=mapping.internal_product_id, is_active=True).first()
        if not bom_version:
            continue

        for row in bom_version.components:
            comp = InternalProduct.query.get(row.component_id)
            if not comp or not comp.department_id:
                continue
            # Same convention log_production uses to consume department
            # stock (raw quantity_required, no MRP-style unit
            # normalization) — quantity_fulfilled has to stay apples-to-
            # apples with what log_production actually credits.
            wastage_multiplier = 1 + ((row.wastage_percent or 0) / 100)
            qty = row.quantity_required * remaining * wastage_multiplier
            key = (comp.department_id, comp.id)
            demand[key] = demand.get(key, 0) + qty

    if not demand:
        return jsonify({
            "error": "Nothing to raise — this PO's line items have no recipe, or nothing remains to produce."
        }), 400

    by_department = {}
    for (department_id, component_id), qty in demand.items():
        by_department.setdefault(department_id, []).append((component_id, qty))

    created = []
    for department_id, component_rows in by_department.items():
        dept = Department.query.get(department_id)
        if not dept:
            continue

        # Top up an existing open DepartmentPO for this exact PO +
        # department instead of spawning a duplicate.
        dpo = DepartmentPO.query.filter(
            DepartmentPO.source_po_id == po.id,
            DepartmentPO.department_id == department_id,
            DepartmentPO.status != 'Fulfilled',
        ).first()

        is_new = dpo is None
        if is_new:
            dpo = DepartmentPO(
                department_id=department_id,
                source_po_id=po.id,
                is_urgent=po.is_urgent,
                created_by=g.current_user.id,
            )
            db.session.add(dpo)
            db.session.flush()

        existing_items_by_component = {it.component_id: it for it in dpo.items}

        lines = []
        for component_id, qty in component_rows:
            comp = InternalProduct.query.get(component_id)
            existing_item = existing_items_by_component.get(component_id)
            if existing_item:
                existing_item.quantity_requested = (existing_item.quantity_requested or 0) + qty
            else:
                db.session.add(DepartmentPOItem(
                    department_po_id=dpo.id,
                    component_id=component_id,
                    quantity_requested=qty,
                ))
            lines.append(f"• {comp.name if comp else component_id}: {round(qty, 2)} {comp.unit_of_measure if comp else ''}")

        create_notification(
            title=f"{'New' if is_new else 'Updated'} internal PO — {dept.name}",
            message=f"Needed for customer PO {po.id[:8]}:\n" + "\n".join(lines),
            department_id=department_id,
        )
        created.append(dpo.id)

    # Move the source PO forward into Material Check, but never backward —
    # a PO already further along (e.g. In Production) shouldn't regress
    # just because this gets re-run for a late-added line item.
    try:
        current_idx = PO_STATUS_PIPELINE.index(po.status)
    except ValueError:
        current_idx = -1
    target_idx = PO_STATUS_PIPELINE.index('Material Check')
    if current_idx < target_idx:
        po.status = 'Material Check'

    try:
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        return jsonify({"error": str(e)}), 500

    return jsonify({
        "status": "success",
        "message": f"Raised/updated {len(created)} internal PO(s).",
        "department_po_ids": created,
    }), 201


@department_po_bp.route('', methods=['GET'], strict_slashes=False)
@jwt_required
def list_department_pos():
    """Lists internal department POs — filter by ?department_id= (what a
    floor screen wants) and/or ?status=."""
    department_id = request.args.get('department_id')
    status = request.args.get('status')

    query = DepartmentPO.query
    if department_id:
        query = query.filter_by(department_id=department_id)
    if status:
        query = query.filter_by(status=status)

    rows = query.order_by(DepartmentPO.is_urgent.desc(), DepartmentPO.created_at.asc()).all()
    return jsonify({"status": "success", "data": [_serialize(d) for d in rows]}), 200


@department_po_bp.route('/<dpo_id>', methods=['GET'], strict_slashes=False)
@jwt_required
def get_department_po(dpo_id):
    dpo = DepartmentPO.query.get(dpo_id)
    if not dpo:
        return jsonify({"error": "Not found"}), 404
    return jsonify({"status": "success", "data": _serialize(dpo)}), 200
