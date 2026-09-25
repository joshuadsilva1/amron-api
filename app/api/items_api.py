from flask import Blueprint, request, jsonify
from app import db
from app.models.item import InternalProduct
from app.models.department import Department, DepartmentLevel
from app.models.unit import UnitOfMeasure
from app.core.department_levels import final_level_rank
from app.core.decorators import jwt_required, permission_required
from app.core.audit import log_audit

items_bp = Blueprint('items', __name__)

VALID_POWDER_COLOURS = {'White', 'Grey', 'Black'}


def _clean_powder_colour(value):
    """Returns (colour, error_message). colour is None (clear it), one of
    VALID_POWDER_COLOURS, or the original value is rejected outright."""
    if value in (None, ''):
        return None, None
    normalized = str(value).strip().capitalize()
    if normalized not in VALID_POWDER_COLOURS:
        return None, f"powder_colour must be one of {sorted(VALID_POWDER_COLOURS)} or blank"
    return normalized, None

@items_bp.route('/', methods=['GET', 'OPTIONS'], strict_slashes=False)
@jwt_required
def get_items():
    if request.method == 'OPTIONS':
        return jsonify({}), 200

    query = InternalProduct.query.filter_by(is_active=1)

    department_id = request.args.get('department_id')
    if department_id:
        query = query.filter_by(department_id=department_id)

    # A "finished good" isn't a category/type flag — it's an item currently
    # sitting in the highest-ranked configured level (i.e. Dispatch).
    # Accepts "FINAL" (the highest rank currently defined, whatever it's
    # named), a level's name, or its raw numeric rank.
    department_level = request.args.get('department_level')
    if department_level is not None:
        if department_level.upper() == 'FINAL':
            level_value = db.session.query(db.func.max(DepartmentLevel.rank)).scalar()
            if level_value is None:
                return jsonify({"error": "No department levels are configured yet."}), 400
        else:
            level_row = DepartmentLevel.query.filter(
                db.func.lower(DepartmentLevel.name) == department_level.lower()
            ).first()
            if level_row:
                level_value = level_row.rank
            else:
                try:
                    level_value = int(department_level)
                except ValueError:
                    return jsonify({"error": f"Invalid department_level '{department_level}'"}), 400
        query = query.join(Department, InternalProduct.department_id == Department.id).filter(
            Department.department_level == level_value
        )

    items = query.all()

    # Finished good = lives in a department on the top level (see
    # app/core/department_levels.py). Resolved here once so screens
    # (PO product picker, price field) don't each re-derive it.
    final_rank = final_level_rank()
    final_dept_ids = {
        d.id for d in Department.query.filter_by(department_level=final_rank).all()
    } if final_rank is not None else set()

    result = [{
        "id": str(i.id),
        "item_code": i.item_code,
        "oem_company_code": i.oem_company_code,
        "name": i.name,
        "description": i.description,
        "department_id": i.department_id,
        "is_finished_good": i.department_id in final_dept_ids,
        "category": i.category,
        "subcategory": i.subcategory,
        "unit_of_measure": i.unit_of_measure,
        "pcs_per_scan": i.pcs_per_scan,
        "price": getattr(i, 'price', 0.0),
        "box_qty": getattr(i, 'box_qty', 0),
        "carton_qty": getattr(i, 'carton_qty', 0),
        "powder_colour": i.powder_colour,
    } for i in items]

    return jsonify({"status": "success", "data": result}), 200

@items_bp.route('/', methods=['POST', 'OPTIONS'], strict_slashes=False)
@jwt_required
@permission_required('scan_inventory', 'manage_recipes')
def create_item():
    if request.method == 'OPTIONS':
        return jsonify({}), 200

    data = request.get_json(silent=True) or {}

    item_code = data.get('item_code')

    if not data.get('name') or not data.get('department_id') or not item_code:
        return jsonify({"error": "Code, Department, and Name are required"}), 400

    existing = InternalProduct.query.filter_by(item_code=item_code).first()
    if existing:
        return jsonify({"error": f"Item code {item_code} already exists"}), 409

    powder_colour, colour_error = _clean_powder_colour(data.get('powder_colour'))
    if colour_error:
        return jsonify({"error": colour_error}), 400

    new_item = InternalProduct(
        item_code=item_code,
        oem_company_code=data.get('oem_company_code'),
        name=data.get('name'),
        description=data.get('description') or None,
        department_id=data.get('department_id'),
        category=data.get('category'),
        subcategory=data.get('subcategory'),
        unit_of_measure=data.get('unit_of_measure', 'pcs'),
        pcs_per_scan=int(data.get('pcs_per_scan', 1)),
        price=float(data.get('price', 0.0)),
        box_qty=int(data.get('box_qty', 0)),
        carton_qty=int(data.get('carton_qty', 0)),
        powder_colour=powder_colour,
    )

    try:
        db.session.add(new_item)
        db.session.commit()
        return jsonify({
            "status": "success",
            "message": f"Item created successfully",
            "id": str(new_item.id)
        }), 201
    except Exception as e:
        db.session.rollback()
        return jsonify({"error": str(e)}), 500

