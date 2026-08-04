from flask import Blueprint, request, jsonify
from app import db
from app.models.recipe import ProductBOM
from app.models.item import InternalProduct
from app.core.decorators import jwt_required

recipes_bp = Blueprint('recipes', __name__)


@recipes_bp.route('/', methods=['GET'], strict_slashes=False)
@jwt_required
def list_recipes():
    """Lists every finished good that has at least one BOM row, with its components."""
    finished_good_ids = [row[0] for row in db.session.query(ProductBOM.finished_good_id).distinct().all()]

    result = []
    for fg_id in finished_good_ids:
        fg = InternalProduct.query.get(fg_id)
        if not fg:
            continue

        boms = ProductBOM.query.filter_by(finished_good_id=fg_id).all()
        components = []
        for b in boms:
            comp = InternalProduct.query.get(b.component_id)
            components.append({
                "id": b.id,
                "component_id": b.component_id,
                "component_code": comp.item_code if comp else None,
                "component_name": comp.name if comp else None,
                "quantity_required": b.quantity_required,
                "lazer_needed": b.lazer_needed,
            })

        result.append({
            "finished_good_id": fg_id,
            "finished_good_code": fg.item_code,
            "finished_good_name": fg.name,
            "component_count": len(components),
            "components": components,
        })

    return jsonify({"status": "success", "data": result}), 200


@recipes_bp.route('/', methods=['POST'], strict_slashes=False)
@jwt_required
def create_recipe():
    """
    Create/replace the BOM for a finished good.
    Body: {
      "finished_good_id": "...",
      "components": [
         {"component_id": "...", "quantity_required": 5, "lazer_needed": false},
         ...
      ]
    }
    """
    data = request.get_json()

    finished_good_id = data.get('finished_good_id') or data.get('output_item_id')
    components = data.get('components') or data.get('ingredients', [])

    if not finished_good_id or not components:
        return jsonify({"error": "finished_good_id and an array of components are required"}), 400

    finished_good = InternalProduct.query.get(finished_good_id)
    if not finished_good:
        return jsonify({"error": "Finished good not found in catalog"}), 404

    # Replace any existing BOM rows for this finished good (so re-saving a
    # recipe from the UI doesn't create duplicates).
    ProductBOM.query.filter_by(finished_good_id=finished_good_id).delete()

    for comp in components:
        component_id = comp.get('component_id') or comp.get('input_item_id')
        qty = float(comp.get('quantity_required', 0))
        lazer_needed = bool(comp.get('lazer_needed', False))

        if not component_id:
            db.session.rollback()
            return jsonify({"error": "Every component needs a component_id"}), 400

        if qty <= 0:
            db.session.rollback()
            return jsonify({"error": "Component quantities must be greater than zero"}), 400

        if not InternalProduct.query.get(component_id):
            db.session.rollback()
            return jsonify({"error": f"Component ID {component_id} not found"}), 404

        bom_row = ProductBOM(
            finished_good_id=finished_good_id,
            component_id=component_id,
            quantity_required=qty,
            lazer_needed=lazer_needed
        )
        db.session.add(bom_row)

    try:
        db.session.commit()
        return jsonify({"status": "success", "message": f"Recipe saved for {finished_good.name}"}), 201
    except Exception as e:
        db.session.rollback()
        return jsonify({"error": str(e)}), 500


@recipes_bp.route('/<finished_good_id>', methods=['GET'], strict_slashes=False)
@jwt_required
def get_recipe(finished_good_id):
    """Fetch the current BOM for a finished good, for editing/verification."""
    boms = ProductBOM.query.filter_by(finished_good_id=finished_good_id).all()
    result = []
    for b in boms:
        comp = InternalProduct.query.get(b.component_id)
        result.append({
            "id": b.id,
            "component_id": b.component_id,
            "component_code": comp.item_code if comp else None,
            "component_name": comp.name if comp else None,
            "quantity_required": b.quantity_required,
            "lazer_needed": b.lazer_needed
        })
    return jsonify({"status": "success", "components": result}), 200


@recipes_bp.route('/explode', methods=['POST'])
@jwt_required
def explode_orders():
    """
    The Engine: Takes a list of clubbed orders and explodes them
    into total aggregated raw material requirements, accounting for complex units.
    """
    data = request.get_json()
    orders = data.get('orders', [])

    if not orders:
        return jsonify({"error": "No orders provided for explosion"}), 400

    raw_materials_needed = {}

    unit_multiplier = {
        "pieces": 1,
        "pcs": 1,
        "gross": 144,
        "dozen": 12
    }

    for order in orders:
        fg_id = order.get('product_id')
        order_qty = order.get('quantity', 0)

        boms = ProductBOM.query.filter_by(finished_good_id=fg_id).all()

        for bom in boms:
            comp_id = bom.component_id
            comp = InternalProduct.query.get(comp_id)

            if not comp:
                continue

            comp_unit = str(comp.unit_of_measure).lower() if comp.unit_of_measure else "pieces"
            multiplier = unit_multiplier.get(comp_unit, 1)

            required_qty = (bom.quantity_required * multiplier) * order_qty

            if comp_id in raw_materials_needed:
                raw_materials_needed[comp_id] += required_qty
            else:
                raw_materials_needed[comp_id] = required_qty

    result = []
    for comp_id, total_qty in raw_materials_needed.items():
        comp = InternalProduct.query.get(comp_id)
        if comp:
            result.append({
                "component_id": comp_id,
                "internal_code": comp.item_code,
                "component_name": comp.name,
                "category": comp.category,
                "sub_category": comp.subcategory,
                "total_required_normalized": total_qty,
                "original_unit": comp.unit_of_measure
            })

    return jsonify({"status": "success", "data": result}), 200