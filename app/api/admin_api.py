from flask import Blueprint, jsonify, request
from app import db
from app.models.user import User, Role
from app.models.department import DepartmentRoute
from app.models.department import Department
from app.models.user import Permission
# Assuming you have a jwt_required decorator, import it here
from app.core.decorators import jwt_required 

admin_bp = Blueprint('admin', __name__, url_prefix='/api/admin')


from app.models.user import AppModule # Make sure AppModule is imported at the top!


@admin_bp.route('/roles', methods=['GET', 'OPTIONS'], strict_slashes=False)
@jwt_required
def get_roles_and_permissions():
    if request.method == 'OPTIONS':
        return jsonify({}), 200
        
    # Fetch all roles
    roles = Role.query.all()
    roles_data = []
    for r in roles:
        roles_data.append({
            "id": r.id,
            "name": r.name,
            "description": r.description,
            # Return an array of permission IDs this role currently has
            "permission_ids": [p.id for p in r.permissions] 
        })
        
    # Fetch the master list of all available permissions
    all_perms = Permission.query.all()
    perms_data = [{"id": p.id, "name": p.name, "description": p.description} for p in all_perms]
    
    return jsonify({
        "roles": roles_data,
        "all_permissions": perms_data
    }), 200


@admin_bp.route('/roles/<int:role_id>/permissions', methods=['PUT', 'OPTIONS'], strict_slashes=False)
@jwt_required
def update_role_permissions(role_id):
    if request.method == 'OPTIONS':
        return jsonify({}), 200
        
    role = Role.query.get(role_id)
    if not role:
        return jsonify({"message": "Role not found"}), 404
        
    data = request.get_json(silent=True) or {}
    new_permission_ids = data.get('permission_ids', [])
    
    # Fetch the actual Permission objects based on the provided IDs
    new_permissions = Permission.query.filter(Permission.id.in_(new_permission_ids)).all()
    
    # SQLAlchemy makes updating many-to-many relationships incredibly easy
    # Just overwrite the array and commit!
    role.permissions = new_permissions
    try:
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        return jsonify({"error": str(e)}), 500

    return jsonify({"message": f"Permissions updated for {role.name}"}), 200

@admin_bp.route('/roles/<int:role_id>', methods=['DELETE', 'OPTIONS'], strict_slashes=False)
@jwt_required
def delete_role(role_id):
    if request.method == 'OPTIONS':
        return jsonify({}), 200

    role = Role.query.get(role_id)
    if not role:
        return jsonify({"message": "Role not found"}), 404

    users_with_role = User.query.filter_by(role_id=role_id).count()
    if users_with_role > 0:
        return jsonify({
            "error": f"Cannot delete '{role.name}' — {users_with_role} user(s) are still assigned to it. Reassign them first."
        }), 409

    db.session.delete(role)
    try:
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        return jsonify({"error": str(e)}), 500

    return jsonify({"message": f"Role '{role.name}' deleted"}), 200

@admin_bp.route('/modules', methods=['GET'])
@jwt_required
def get_all_modules():
    """Fetch all dynamic app modules"""
    modules = AppModule.query.all()
    
    modules_data = []
    for m in modules:
        modules_data.append({
            "id": m.id,
            "name": m.name,
            "description": m.description,
            "icon": m.icon,
            "is_active": m.is_active,
            "route": m.route
        })
        
    return jsonify({"modules": modules_data}), 200

@admin_bp.route('/modules/<int:module_id>/toggle', methods=['PUT'])
@jwt_required
def toggle_module(module_id):
    """Toggle a module on or off for the entire system"""
    module = AppModule.query.get(module_id)
    if not module:
        return jsonify({"message": "Module not found"}), 404
        
    # Flip the boolean
    module.is_active = not module.is_active
    try:
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        return jsonify({"error": str(e)}), 500

    return jsonify({
        "message": f"Module '{module.name}' is now {'Active' if module.is_active else 'Disabled'}",
        "is_active": module.is_active
    }), 200


@admin_bp.route('/routing/sync', methods=['POST', 'OPTIONS'], strict_slashes=False)
@jwt_required
def sync_routing_board():
    """Sync the entire routing board state at once"""
    
    # 1. CATCH THE PREFLIGHT AND RETURN 200 OK IMMEDIATELY
    if request.method == 'OPTIONS':
        return jsonify({}), 200
        
    # 2. Only process JSON if it's the actual POST request
    # Using request.get_json(silent=True) prevents 415 crashes if the body is empty
    data = request.get_json(silent=True) or {}
    
    dept_data = data.get('departments', [])
    route_data = data.get('routes', [])
    
    # 3. Update all Department Levels based on where they were dragged
    for d_data in dept_data:
        dept = Department.query.get(d_data.get('id'))
        if dept and 'level' in d_data:
            dept.department_level = d_data['level']

    # 4. Wipe the old routing slate clean
    DepartmentRoute.query.delete()

    # 5. Insert the newly drawn routes
    for r_data in route_data:
        from_id = r_data.get('from_department_id')
        to_id = r_data.get('to_department_id')
        if not from_id or not to_id:
            db.session.rollback()
            return jsonify({"error": "Each route needs a from_department_id and to_department_id"}), 400
        new_route = DepartmentRoute(
            from_department_id=from_id,
            to_department_id=to_id
        )
        db.session.add(new_route)

    try:
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        return jsonify({"error": str(e)}), 500

    return jsonify({"message": "Board synced successfully!"}), 200



