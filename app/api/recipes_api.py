from flask import Blueprint, request, jsonify, g
from app import db
from app.models.recipe import ProductBOM, BOMVersion
from app.models.item import InternalProduct
from app.core.decorators import jwt_required
from sqlalchemy import func

recipes_bp = Blueprint('recipes', __name__)

MAX_BOM_DEPTH = 12

UNIT_MULTIPLIER = {
    "pieces": 1,
    "pcs": 1,
    "gross": 144,
    "dozen": 12,
}


def _serialize_components(bom_version):
    components = []
    for b in bom_version.components:
        comp = InternalProduct.query.get(b.component_id)
        has_sub_recipe = BOMVersion.query.filter_by(finished_good_id=b.component_id, is_active=True).first() is not None
        components.append({
            "id": b.id,
            "component_id": b.component_id,
            "component_code": comp.item_code if comp else None,
            "component_name": comp.name if comp else None,
            "quantity_required": b.quantity_required,
            "lazer_needed": b.lazer_needed,
            "has_sub_recipe": has_sub_recipe,
        })
    return components


@recipes_bp.route('/', methods=['GET'], strict_slashes=False)
@jwt_required
def list_recipes():
    """Lists every item with an active recipe — a finished good or an
    intermediate component/subassembly, since either can now have its own
    BOM (that's what makes multi-level explosion possible)."""
    active_versions = BOMVersion.query.filter_by(is_active=True).all()

    result = []
    for bv in active_versions:
        fg = InternalProduct.query.get(bv.finished_good_id)
        if not fg:
            continue

        components = _serialize_components(bv)
        result.append({
            "finished_good_id": bv.finished_good_id,
            "finished_good_code": fg.item_code,
            "finished_good_name": fg.name,
            "version": bv.version,
            "component_count": len(components),
            "components": components,
        })

    return jsonify({"status": "success", "data": result}), 200


@recipes_bp.route('/', methods=['POST'], strict_slashes=False)
@jwt_required
def create_recipe():
    """
    Creates a NEW VERSION of an item's BOM — never overwrites history.
    The previous active version (if any) is marked inactive but stays
    retrievable via GET /<id>?version=N.
    Body: {
      "finished_good_id": "...",
      "notes": "...",              # optional, why this revision was made
      "components": [
         {"component_id": "...", "quantity_required": 5, "lazer_needed": false},
         ...
      ]
    }
    """
    data = request.get_json()

    finished_good_id = data.get('finished_good_id') or data.get('output_item_id')
    components = data.get('components') or data.get('ingredients', [])
    notes = data.get('notes')

    if not finished_good_id or not components:
        return jsonify({"error": "finished_good_id and an array of components are required"}), 400

    finished_good = InternalProduct.query.get(finished_good_id)
    if not finished_good:
        return jsonify({"error": "Item not found in catalog"}), 404

    for comp in components:
        cid = comp.get('component_id') or comp.get('input_item_id')
        if cid == finished_good_id:
            return jsonify({"error": "A recipe cannot include itself as a component"}), 400

    last_version = db.session.query(func.max(BOMVersion.version)).filter_by(
        finished_good_id=finished_good_id
    ).scalar()
    next_version_num = (last_version or 0) + 1

    BOMVersion.query.filter_by(finished_good_id=finished_good_id, is_active=True).update({"is_active": False})

    new_version = BOMVersion(
        finished_good_id=finished_good_id,
        version=next_version_num,
        is_active=True,
        notes=notes,
        created_by=g.current_user.id,
    )
    db.session.add(new_version)
    db.session.flush()

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

        db.session.add(ProductBOM(
            bom_version_id=new_version.id,
            component_id=component_id,
            quantity_required=qty,
            lazer_needed=lazer_needed
        ))

    try:
        db.session.commit()
        return jsonify({
            "status": "success",
            "message": f"Recipe v{next_version_num} saved for {finished_good.name}",
            "version": next_version_num,
        }), 201
    except Exception as e:
        db.session.rollback()
        return jsonify({"error": str(e)}), 500


