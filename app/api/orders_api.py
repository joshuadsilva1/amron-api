from flask import Blueprint, request, jsonify
from app import db
from app.models.order import PurchaseOrder, POLineItem, PO_STATUS_PIPELINE
from app.models.item import InternalProduct, OEMCompanyCode
from app.models.client import Client
from sqlalchemy import func
from datetime import datetime
from app.core.decorators import jwt_required


orders_bp = Blueprint('orders', __name__)

@orders_bp.route('', methods=['GET'], strict_slashes=False)
@jwt_required
def list_orders():
    """Lists individual PO line items, client-wise. The OEM code -> internal
    code mapping is already resolved at creation time (see create_po), so
    every row here always has a full internal_code/product_name — there is
    no "unmapped" state to convert on this end."""
    status_filter = request.args.get('status')

    query = db.session.query(
        PurchaseOrder, POLineItem, OEMCompanyCode, InternalProduct, Client
    ).join(
        POLineItem, POLineItem.order_id == PurchaseOrder.id
    ).join(
        OEMCompanyCode, POLineItem.mapping_id == OEMCompanyCode.id
    ).join(
        InternalProduct, OEMCompanyCode.internal_product_id == InternalProduct.id
    ).join(
        Client, PurchaseOrder.client_id == Client.id
    ).filter(
        PurchaseOrder.is_active == 1
    )

    if status_filter:
        query = query.filter(PurchaseOrder.status == status_filter)

    rows = query.order_by(PurchaseOrder.order_date.desc()).all()

    result = []
    for po, line_item, mapping, product, client in rows:
        result.append({
            "po_id": po.id,
            "line_item_id": line_item.id,
            "client_id": client.id,
            "client_name": client.name,
            "product_id": product.id,
            "chalan_no": po.challan_number,
            "order_date": po.order_date.isoformat() if po.order_date else None,
            "due_date": po.required_date.isoformat() if po.required_date else None,
            "is_urgent": bool(po.is_urgent),
            "status": po.status,
            "notes": po.notes,
            "oem_code": mapping.client_product_code,
            "oem_name": mapping.client_product_name,
            "internal_code": product.item_code,
            "internal_product_name": product.name,
            "category": product.category,
            "quantity": line_item.quantity,
            "produced_qty": line_item.produced_qty or 0,
            "dispatched_qty": line_item.dispatched_qty,
        })

    return jsonify({"status": "success", "orders": result}), 200

@orders_bp.route('', methods=['POST'], strict_slashes=False)
@jwt_required
def create_po():
    """
    Endpoint for Production Manager to enter a Client PO.
    Each line item can be given EITHER:
      - "mapping_id" directly (if the frontend already resolved it), OR
      - "client_product_code" (the client's own OEM code) + the PO's client_id,
        in which case we resolve it to the mapping ourselves.
    Body: {
      "client_id": "...",
      "due_date": "2026-08-15",      # ISO date, optional
      "challan_number": "...",        # optional
      "is_urgent": true/false,
      "notes": "...",
      "items": [
        {"client_product_code": "HA101", "quantity": 500},
        {"mapping_id": "...", "quantity": 200}
      ]
    }
    """
    data = request.get_json()

    client_id = data.get('client_id')
    if not client_id:
        return jsonify({"error": "client_id is required"}), 400

    items = data.get('items', [])
    if not items:
        return jsonify({"error": "At least one item is required"}), 400

    # Parse the due date up front so a bad date fails before we touch the DB.
    required_date = None
    due_date_raw = data.get('due_date') or data.get('required_date')
    if due_date_raw:
        try:
            required_date = datetime.fromisoformat(due_date_raw)
        except ValueError:
            return jsonify({"error": f"due_date '{due_date_raw}' is not a valid date. Use YYYY-MM-DD."}), 400

    new_po = PurchaseOrder(
        client_id=client_id,
        notes=data.get('notes'),
        challan_number=data.get('challan_number'),
        is_urgent=1 if data.get('is_urgent') else 0,
        required_date=required_date,
    )
    db.session.add(new_po)
    db.session.flush()

    for item in items:
        mapping_id = item.get('mapping_id')
        client_product_code = item.get('client_product_code')

        if not mapping_id and client_product_code:
            mapping = OEMCompanyCode.query.filter_by(
                client_id=client_id, client_product_code=client_product_code
            ).first()
            if not mapping:
                db.session.rollback()
                return jsonify({
                    "error": f"No OEM code mapping found for '{client_product_code}' for this client. "
                             f"Create the mapping first under OEM Company Items."
                }), 404
            mapping_id = mapping.id

        if not mapping_id:
            db.session.rollback()
            return jsonify({"error": "Each item needs a mapping_id or a client_product_code"}), 400

        try:
            quantity = int(item.get('quantity'))
        except (TypeError, ValueError):
            quantity = None
        if not quantity or quantity <= 0:
            db.session.rollback()
            return jsonify({"error": "Each item needs a quantity greater than zero"}), 400

        line_item = POLineItem(
            order_id=new_po.id,
            mapping_id=mapping_id,
            quantity=quantity
        )
        db.session.add(line_item)

    try:
        db.session.commit()
        return jsonify({"status": "success", "message": "PO Created", "po_id": new_po.id}), 201
    except Exception as e:
        db.session.rollback()
        return jsonify({"error": str(e)}), 500