@admin_bp.route('/users', methods=['GET'])
@jwt_required
def get_all_users():
    """Fetch all users and their assigned roles"""
    users = User.query.all()
    roles = Role.query.all()
    
    # Send all available roles so the frontend can populate the dropdown
    roles_data = [{"id": r.id, "name": r.name} for r in roles]
    
    users_data = []
    for u in users:
        users_data.append({
            "id": u.id,
            "phone": u.phone_number,
            "name": u.full_name or "Unknown",
            "role_id": u.role_id,
            "role_name": u.role_data.name if u.role_data else "Unassigned",
            "department_id": u.department_id
        })
        
    return jsonify({
        "users": users_data,
        "roles": roles_data
    }), 200



@admin_bp.route('/users', methods=['POST', 'OPTIONS'], strict_slashes=False)
@jwt_required
def add_user():
    if request.method == 'OPTIONS':
        return jsonify({}), 200
        
    data = request.get_json(silent=True) or {}
    phone = data.get('phone')
    name = data.get('name')
    role_id = data.get('role_id')
    
    if not phone:
        return jsonify({"message": "Phone number is required"}), 400
        
    # FORCE A ROLE TO BE SELECTED. If none is passed, reject it.
    if not role_id:
        return jsonify({"message": "A role must be assigned to new users."}), 400
        
    existing_user = User.query.filter_by(phone_number=phone).first()
    if existing_user:
        return jsonify({"message": "A user with this phone number already exists"}), 400
        
    new_user = User(
        phone_number=phone,
        full_name=name,
        role_id=role_id
    )
    db.session.add(new_user)
    try:
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        return jsonify({"error": str(e)}), 500

    return jsonify({"message": "User added successfully"}), 201


@admin_bp.route('/users/<user_id>', methods=['PUT', 'OPTIONS'], strict_slashes=False)
@jwt_required
def update_user_details(user_id):
    """Update a user's name, phone, or role"""
    if request.method == 'OPTIONS':
        return jsonify({}), 200
        
    data = request.get_json(silent=True) or {}
    
    user = User.query.get(user_id)
    if not user:
        return jsonify({"message": "User not found"}), 404
        
    if 'role_id' in data and data['role_id']:
        user.role_id = data['role_id']
    if 'name' in data:
        user.full_name = data['name']
    if 'phone' in data:
        user.phone_number = data['phone']

    try:
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        return jsonify({"error": str(e)}), 500

    return jsonify({"message": "User updated successfully"}), 200

@admin_bp.route('/routing', methods=['GET', 'OPTIONS'], strict_slashes=False)
@jwt_required
def get_all_routes():
    """Fetch all active department connections"""
    routes = DepartmentRoute.query.all()
    
    routes_data = []
    for r in routes:
        routes_data.append({
            "id": str(r.id),
            "fromId": str(r.from_department_id),
            "toId": str(r.to_department_id)
        })
        
    return jsonify({"data": routes_data}), 200

@admin_bp.route('/routing', methods=['POST', 'OPTIONS'], strict_slashes=False)
@jwt_required
def create_route():
    """Create a new connection between two departments"""
    data = request.json
    from_id = data.get('from_department_id')
    to_id = data.get('to_department_id')
    
    if not from_id or not to_id:
        return jsonify({"message": "Both source and destination department IDs are required"}), 400
        
    # Prevent duplicate routes
    existing = DepartmentRoute.query.filter_by(from_department_id=from_id, to_department_id=to_id).first()
    if existing:
        return jsonify({"message": "This route already exists"}), 400
        
    new_route = DepartmentRoute(
        from_department_id=from_id, 
        to_department_id=to_id
    )
    
    db.session.add(new_route)
    try:
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        return jsonify({"error": str(e)}), 500

    return jsonify({
        "message": "Route saved successfully",
        "id": str(new_route.id)
    }), 201

@admin_bp.route('/routing/<route_id>', methods=['DELETE', 'OPTIONS'], strict_slashes=False)
@jwt_required
def delete_route(route_id):
    """Remove a connection between departments"""
    route = DepartmentRoute.query.get(route_id)
    if not route:
        return jsonify({"message": "Route not found"}), 404
        
    db.session.delete(route)
    try:
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        return jsonify({"error": str(e)}), 500

    return jsonify({"message": "Route removed successfully"}), 200



