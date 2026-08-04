from flask import Blueprint, request, jsonify
from app import db
from app.models.item import BoxMapping, InternalProduct
from app.core.decorators import jwt_required

box_bp = Blueprint('boxes', __name__)


@box_bp.route('/mappings', methods=['GET', 'OPTIONS'], strict_slashes=False)
@jwt_required
def get_box_mappings():
    if request.method == 'OPTIONS':
        return jsonify({}), 200

    mappings = BoxMapping.query.order_by(BoxMapping.created_at.desc()).all()
    box_ids = {m.box_item_id for m in mappings}
    product_ids = {m.product_id for m in mappings}
    items = {i.id: i for i in InternalProduct.query.filter(InternalProduct.id.in_(box_ids | product_ids)).all()}

    result = []
    for m in mappings:
        box = items.get(m.box_item_id)
        product = items.get(m.product_id)
        result.append({
            "id": m.id,
            "box_item_id": m.box_item_id,
            "box_name": box.name if box else "Unknown Box",
            "box_code": box.item_code if box else None,
            "product_id": m.product_id,
            "product_name": product.name if product else "Unknown Product",
            "product_code": product.item_code if product else None,
            "pcs_per_box": m.pcs_per_box,
        })

    return jsonify({"status": "success", "data": result}), 200


@box_bp.route('/mappings', methods=['POST', 'OPTIONS'], strict_slashes=False)
@jwt_required
def create_or_update_box_mapping():
    """Upsert: saving the same (box, product) pair again just updates the
    quantity instead of erroring, so re-editing from the UI is simple."""
    if request.method == 'OPTIONS':
        return jsonify({}), 200

    data = request.get_json(silent=True) or {}
    box_item_id = data.get('box_item_id')
    product_id = data.get('product_id')
    pcs_per_box = data.get('pcs_per_box')

    if not box_item_id or not product_id:
        return jsonify({"error": "box_item_id and product_id are required"}), 400
    try:
        pcs_per_box = int(pcs_per_box)
        if pcs_per_box <= 0:
            raise ValueError()
    except (TypeError, ValueError):
        return jsonify({"error": "pcs_per_box must be a positive integer"}), 400

    if not InternalProduct.query.get(box_item_id):
        return jsonify({"error": "Box item not found"}), 404
    if not InternalProduct.query.get(product_id):
        return jsonify({"error": "Product not found"}), 404

    existing = BoxMapping.query.filter_by(box_item_id=box_item_id, product_id=product_id).first()
    if existing:
        existing.pcs_per_box = pcs_per_box
        message = "Mapping updated"
        mapping_id = existing.id
    else:
        new_mapping = BoxMapping(box_item_id=box_item_id, product_id=product_id, pcs_per_box=pcs_per_box)
        db.session.add(new_mapping)
        db.session.flush()
        message = "Mapping created"
        mapping_id = new_mapping.id

    try:
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        return jsonify({"error": str(e)}), 500

    return jsonify({"status": "success", "message": message, "id": mapping_id}), 201


@box_bp.route('/mappings/<mapping_id>', methods=['DELETE', 'OPTIONS'], strict_slashes=False)
@jwt_required
def delete_box_mapping(mapping_id):
    if request.method == 'OPTIONS':
        return jsonify({}), 200

    mapping = BoxMapping.query.get(mapping_id)
    if not mapping:
        return jsonify({"error": "Mapping not found"}), 404

    db.session.delete(mapping)
    try:
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        return jsonify({"error": str(e)}), 500

    return jsonify({"status": "success", "message": "Mapping deleted"}), 200
