# from flask import Blueprint, request, jsonify
# from app import db
# from app.models.department import Department, DeptLevel
# from app.models.item import DepartmentStock, InternalProduct
# from app.core.decorators import jwt_required


# department_bp = Blueprint('departments', __name__)

# @department_bp.route('/', methods=['GET'], strict_slashes=False)
# @jwt_required
# def get_departments():
#     departments = Department.query.filter_by(is_active=1).all()
#     result = [
#         {
#             "id": d.id, 
#             "department_code": d.department_code, 
#             "name": d.name, 
#             "level": d.department_level
#         } for d in departments
#     ]
#     return jsonify({"status": "success", "data": result}), 200

# @department_bp.route('/', methods=['POST'])
# @jwt_required
# def create_department():
#     data = request.get_json()
#     name = data.get('name')
#     department_code = data.get('department_code') 
#     level_int = data.get('department_level', 0)
    
#     if not name:
#         return jsonify({"error": "Department name is required"}), 400
        
#     try:
#         valid_level = DeptLevel(level_int)
#     except ValueError:
#         return jsonify({"error": "Invalid department_level."}), 400
        
#     existing = Department.query.filter_by(name=name).first()
#     if existing:
#         return jsonify({"error": "Department already exists"}), 409
        
#     # --- AUTO-INCREMENT LOGIC ---
#     if department_code is None or str(department_code).strip() == "":
#         # Find the highest existing department_code
#         max_code = db.session.query(db.func.max(Department.department_code)).scalar()
#         # If no departments exist, start at 1. Otherwise, add 1 to the max.
#         department_code = (max_code or 0) + 1
#     else:
#         # If the admin manually provided a code, make sure it's an integer
#         try:
#             department_code = int(department_code)
#         except ValueError:
#             return jsonify({"error": "department_code must be an integer"}), 400
            
#         # Check if the manual code is already taken
#         existing_code = Department.query.filter_by(department_code=department_code).first()
#         if existing_code:
#             return jsonify({"error": f"Department code {department_code} is already in use"}), 409
#     # -----------------------------
        
#     new_dept = Department(
#         name=name,
#         department_code=department_code,
#         department_level=valid_level.value
#     )
    
#     try:
#         db.session.add(new_dept)
#         db.session.commit()
#         return jsonify({
#             "status": "success", 
#             "message": f"Department {name} created", 
#             "id": new_dept.id,
#             "department_code": new_dept.department_code
#         }), 201
#     except Exception as e:
#         db.session.rollback()
#         return jsonify({"error": str(e)}), 500


    
# @department_bp.route('/<string:department_id>/stock', methods=['GET'])
# @jwt_required
# def get_department_stock(department_id):
#     """View the live physical inventory currently sitting in a specific department"""
    
#     # 1. Verify the department exists
#     dept = Department.query.get(department_id)
#     if not dept:
#         return jsonify({"error": "Department not found"}), 404

#     # 2. Query the bridge table (The Physical Shelves)
#     stock_records = DepartmentStock.query.filter_by(department_id=department_id).all()
    
#     result = []
#     for record in stock_records:
#         # 3. Look up the item in the Master Catalog to get its name and unit
#         item = InternalProduct.query.get(record.item_id)
#         if item and record.quantity > 0: # Only show it if there is actual stock
#             result.append({
#                 "item_id": item.id,
#                 "item_name": item.name,
#                 "item_code": item.item_code,
#                 "category": item.category,
#                 "quantity_on_shelf": record.quantity,
#                 "unit_of_measure": item.unit_of_measure,
#                 "last_updated": record.last_updated
#             })
            
#     return jsonify({
#         "status": "success",
#         "department_name": dept.name,
#         "stock": result
#     }), 200
    

from flask import Blueprint, request, jsonify
from app import db
from app.models.department import Department, DeptLevel, DepartmentLevel
from app.models.item import DepartmentStock, InternalProduct
from app.models.user import User
from app.core.decorators import jwt_required

department_bp = Blueprint('departments', __name__)

@department_bp.route('/', methods=['GET', 'OPTIONS'], strict_slashes=False)
@jwt_required
def get_departments():
    if request.method == 'OPTIONS':
        return jsonify({}), 200
        
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

