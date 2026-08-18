from flask import Blueprint, request, jsonify
from app import db
from app.models.item import InternalProduct
from app.models.supplier import Supplier, SupplierItem
from app.core.mrp import compute_shortages
from app.core.decorators import jwt_required

mrp_bp = Blueprint('mrp', __name__)


@mrp_bp.route('/summary', methods=['GET', 'OPTIONS'], strict_slashes=False)
@jwt_required
def get_summary():
    if request.method == 'OPTIONS':
        return jsonify({}), 200

    shortages = compute_shortages()
    rows = list(shortages.values())
    rows.sort(key=lambda r: r['shortage'], reverse=True)

    # Group shortage rows by their linked supplier (an item with multiple
    # suppliers appears once per supplier group; unlinked items land in
    # "Unassigned" so nothing silently disappears).
    grouped = {}
    for row in rows:
        if row['shortage'] <= 0:
            continue
        targets = row['suppliers'] or [{"id": None, "name": "Unassigned"}]
        for supplier in targets:
            key = supplier['id'] or 'unassigned'
            if key not in grouped:
                grouped[key] = {"supplier_id": supplier['id'], "supplier_name": supplier['name'], "items": []}
            grouped[key]['items'].append(row)

    return jsonify({
        "status": "success",
        "items": rows,
        "shortage_count": sum(1 for r in rows if r['shortage'] > 0),
        "grouped_by_supplier": list(grouped.values()),
    }), 200


@mrp_bp.route('/assign-supplier', methods=['POST', 'OPTIONS'], strict_slashes=False)
@jwt_required
def assign_supplier():
    """Links an item to a supplier so future MRP shortages for it get
    grouped under that supplier instead of 'Unassigned'."""
    if request.method == 'OPTIONS':
        return jsonify({}), 200

    data = request.get_json(silent=True) or {}
    item_id = data.get('item_id')
    supplier_id = data.get('supplier_id')

    if not item_id or not supplier_id:
        return jsonify({"error": "item_id and supplier_id are required"}), 400
    if not InternalProduct.query.get(item_id):
        return jsonify({"error": "Item not found"}), 404
    if not Supplier.query.get(supplier_id):
        return jsonify({"error": "Supplier not found"}), 404

    existing = SupplierItem.query.filter_by(item_id=item_id, supplier_id=supplier_id).first()
    if existing:
        return jsonify({"status": "success", "message": "Already linked", "id": existing.id}), 200

    link = SupplierItem(item_id=item_id, supplier_id=supplier_id)
    db.session.add(link)
    try:
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        return jsonify({"error": str(e)}), 500

    return jsonify({"status": "success", "id": link.id}), 201


@mrp_bp.route('/assign-supplier/<link_id>', methods=['DELETE', 'OPTIONS'], strict_slashes=False)
@jwt_required
def unassign_supplier(link_id):
    if request.method == 'OPTIONS':
        return jsonify({}), 200

    link = SupplierItem.query.get(link_id)
    if not link:
        return jsonify({"error": "Link not found"}), 404

    db.session.delete(link)
    try:
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        return jsonify({"error": str(e)}), 500

    return jsonify({"status": "success"}), 200
