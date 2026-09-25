from flask import Blueprint, request, jsonify, g
from app import db

from app.models.department_po import DepartmentPO, DepartmentPOItem
from app.models.order import PurchaseOrder, PO_STATUS_PIPELINE
from app.models.item import InternalProduct, OEMCompanyCode
from app.models.recipe import BOMVersion
from app.models.department import Department
from app.core.decorators import jwt_required, permission_required
from app.core.notify import create_notification
from app.core.bom import MAX_BOM_DEPTH

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


def _po_label(po):
    """Human label for a customer PO in messages — the client + their
    challan number where there is one, never a bare uuid fragment."""
    from app.models.client import Client
    client = Client.query.get(po.client_id)
    who = client.name if client else "Unknown client"
    return f"{who} — {po.challan_number}" if po.challan_number else f"{who} (order {po.id[:6]})"


def _collect_demand(parent_id, parent_code, qty, depth, visited, demand, problems):
    """Walks a recipe and adds what each department owes to `demand`
    ({(department_id, component_id): qty}).

    Direct components of the finished good (depth 1) are always raised.
    Below that, only components that are themselves MADE here (have their
    own active recipe) are raised — e.g. FG -> "Cap, lasered" (Laser)
    -> "Cap, plain" (Moulding) -> powder: Laser and Moulding both get an
    internal PO, but powder (no recipe = bought raw material) doesn't —
    that shows up on MRP / the department's Stock vs PO screen and is
    bought via Supplier Orders instead."""
    if depth > MAX_BOM_DEPTH or parent_id in visited:
        problems.append(f"{parent_code}'s recipe loops back on itself")
        return
    bom_version = BOMVersion.query.filter_by(finished_good_id=parent_id, is_active=True).first()
    if not bom_version:
        return

    for row in bom_version.components:
        comp = InternalProduct.query.get(row.component_id)
        if not comp:
            continue
        has_recipe = BOMVersion.query.filter_by(finished_good_id=comp.id, is_active=True).first() is not None
        if depth > 1 and not has_recipe:
            continue
        # Same convention log_production uses to consume department
        # stock (raw quantity_required, no MRP-style unit
        # normalization) — quantity_fulfilled has to stay apples-to-
        # apples with what log_production actually credits.
        wastage_multiplier = 1 + ((row.wastage_percent or 0) / 100)
        comp_qty = row.quantity_required * qty * wastage_multiplier

        if not comp.department_id:
            problems.append(f"{comp.item_code} (in {parent_code}'s recipe) has no department")
        else:
            key = (comp.department_id, comp.id)
            demand[key] = demand.get(key, 0) + comp_qty

        if has_recipe:
            _collect_demand(comp.id, comp.item_code, comp_qty, depth + 1,
                            visited | {parent_id}, demand, problems)