@department_bp.route('/', methods=['POST', 'OPTIONS'], strict_slashes=False)
@jwt_required
def create_department():
    if request.method == 'OPTIONS':
        return jsonify({}), 200
        
    data = request.get_json()
    name = data.get('name')
    department_code = data.get('department_code')
    level_int = data.get('department_level', 0)

    if not name:
        return jsonify({"error": "Department name is required"}), 400

    if not DepartmentLevel.query.filter_by(rank=level_int).first():
        return jsonify({"error": "Invalid department_level — it doesn't match any configured level."}), 400

    existing = Department.query.filter_by(name=name).first()
    if existing:
        return jsonify({"error": "Department already exists"}), 409
        
    if department_code is None or str(department_code).strip() == "":
        max_code = db.session.query(db.func.max(Department.department_code)).scalar()
        department_code = (max_code or 0) + 1
    else:
        try:
            department_code = int(department_code)
        except ValueError:
            return jsonify({"error": "department_code must be an integer"}), 400
            
        existing_code = Department.query.filter_by(department_code=department_code).first()
        if existing_code:
            return jsonify({"error": f"Department code {department_code} is already in use"}), 409
        
    new_dept = Department(
        name=name,
        department_code=department_code,
        department_level=level_int
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

@department_bp.route('/<string:department_id>', methods=['PUT', 'OPTIONS'], strict_slashes=False)
@jwt_required
def update_department(department_id):
    if request.method == 'OPTIONS':
        return jsonify({}), 200

    dept = Department.query.get(department_id)
    if not dept or not dept.is_active:
        return jsonify({"error": "Department not found"}), 404

    data = request.get_json(silent=True) or {}

    if 'name' in data:
        new_name = (data['name'] or '').strip()
        if not new_name:
            return jsonify({"error": "Department name is required"}), 400
        existing = Department.query.filter(Department.name == new_name, Department.id != department_id).first()
        if existing:
            return jsonify({"error": "Department already exists"}), 409
        dept.name = new_name

    if 'department_level' in data:
        level_int = data['department_level']
        if not DepartmentLevel.query.filter_by(rank=level_int).first():
            return jsonify({"error": "Invalid department_level — it doesn't match any configured level."}), 400
        dept.department_level = level_int

    if 'department_code' in data and str(data['department_code']).strip() != '':
        try:
            new_code = int(data['department_code'])
        except (TypeError, ValueError):
            return jsonify({"error": "department_code must be an integer"}), 400
        existing_code = Department.query.filter(Department.department_code == new_code, Department.id != department_id).first()
        if existing_code:
            return jsonify({"error": f"Department code {new_code} is already in use"}), 409
        dept.department_code = new_code

    try:
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        return jsonify({"error": str(e)}), 500

    return jsonify({
        "status": "success",
        "message": f"Department '{dept.name}' updated",
        "id": dept.id,
        "name": dept.name,
        "level": dept.department_level,
        "department_code": dept.department_code,
    }), 200


@department_bp.route('/<string:department_id>', methods=['DELETE', 'OPTIONS'], strict_slashes=False)
@jwt_required
def delete_department(department_id):
    if request.method == 'OPTIONS':
        return jsonify({}), 200

    dept = Department.query.get(department_id)
    if not dept or not dept.is_active:
        return jsonify({"error": "Department not found"}), 404

    users_in_dept = User.query.filter_by(department_id=department_id, is_active=True).count()
    if users_in_dept > 0:
        return jsonify({
            "error": f"Cannot delete '{dept.name}' — {users_in_dept} active user(s) are still assigned to it. Reassign them first."
        }), 409

    dept.is_active = 0
    try:
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        return jsonify({"error": str(e)}), 500

    return jsonify({"message": f"Department '{dept.name}' deleted"}), 200

@department_bp.route('/<string:department_id>/stock', methods=['GET', 'OPTIONS'], strict_slashes=False)
@jwt_required
def get_department_stock(department_id):
    if request.method == 'OPTIONS':
        return jsonify({}), 200
        
    dept = Department.query.get(department_id)
    if not dept:
        return jsonify({"error": "Department not found"}), 404

    stock_records = DepartmentStock.query.filter_by(department_id=department_id).all()
    
    result = []
    for record in stock_records:
        item = InternalProduct.query.get(record.item_id)
        if item and record.quantity > 0: 
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


# ==========================================
# HIERARCHY LEVELS — user-managed, not a fixed enum. The highest `rank`
# currently defined is treated as "final" (finished goods / dispatch)
# wherever the app used to check for the old fixed FINAL value.
# ==========================================

@department_bp.route('/levels', methods=['GET', 'OPTIONS'], strict_slashes=False)
@jwt_required
def get_department_levels():
    if request.method == 'OPTIONS':
        return jsonify({}), 200

    levels = DepartmentLevel.query.order_by(DepartmentLevel.rank.asc()).all()
    max_rank = max((l.rank for l in levels), default=None)

    return jsonify({
        "status": "success",
        "data": [{
            "id": l.id,
            "name": l.name,
            "rank": l.rank,
            "is_final": l.rank == max_rank,
        } for l in levels]
    }), 200


@department_bp.route('/levels', methods=['POST', 'OPTIONS'], strict_slashes=False)
@jwt_required
def create_department_level():
    if request.method == 'OPTIONS':
        return jsonify({}), 200

    data = request.get_json(silent=True) or {}
    name = (data.get('name') or '').strip()
    rank = data.get('rank')

    if not name:
        return jsonify({"error": "Level name is required"}), 400
    if rank is None:
        return jsonify({"error": "Level rank is required"}), 400
    try:
        rank = int(rank)
    except (TypeError, ValueError):
        return jsonify({"error": "rank must be an integer"}), 400

    if DepartmentLevel.query.filter_by(name=name).first():
        return jsonify({"error": f"Level '{name}' already exists"}), 409
    if DepartmentLevel.query.filter_by(rank=rank).first():
        return jsonify({"error": f"Rank {rank} is already used by another level"}), 409

    new_level = DepartmentLevel(name=name, rank=rank)
    try:
        db.session.add(new_level)
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        return jsonify({"error": str(e)}), 500

    return jsonify({"status": "success", "message": f"Level '{name}' created", "id": new_level.id}), 201


@department_bp.route('/levels/<int:level_id>', methods=['PUT', 'OPTIONS'], strict_slashes=False)
@jwt_required
def update_department_level(level_id):
    if request.method == 'OPTIONS':
        return jsonify({}), 200

    level = DepartmentLevel.query.get(level_id)
    if not level:
        return jsonify({"error": "Level not found"}), 404

    data = request.get_json(silent=True) or {}

    if 'name' in data:
        new_name = (data['name'] or '').strip()
        if not new_name:
            return jsonify({"error": "Level name is required"}), 400
        existing = DepartmentLevel.query.filter(DepartmentLevel.name == new_name, DepartmentLevel.id != level_id).first()
        if existing:
            return jsonify({"error": f"Level '{new_name}' already exists"}), 409
        level.name = new_name

    if 'rank' in data:
        try:
            new_rank = int(data['rank'])
        except (TypeError, ValueError):
            return jsonify({"error": "rank must be an integer"}), 400
        existing_rank = DepartmentLevel.query.filter(DepartmentLevel.rank == new_rank, DepartmentLevel.id != level_id).first()
        if existing_rank:
            return jsonify({"error": f"Rank {new_rank} is already used by another level"}), 409
        level.rank = new_rank

    try:
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        return jsonify({"error": str(e)}), 500

    return jsonify({"status": "success", "message": f"Level '{level.name}' updated"}), 200


@department_bp.route('/levels/<int:level_id>', methods=['DELETE', 'OPTIONS'], strict_slashes=False)
@jwt_required
def delete_department_level(level_id):
    if request.method == 'OPTIONS':
        return jsonify({}), 200

    level = DepartmentLevel.query.get(level_id)
    if not level:
        return jsonify({"error": "Level not found"}), 404

    depts_using_it = Department.query.filter_by(department_level=level.rank, is_active=1).count()
    if depts_using_it > 0:
        return jsonify({
            "error": f"Cannot delete '{level.name}' — {depts_using_it} department(s) are still on this level. Move them first."
        }), 409

    db.session.delete(level)
    try:
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        return jsonify({"error": str(e)}), 500

    return jsonify({"status": "success", "message": f"Level '{level.name}' deleted"}), 200