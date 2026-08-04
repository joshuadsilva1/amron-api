from flask import Blueprint, request, jsonify
from app import db
from app.models.rack import Rack
from app.core.decorators import jwt_required

racks_bp = Blueprint('racks', __name__)

@racks_bp.route('/', methods=['GET', 'OPTIONS'], strict_slashes=False)
@jwt_required
def get_racks():
    if request.method == 'OPTIONS':
        return jsonify({}), 200
        
    dept_id = request.args.get('department_id')
    query = Rack.query.filter_by(is_active=1)
    
    if dept_id:
        query = query.filter_by(department_id=dept_id)
        
    racks = query.all()
    
    result = [{
        "id": r.id,
        "rack_code": r.rack_code,
        "department_id": r.department_id,
        "department_name": r.department.name if r.department else "Unknown",
        "description": r.description,
        "max_capacity_kg": r.max_capacity_kg
    } for r in racks]
    
    return jsonify({"status": "success", "data": result}), 200

@racks_bp.route('/', methods=['POST', 'OPTIONS'], strict_slashes=False)
@jwt_required
def create_rack():
    if request.method == 'OPTIONS':
        return jsonify({}), 200
        
    data = request.get_json(silent=True) or {}
    
    rack_code = data.get('rack_code')
    department_id = data.get('department_id')
    
    if not rack_code or not department_id:
        return jsonify({"error": "Rack code and department are required"}), 400
        
    if Rack.query.filter_by(rack_code=rack_code).first():
        return jsonify({"error": f"Rack code {rack_code} already exists"}), 409
        
    new_rack = Rack(
        rack_code=rack_code,
        department_id=department_id,
        description=data.get('description', ''),
        max_capacity_kg=float(data.get('max_capacity_kg', 0.0) if data.get('max_capacity_kg') else 0.0)
    )
    
    try:
        db.session.add(new_rack)
        db.session.commit()
        return jsonify({"status": "success", "message": "Rack created", "id": str(new_rack.id)}), 201
    except Exception as e:
        db.session.rollback()
        return jsonify({"error": str(e)}), 500

@racks_bp.route('/<rack_id>', methods=['PUT', 'OPTIONS'], strict_slashes=False)
@jwt_required
def update_rack(rack_id):
    if request.method == 'OPTIONS':
        return jsonify({}), 200
        
    rack = Rack.query.get(rack_id)
    if not rack:
        return jsonify({"error": "Rack not found"}), 404
        
    data = request.get_json(silent=True) or {}
    
    if 'rack_code' in data and data['rack_code'] != rack.rack_code:
        if Rack.query.filter_by(rack_code=data['rack_code']).first():
            return jsonify({"error": f"Rack code {data['rack_code']} is already taken."}), 409
            
    if 'rack_code' in data: rack.rack_code = data['rack_code']
    if 'department_id' in data: rack.department_id = data['department_id']
    if 'description' in data: rack.description = data['description']
    if 'max_capacity_kg' in data: rack.max_capacity_kg = float(data['max_capacity_kg'] or 0.0)
        
    try:
        db.session.commit()
        return jsonify({"status": "success", "message": "Rack updated"}), 200
    except Exception as e:
        db.session.rollback()
        return jsonify({"error": str(e)}), 500