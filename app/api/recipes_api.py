from flask import Blueprint, request, jsonify, g
from app import db
from app.models.recipe import ProductBOM, BOMVersion
from app.models.item import InternalProduct
from app.models.department import Department
from app.core.department_levels import is_finished_good
from app.core.decorators import jwt_required, permission_required, user_has_permission
from app.core.bom import explode_product_quantity
from app.models.system_setting import get_default_wastage_percent
from sqlalchemy import func

recipes_bp = Blueprint('recipes', __name__)


def _serialize_components(bom_version):
    """One finished good's components can be drawn from several different
    departments (e.g. a moulded body from Moulding plus a brass insert
    from Brasspart) — component_department_* here is what tells the UI
    (and anything downstream reading this list) which department each
    line is actually coming from, since ProductBOM itself has no
    department column (see app/models/recipe.py)."""
    components = []
    for b in bom_version.components:
        comp = InternalProduct.query.get(b.component_id)
        dept = Department.query.get(comp.department_id) if comp and comp.department_id else None
        has_sub_recipe = BOMVersion.query.filter_by(finished_good_id=b.component_id, is_active=True).first() is not None
        components.append({
            "id": b.id,
            "component_id": b.component_id,
            "component_code": comp.item_code if comp else None,
            "component_name": comp.name if comp else None,
            "component_department_id": comp.department_id if comp else None,
            "component_department_name": dept.name if dept else None,
            "component_powder_colour": comp.powder_colour if comp else None,
            "quantity_required": b.quantity_required,
            "lazer_needed": b.lazer_needed,
            "colour_needed": b.colour_needed,
            "wastage_percent": b.wastage_percent,
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
        departments = sorted({c["component_department_name"] for c in components if c["component_department_name"]})
        result.append({
            "finished_good_id": bv.finished_good_id,
            "finished_good_code": fg.item_code,
            "finished_good_name": fg.name,
            "version": bv.version,
            "component_count": len(components),
            "departments": departments,
            "components": components,
        })

    return jsonify({"status": "success", "data": result}), 200


@recipes_bp.route('/', methods=['POST'], strict_slashes=False)
@jwt_required
@permission_required('manage_recipes')
def create_recipe():
    """
    Creates a NEW VERSION of an item's BOM — never overwrites history.
    The previous active version (if any) is marked inactive but stays
    retrievable via GET /<id>?version=N.
    Body: {
      "finished_good_id": "...",
      "notes": "...",              # optional, why this revision was made
      "components": [
         {"component_id": "...", "quantity_required": 5, "lazer_needed": false,
          "colour_needed": false, "wastage_percent": 10},   # wastage_percent: Admin only, see below
         ...
      ]
    }

    wastage_percent is admin-only (manage_wastage permission) since it's a
    factory-wide judgment call, not a per-recipe-edit one, and it varies
    over time (e.g. 10% today, 12% next quarter). A non-admin saving a new
    version simply carries forward whatever wastage_percent the component
    already had on the previous active version (0 if it's new) — they can
    still edit quantity_required/lazer_needed/colour_needed freely, they
    just can't touch the wastage number.
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
        component = InternalProduct.query.get(cid)
        if is_finished_good(component):
            return jsonify({
                "error": f"'{component.item_code}' is a finished good and can't be a component of another recipe."
            }), 400

    can_edit_wastage = user_has_permission(g.current_user, 'manage_wastage')

    # Carry-forward map for wastage_percent: {component_id: last active value}.
    # A component with no prior value (brand new to this recipe) falls back
    # to the admin-configurable default rather than a hardcoded 0 — see
    # system_settings.default_wastage_percent.
    prior_version = BOMVersion.query.filter_by(finished_good_id=finished_good_id, is_active=True).first()
    prior_wastage = {row.component_id: row.wastage_percent for row in prior_version.components} if prior_version else {}
    default_wastage = get_default_wastage_percent()

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
        colour_needed = bool(comp.get('colour_needed', False))

        carried_forward = prior_wastage.get(component_id, default_wastage)
        if 'wastage_percent' in comp:
            requested_wastage = float(comp.get('wastage_percent') or 0)
            if requested_wastage != carried_forward and not can_edit_wastage:
                db.session.rollback()
                return jsonify({
                    "error": f"wastage_percent can only be changed by an Admin (component {component_id})."
                }), 403
            wastage_percent = requested_wastage
        else:
            wastage_percent = carried_forward

        if not component_id:
            db.session.rollback()
            return jsonify({"error": "Every component needs a component_id"}), 400

        if qty <= 0:
            db.session.rollback()
            return jsonify({"error": "Component quantities must be greater than zero"}), 400

        component_row = InternalProduct.query.get(component_id)
        if not component_row:
            db.session.rollback()
            return jsonify({"error": f"Component ID {component_id} not found"}), 404

        # Hard routing rule: powder colour dictates the Colour department.
        # Only Black/Grey moulded parts may go there — White never can.
        if colour_needed and component_row.powder_colour == 'White':
            db.session.rollback()
            return jsonify({
                "error": f"'{component_row.item_code}' is a White moulded part and can never be routed to "
                         "Colour. Only Black/Grey parts may set colour_needed."
            }), 400

        db.session.add(ProductBOM(
            bom_version_id=new_version.id,
            component_id=component_id,
            quantity_required=qty,
            lazer_needed=lazer_needed,
            colour_needed=colour_needed,
            wastage_percent=wastage_percent,
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

        try:
            sub_totals = explode_product_quantity(fg_id, order_qty)
        except ValueError as e:
            return jsonify({"error": str(e)}), 400

        for k, v in sub_totals.items():
            raw_materials_needed[k] = raw_materials_needed.get(k, 0) + v

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
