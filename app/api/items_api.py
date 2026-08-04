from flask import Blueprint, request, jsonify
from app import db
from app.models.item import InternalProduct
from app.models.department import Department, DepartmentLevel
from app.core.decorators import jwt_required

items_bp = Blueprint('items', __name__)

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

    result = [{
        "id": str(i.id),
        "item_code": i.item_code,
        "oem_company_code": i.oem_company_code,
        "name": i.name,
        "department_id": i.department_id,
        "category": i.category,
        "subcategory": i.subcategory,
        "unit_of_measure": i.unit_of_measure,
        "pcs_per_scan": i.pcs_per_scan,
        "price": getattr(i, 'price', 0.0),
        "box_qty": getattr(i, 'box_qty', 0),
        "carton_qty": getattr(i, 'carton_qty', 0)
    } for i in items]

    return jsonify({"status": "success", "data": result}), 200

@items_bp.route('/', methods=['POST', 'OPTIONS'], strict_slashes=False)
@jwt_required
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

    new_item = InternalProduct(
        item_code=item_code,
        oem_company_code=data.get('oem_company_code'),
        name=data.get('name'),
        department_id=data.get('department_id'),
        category=data.get('category'),
        subcategory=data.get('subcategory'),
        unit_of_measure=data.get('unit_of_measure', 'pcs'),
        pcs_per_scan=int(data.get('pcs_per_scan', 1)),
        price=float(data.get('price', 0.0)),
        box_qty=int(data.get('box_qty', 0)),
        carton_qty=int(data.get('carton_qty', 0))
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

    if 'item_code' in data: item.item_code = data['item_code']
    if 'oem_company_code' in data: item.oem_company_code = data['oem_company_code']
    if 'name' in data: item.name = data['name']
    if 'department_id' in data: item.department_id = data['department_id']
    if 'category' in data: item.category = data['category']
    if 'subcategory' in data: item.subcategory = data['subcategory']
    if 'unit_of_measure' in data: item.unit_of_measure = data['unit_of_measure']

    if 'pcs_per_scan' in data: item.pcs_per_scan = int(data['pcs_per_scan'] or 1)
    if 'price' in data: item.price = float(data['price'] or 0.0)
    if 'box_qty' in data: item.box_qty = int(data['box_qty'] or 0)
    if 'carton_qty' in data: item.carton_qty = int(data['carton_qty'] or 0)

    try:
        db.session.commit()
        return jsonify({"status": "success", "message": "Item updated"}), 200
    except Exception as e:
        db.session.rollback()
        return jsonify({"error": str(e)}), 500