def _raise_for_po(po, user_id):
    """Raises/tops up the internal DepartmentPOs for ONE customer PO (no
    commit — the caller commits once for the whole batch). Returns
    (result, department_po_ids) where result is
    {"po_id", "ok", "changed", "message"}.

    Walks each line item's recipe (see _collect_demand for exactly which
    components get raised), aggregates by (department, component) across
    the PO's line items and keeps one open DepartmentPO per department.
    Safe to run again: an existing open DepartmentPO is only topped up by
    whatever is NOT already outstanding on it, so re-sending the same PO
    adds nothing, and re-sending after a late-added line item adds just
    that line's demand.
    """
    label = _po_label(po)
    problems = []

    # {(department_id, component_id): quantity}
    demand = {}
    for li in po.items:
        remaining = (li.quantity or 0) - (li.produced_qty or 0)
        if remaining <= 0:
            continue
        mapping = OEMCompanyCode.query.get(li.mapping_id)
        if not mapping:
            problems.append("a line has no product attached")
            continue

        fg = InternalProduct.query.get(mapping.internal_product_id)
        fg_code = fg.item_code if fg else "a product"
        if not BOMVersion.query.filter_by(finished_good_id=mapping.internal_product_id, is_active=True).first():
            problems.append(f"{fg_code} has no recipe yet (Recipes → New recipe)")
            continue
        _collect_demand(mapping.internal_product_id, fg_code, remaining, 1, set(), demand, problems)

    if not demand:
        reason = "; ".join(dict.fromkeys(problems)) if problems else "nothing remains to produce"
        return {"po_id": po.id, "ok": False, "changed": False,
                "message": f"{label}: not sent — {reason}."}, []

    by_department = {}
    for (department_id, component_id), qty in demand.items():
        by_department.setdefault(department_id, []).append((component_id, qty))

    touched_ids = []
    sent_to = []
    changed = False
    for department_id, component_rows in by_department.items():
        dept = Department.query.get(department_id)
        if not dept:
            continue

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
                created_by=user_id,
            )
            db.session.add(dpo)
            db.session.flush()

        existing_items_by_component = {it.component_id: it for it in dpo.items}

        lines = []
        for component_id, qty in component_rows:
            comp = InternalProduct.query.get(component_id)
            existing_item = existing_items_by_component.get(component_id)
            if existing_item:
                outstanding = (existing_item.quantity_requested or 0) - (existing_item.quantity_fulfilled or 0)
                delta = qty - outstanding
                if delta <= 1e-9:
                    continue  # already asked for (or more) — nothing new
                existing_item.quantity_requested = (existing_item.quantity_requested or 0) + delta
                added = delta
            else:
                db.session.add(DepartmentPOItem(
                    department_po_id=dpo.id,
                    component_id=component_id,
                    quantity_requested=qty,
                ))
                added = qty
            lines.append(f"• {comp.name if comp else component_id}: {round(added, 2)} {comp.unit_of_measure if comp else ''}")

        touched_ids.append(dpo.id)
        if lines:
            changed = True
            create_notification(
                title=f"{'New' if is_new else 'Updated'} internal PO — {dept.name}",
                message=f"Needed for {label}:\n" + "\n".join(lines),
                department_id=department_id,
            )
            sent_to.append(f"{dept.name} ({len(lines)} part{'s' if len(lines) != 1 else ''})")

    # Move the source PO forward into Material Check, but never backward —
    # a PO already further along (e.g. In Production) shouldn't regress
    # just because this gets re-run for a late-added line item.
    try:
        current_idx = PO_STATUS_PIPELINE.index(po.status)
    except ValueError:
        current_idx = -1
    if current_idx < PO_STATUS_PIPELINE.index('Material Check'):
        po.status = 'Material Check'

    message = (f"{label}: sent to " + ", ".join(sent_to) + "." if changed
               else f"{label}: already sent earlier — nothing new to add.")
    if problems:
        message += " Skipped: " + "; ".join(dict.fromkeys(problems)) + "."
    return {"po_id": po.id, "ok": True, "changed": changed, "message": message}, touched_ids


@department_po_bp.route('/generate', methods=['POST', 'OPTIONS'], strict_slashes=False)
@jwt_required
@permission_required('create_po')
def generate_from_po():
    """
    The "we picked up the PO, here's what Moulding/Brasspart owe it" step,
    for one customer PO or many at once (see _raise_for_po for the rules).
    Body: {"po_id": "..."} or {"po_ids": ["...", "..."]}

    A PO that can't be raised (no recipe, nothing left to produce, ...)
    doesn't block the others in a batch — it's reported in `results` with
    the reason. If NOTHING could be raised the response is a 400 carrying
    those reasons.
    """
    if request.method == 'OPTIONS':
        return jsonify({}), 200

    data = request.get_json(silent=True) or {}
    po_ids = data.get('po_ids') or ([data['po_id']] if data.get('po_id') else [])
    po_ids = list(dict.fromkeys(po_ids))
    if not po_ids:
        return jsonify({"error": "po_id or po_ids is required"}), 400

    results = []
    department_po_ids = []
    for po_id in po_ids:
        po = PurchaseOrder.query.get(po_id)
        if not po or not po.is_active:
            results.append({"po_id": po_id, "ok": False, "changed": False,
                            "message": f"PO {str(po_id)[:8]}: not found."})
            continue
        result, touched = _raise_for_po(po, g.current_user.id)
        results.append(result)
        department_po_ids.extend(touched)

    ok_count = sum(1 for r in results if r["ok"])
    if ok_count == 0:
        db.session.rollback()
        return jsonify({"error": "\n".join(r["message"] for r in results), "results": results}), 400

    try:
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        return jsonify({"error": str(e)}), 500

    return jsonify({
        "status": "success",
        "message": "\n".join(r["message"] for r in results),
        "department_po_ids": list(dict.fromkeys(department_po_ids)),
        "results": results,
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