@orders_bp.route('/statuses', methods=['GET'], strict_slashes=False)
@jwt_required
def get_status_pipeline():
    return jsonify({"status": "success", "statuses": PO_STATUS_PIPELINE}), 200


@orders_bp.route('/<po_id>/status', methods=['PUT', 'OPTIONS'], strict_slashes=False)
@jwt_required
def update_po_status(po_id):
    """Moves a PO to a new stage in PO_STATUS_PIPELINE. Not restricted to
    the next sequential stage — manufacturing reality sometimes needs a
    manual correction backwards (e.g. a QC reject sending it back to
    In Production), so any valid pipeline stage is accepted."""
    if request.method == 'OPTIONS':
        return jsonify({}), 200

    po = PurchaseOrder.query.get(po_id)
    if not po:
        return jsonify({"error": "PO not found"}), 404

    data = request.get_json(silent=True) or {}
    new_status = data.get('status')
    if new_status not in PO_STATUS_PIPELINE:
        return jsonify({"error": f"status must be one of {PO_STATUS_PIPELINE}"}), 400

    po.status = new_status
    try:
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        return jsonify({"error": str(e)}), 500

    return jsonify({"status": "success", "po_id": po.id, "new_status": po.status}), 200


@orders_bp.route('/line-items/<line_item_id>', methods=['PUT', 'OPTIONS'], strict_slashes=False)
@jwt_required
def update_line_item_progress(line_item_id):
    """Updates a line item's production/dispatch progress independently of
    the parent PO's overall status — one PO can have one line fully done
    and another still short."""
    if request.method == 'OPTIONS':
        return jsonify({}), 200

    line_item = POLineItem.query.get(line_item_id)
    if not line_item:
        return jsonify({"error": "Line item not found"}), 404

    data = request.get_json(silent=True) or {}

    if 'produced_qty' in data:
        try:
            produced_qty = int(data['produced_qty'])
        except (TypeError, ValueError):
            return jsonify({"error": "produced_qty must be a number"}), 400
        if produced_qty < 0 or produced_qty > line_item.quantity:
            return jsonify({"error": f"produced_qty must be between 0 and {line_item.quantity}"}), 400
        line_item.produced_qty = produced_qty

    if 'dispatched_qty' in data:
        try:
            dispatched_qty = int(data['dispatched_qty'])
        except (TypeError, ValueError):
            return jsonify({"error": "dispatched_qty must be a number"}), 400
        if dispatched_qty < 0 or dispatched_qty > line_item.quantity:
            return jsonify({"error": f"dispatched_qty must be between 0 and {line_item.quantity}"}), 400
        line_item.dispatched_qty = dispatched_qty

    try:
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        return jsonify({"error": str(e)}), 500

    return jsonify({
        "status": "success",
        "line_item_id": line_item.id,
        "produced_qty": line_item.produced_qty,
        "dispatched_qty": line_item.dispatched_qty,
    }), 200


@orders_bp.route('/clubbed', methods=['GET'], strict_slashes=False)
@jwt_required
def get_clubbed_orders():
    """Aggregates all pending POs by translating OEM codes into Internal SKUs"""
    clubbed_data = db.session.query(
        InternalProduct.item_code.label('internal_code'),
        InternalProduct.name,
        InternalProduct.category,
        func.sum(POLineItem.quantity).label('total_required')
    ).join(
        OEMCompanyCode, POLineItem.mapping_id == OEMCompanyCode.id
    ).join(
        InternalProduct, OEMCompanyCode.internal_product_id == InternalProduct.id
    ).join(
        PurchaseOrder, POLineItem.order_id == PurchaseOrder.id
    ).filter(
        PurchaseOrder.status == 'Pending'
    ).group_by(
        InternalProduct.id
    ).all()

    result = []
    for row in clubbed_data:
        result.append({
            "internal_code": row.internal_code,
            "product_name": row.name,
            "category": row.category,
            "total_quantity_to_manufacture": row.total_required
        })

    return jsonify({"status": "success", "clubbed_orders": result}), 200