@recipes_bp.route('/<finished_good_id>', methods=['GET'], strict_slashes=False)
@jwt_required
def get_recipe(finished_good_id):
    """Fetch a BOM for an item — the active version by default, or a
    specific historical version via ?version=N (for editing/verification,
    or checking what a production run released against actually used)."""
    version_param = request.args.get('version', type=int)

    if version_param:
        bom_version = BOMVersion.query.filter_by(finished_good_id=finished_good_id, version=version_param).first()
    else:
        bom_version = BOMVersion.query.filter_by(finished_good_id=finished_good_id, is_active=True).first()

    if not bom_version:
        return jsonify({"status": "success", "components": [], "version": None}), 200

    return jsonify({
        "status": "success",
        "components": _serialize_components(bom_version),
        "version": bom_version.version,
    }), 200


@recipes_bp.route('/<finished_good_id>/versions', methods=['GET'], strict_slashes=False)
@jwt_required
def get_recipe_versions(finished_good_id):
    """Lists every version ever saved for this item, newest first."""
    versions = BOMVersion.query.filter_by(finished_good_id=finished_good_id).order_by(BOMVersion.version.desc()).all()
    result = [{
        "id": v.id,
        "version": v.version,
        "is_active": v.is_active,
        "notes": v.notes,
        "component_count": len(v.components),
        "created_at": v.created_at.isoformat() if v.created_at else None,
    } for v in versions]
    return jsonify({"status": "success", "versions": result}), 200


def _explode_component(component_id, qty_needed, visited, depth):
    """Recurses into a component's own active BOM, if it has one, down to
    raw materials (components with no BOM of their own = leaves)."""
    if depth > MAX_BOM_DEPTH:
        raise ValueError(f"BOM nesting exceeds {MAX_BOM_DEPTH} levels (likely a circular reference)")
    if component_id in visited:
        raise ValueError("Circular BOM reference detected — a component's recipe refers back to itself")

    active_version = BOMVersion.query.filter_by(finished_good_id=component_id, is_active=True).first()
    if not active_version:
        return {component_id: qty_needed}

    child_visited = visited | {component_id}
    totals = {}
    for row in active_version.components:
        comp = InternalProduct.query.get(row.component_id)
        comp_unit = str(comp.unit_of_measure).lower() if comp and comp.unit_of_measure else "pieces"
        multiplier = UNIT_MULTIPLIER.get(comp_unit, 1)
        sub_qty = (row.quantity_required * multiplier) * qty_needed

        sub_totals = _explode_component(row.component_id, sub_qty, child_visited, depth + 1)
        for k, v in sub_totals.items():
            totals[k] = totals.get(k, 0) + v
    return totals


@recipes_bp.route('/explode', methods=['POST'])
@jwt_required
def explode_orders():
    """
    The Engine: takes a list of orders and explodes them into total
    aggregated raw-material requirements — recursively, all the way down
    through any subassemblies that have their own recipe (multi-level
    BOM), not just the finished good's direct components.
    """
    data = request.get_json()
    orders = data.get('orders', [])

    if not orders:
        return jsonify({"error": "No orders provided for explosion"}), 400

    raw_materials_needed = {}

    for order in orders:
        fg_id = order.get('product_id')
        order_qty = order.get('quantity', 0)

        active_version = BOMVersion.query.filter_by(finished_good_id=fg_id, is_active=True).first()
        if not active_version:
            continue

        try:
            for row in active_version.components:
                comp = InternalProduct.query.get(row.component_id)
                comp_unit = str(comp.unit_of_measure).lower() if comp and comp.unit_of_measure else "pieces"
                multiplier = UNIT_MULTIPLIER.get(comp_unit, 1)
                sub_qty = (row.quantity_required * multiplier) * order_qty

                sub_totals = _explode_component(row.component_id, sub_qty, {fg_id}, 1)
                for k, v in sub_totals.items():
                    raw_materials_needed[k] = raw_materials_needed.get(k, 0) + v
        except ValueError as e:
            return jsonify({"error": str(e)}), 400

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