@items_bp.route('/<item_id>', methods=['PUT', 'OPTIONS'], strict_slashes=False)
@jwt_required
@permission_required('scan_inventory', 'manage_recipes')
def update_item(item_id):
    if request.method == 'OPTIONS':
        return jsonify({}), 200

    item = InternalProduct.query.get(item_id)
    if not item:
        return jsonify({"error": "Item not found"}), 404

    data = request.get_json(silent=True) or {}

    if 'item_code' in data and data['item_code'] != item.item_code:
        existing = InternalProduct.query.filter_by(item_code=data['item_code']).first()
        if existing:
            return jsonify({"error": f"Item code {data['item_code']} is already taken."}), 409
        # The printed QR label encodes item_code (see labels_api), so
        # changing it makes every label already stuck on a package stop
        # scanning. Only allowed when the caller explicitly confirms.
        if not data.get('confirm_code_change'):
            return jsonify({
                "error": "Changing the item code will make QR labels already printed for this item stop scanning. "
                         "Confirm the change to continue.",
                "code": "confirm_code_change",
            }), 409
        log_audit(
            'item.item_code.update', 'internal_product', item_id,
            payload_before={"item_code": item.item_code},
            payload_after={"item_code": data['item_code']},
        )

    if 'item_code' in data: item.item_code = data['item_code']
    if 'oem_company_code' in data: item.oem_company_code = data['oem_company_code']
    if 'name' in data: item.name = data['name']
    if 'description' in data: item.description = data['description'] or None
    if 'department_id' in data: item.department_id = data['department_id']
    if 'category' in data: item.category = data['category']
    if 'subcategory' in data: item.subcategory = data['subcategory']
    if 'unit_of_measure' in data: item.unit_of_measure = data['unit_of_measure']

    if 'pcs_per_scan' in data: item.pcs_per_scan = int(data['pcs_per_scan'] or 1)
    if 'price' in data: item.price = float(data['price'] or 0.0)
    if 'box_qty' in data: item.box_qty = int(data['box_qty'] or 0)
    if 'carton_qty' in data: item.carton_qty = int(data['carton_qty'] or 0)

    if 'powder_colour' in data:
        powder_colour, colour_error = _clean_powder_colour(data['powder_colour'])
        if colour_error:
            return jsonify({"error": colour_error}), 400
        # Switching an item to White while it's already flagged
        # colour_needed on a live recipe would silently violate the
        # White->Colour block, so recheck every active BOM row that
        # references this component before allowing the change.
        if powder_colour == 'White':
            from app.models.recipe import ProductBOM, BOMVersion
            conflicting = (
                db.session.query(ProductBOM)
                .join(BOMVersion, ProductBOM.bom_version_id == BOMVersion.id)
                .filter(
                    BOMVersion.is_active == True,
                    ProductBOM.component_id == item_id,
                    ProductBOM.colour_needed == True,
                )
                .first()
            )
            if conflicting:
                return jsonify({
                    "error": "This item is used as a colour_needed component in an active recipe. "
                             "White moulded parts can't be routed to Colour — update the recipe first."
                }), 409
        if powder_colour != item.powder_colour:
            log_audit(
                'item.powder_colour.update', 'internal_product', item_id,
                payload_before={"item_code": item.item_code, "powder_colour": item.powder_colour},
                payload_after={"item_code": item.item_code, "powder_colour": powder_colour},
            )
        item.powder_colour = powder_colour

    try:
        db.session.commit()
        return jsonify({"status": "success", "message": "Item updated"}), 200
    except Exception as e:
        db.session.rollback()
        return jsonify({"error": str(e)}), 500


@items_bp.route('/units', methods=['GET'], strict_slashes=False)
@jwt_required
def list_units():
    units = UnitOfMeasure.query.order_by(UnitOfMeasure.name.asc()).all()
    return jsonify({"status": "success", "data": [
        {"id": u.id, "name": u.name, "description": u.description} for u in units
    ]}), 200


@items_bp.route('/units', methods=['POST', 'OPTIONS'], strict_slashes=False)
@jwt_required
@permission_required('scan_inventory', 'manage_recipes')
def create_unit():
    if request.method == 'OPTIONS':
        return jsonify({}), 200

    data = request.get_json(silent=True) or {}
    name = (data.get('name') or '').strip()
    if not name:
        return jsonify({"error": "Unit name is required"}), 400
    if len(name) > 20:
        return jsonify({"error": "Unit name must be 20 characters or fewer"}), 400
    if UnitOfMeasure.query.filter(db.func.lower(UnitOfMeasure.name) == name.lower()).first():
        return jsonify({"error": f"Unit '{name}' already exists"}), 409

    unit = UnitOfMeasure(name=name, description=(data.get('description') or '').strip() or None)
    db.session.add(unit)
    try:
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        return jsonify({"error": str(e)}), 500
    return jsonify({"status": "success", "id": unit.id, "name": unit.name}), 201


@items_bp.route('/units/<int:unit_id>', methods=['DELETE', 'OPTIONS'], strict_slashes=False)
@jwt_required
@permission_required('scan_inventory', 'manage_recipes')
def delete_unit(unit_id):
    if request.method == 'OPTIONS':
        return jsonify({}), 200

    unit = UnitOfMeasure.query.get(unit_id)
    if not unit:
        return jsonify({"error": "Unit not found"}), 404
    in_use = InternalProduct.query.filter_by(unit_of_measure=unit.name, is_active=1).count()
    if in_use:
        return jsonify({"error": f"'{unit.name}' is used by {in_use} item(s) — change them first."}), 409

    db.session.delete(unit)
    try:
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        return jsonify({"error": str(e)}), 500
    return jsonify({"status": "success"}), 200
