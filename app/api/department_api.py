from flask import Blueprint, request, jsonify
from app import db
from app.models.department import Department, DeptLevel
from app.models.item import DepartmentStock, InternalProduct



department_bp = Blueprint('departments', __name__)

@department_bp.route('/', methods=['GET'])
def get_departments():
    departments = Department.query.filter_by(is_active=1).all()
    result = [
        {
            "id": d.id, 
            "department_code": d.department_code, 
            "name": d.name, 
            "level": d.department_level
        } for d in departments
    ]
    return jsonify({"status": "success", "data": result}), 200

@department_bp.route('/', methods=['POST'])
def create_department():
    data = request.get_json()
    name = data.get('name')
    department_code = data.get('department_code') 
    level_int = data.get('department_level', 0)
    
    if not name:
        return jsonify({"error": "Department name is required"}), 400
        
    try:
        valid_level = DeptLevel(level_int)
    except ValueError:
        return jsonify({"error": "Invalid department_level."}), 400
        
    existing = Department.query.filter_by(name=name).first()
    if existing:
        return jsonify({"error": "Department already exists"}), 409
        
    # --- AUTO-INCREMENT LOGIC ---
    if department_code is None or str(department_code).strip() == "":
        # Find the highest existing department_code
        max_code = db.session.query(db.func.max(Department.department_code)).scalar()
        # If no departments exist, start at 1. Otherwise, add 1 to the max.
        department_code = (max_code or 0) + 1
    else:
        # If the admin manually provided a code, make sure it's an integer
        try:
            department_code = int(department_code)
        except ValueError:
            return jsonify({"error": "department_code must be an integer"}), 400
            
        # Check if the manual code is already taken
        existing_code = Department.query.filter_by(department_code=department_code).first()
        if existing_code:
            return jsonify({"error": f"Department code {department_code} is already in use"}), 409
    # -----------------------------
        
    new_dept = Department(
        name=name,
        department_code=department_code,
        department_level=valid_level.value
    )
    
    try:
        db.session.add(new_dept)
        db.session.commit()
        return jsonify({
            "status": "success", 
            "message": f"Department {name} created", 
            "id": new_dept.id,
            "department_code": new_dept.department_code
        }), 201
    except Exception as e:
        db.session.rollback()
        return jsonify({"error": str(e)}), 500
@department_bp.route('/<string:department_id>/stock', methods=['GET'])
def get_department_stock(department_id):
    """View the live physical inventory currently sitting in a specific department"""
    
    # 1. Verify the department exists
    dept = Department.query.get(department_id)
    if not dept:
        return jsonify({"error": "Department not found"}), 404

    # 2. Query the bridge table (The Physical Shelves)
    stock_records = DepartmentStock.query.filter_by(department_id=department_id).all()
    
    result = []
    for record in stock_records:
        # 3. Look up the item in the Master Catalog to get its name and unit
        item = InternalProduct.query.get(record.item_id)
        if item and record.quantity > 0: # Only show it if there is actual stock
            result.append({
                "item_id": item.id,
                "item_name": item.name,
                "item_code": item.item_code,
                "category": item.category,
                "quantity_on_shelf": record.quantity,
                "unit_of_measure": item.unit_of_measure,
                "last_updated": record.last_updated
            })
            
    return jsonify({
        "status": "success",
        "department_name": dept.name,
        "stock": result
    }), 200
    