from flask import Blueprint, jsonify, request, g
from app import db
from app.models.user import User, Role
from app.models.department import DepartmentRoute
from app.models.department import Department
from app.models.user import Permission
# Assuming you have a jwt_required decorator, import it here
from app.core.decorators import jwt_required, permission_required
from app.core.utils import normalize_phone_number
from app.models.system_setting import SystemSetting, DEFAULT_SETTINGS
from app.models.audit_log import AuditLog
from app.core.audit import log_audit

admin_bp = Blueprint('admin', __name__, url_prefix='/api/admin')


from app.models.user import AppModule # Make sure AppModule is imported at the top!


@admin_bp.route('/roles', methods=['GET', 'OPTIONS'], strict_slashes=False)
@jwt_required
@permission_required('admin_access')
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
@permission_required('admin_access')
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

    before_names = sorted(p.name for p in role.permissions)

    # SQLAlchemy makes updating many-to-many relationships incredibly easy
    # Just overwrite the array and commit!
    role.permissions = new_permissions

    log_audit(
        'role.permissions.update', 'role', role_id,
        payload_before={"role": role.name, "permissions": before_names},
        payload_after={"role": role.name, "permissions": sorted(p.name for p in new_permissions)},
    )

    try:
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        return jsonify({"error": str(e)}), 500

    return jsonify({"message": f"Permissions updated for {role.name}"}), 200

@admin_bp.route('/roles/<int:role_id>', methods=['DELETE', 'OPTIONS'], strict_slashes=False)
@jwt_required
@permission_required('admin_access')
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

    log_audit(
        'role.delete', 'role', role_id,
        payload_before={"name": role.name, "permissions": sorted(p.name for p in role.permissions)},
    )

    db.session.delete(role)
    try:
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        return jsonify({"error": str(e)}), 500

    return jsonify({"message": f"Role '{role.name}' deleted"}), 200

@admin_bp.route('/modules', methods=['GET'])
@jwt_required
# Deliberately NOT permission_required('admin_access') — every authenticated
# user's sidebar calls this (see (protected)/_layout.tsx and
# components/common/RequireModuleAccess.tsx) to know which routes are gated
# at all, so it can tell "not configured" apart from "configured but denied
# to you". It only returns module metadata (name/route/icon/description),
# not anything sensitive like role assignments.
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
@permission_required('admin_access')
def toggle_module(module_id):
    """Toggle a module on or off for the entire system"""
    module = AppModule.query.get(module_id)
    if not module:
        return jsonify({"message": "Module not found"}), 404

    # Flip the boolean
    was_active = module.is_active
    module.is_active = not module.is_active

    log_audit(
        'module.toggle', 'app_module', module_id,
        payload_before={"name": module.name, "is_active": was_active},
        payload_after={"name": module.name, "is_active": module.is_active},
    )

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
@permission_required('admin_access')
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
@permission_required('admin_access')
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
@permission_required('admin_access')
def add_user():
    if request.method == 'OPTIONS':
        return jsonify({}), 200
        
    data = request.get_json(silent=True) or {}
    phone = normalize_phone_number(data.get('phone'))
    name = data.get('name')
    role_id = data.get('role_id')

    if not phone:
        return jsonify({"message": "Phone number is required"}), 400

    # FORCE A ROLE TO BE SELECTED. If none is passed, reject it.
    if not role_id:
        return jsonify({"message": "A role must be assigned to new users."}), 400

    # If this number already self-registered via Firebase (e.g. they tried
    # logging in before an admin got to them, landing on PENDING), assign
    # the role to that existing account instead of rejecting — otherwise
    # the number the admin "added" here and the number Firebase actually
    # logs them in as never match, and they're stuck on "awaiting approval"
    # forever even though a role was assigned.
    existing_user = User.query.filter_by(phone_number=phone).first()
    if existing_user:
        before_role = existing_user.role_data.name if existing_user.role_data else None
        existing_user.role_id = role_id
        if name:
            existing_user.full_name = name
        after_role = existing_user.role_data.name if existing_user.role_data else None
        log_audit(
            'user.role_assign', 'user', existing_user.id,
            payload_before={"phone": phone, "role": before_role},
            payload_after={"phone": phone, "role": after_role},
        )
        try:
            db.session.commit()
            return jsonify({"message": "Existing account found for this number — role assigned"}), 200
        except Exception as e:
            db.session.rollback()
            return jsonify({"error": str(e)}), 500

    new_user = User(
        phone_number=phone,
        full_name=name,
        role_id=role_id
    )
    db.session.add(new_user)
    db.session.flush()
    log_audit(
        'user.create', 'user', new_user.id,
        payload_after={"phone": phone, "name": name, "role": new_user.role_data.name if new_user.role_data else None},
    )
    try:
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        return jsonify({"error": str(e)}), 500

    return jsonify({"message": "User added successfully"}), 201


@admin_bp.route('/users/<user_id>', methods=['PUT', 'OPTIONS'], strict_slashes=False)
@jwt_required
@permission_required('admin_access')
def update_user_details(user_id):
    """Update a user's name, phone, or role"""
    if request.method == 'OPTIONS':
        return jsonify({}), 200
        
    data = request.get_json(silent=True) or {}
    
    user = User.query.get(user_id)
    if not user:
        return jsonify({"message": "User not found"}), 404

    before = {
        "name": user.full_name,
        "phone": user.phone_number,
        "role": user.role_data.name if user.role_data else None,
    }

    if 'role_id' in data and data['role_id']:
        user.role_id = data['role_id']
    if 'name' in data:
        user.full_name = data['name']
    if 'phone' in data:
        user.phone_number = normalize_phone_number(data['phone'])

    after = {
        "name": user.full_name,
        "phone": user.phone_number,
        "role": user.role_data.name if user.role_data else None,
    }
    if after != before:
        log_audit('user.update', 'user', user.id, payload_before=before, payload_after=after)

    try:
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        return jsonify({"error": str(e)}), 500

    return jsonify({"message": "User updated successfully"}), 200

@admin_bp.route('/routing', methods=['GET', 'OPTIONS'], strict_slashes=False)
@jwt_required
@permission_required('admin_access')
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
@permission_required('admin_access')
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
@permission_required('admin_access')
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


# ==========================================
# SYSTEM SETTINGS — admin-configurable key/value store (see
# models/system_setting.py). Currently just default_wastage_percent, but
# built to hold more without another migration.
# ==========================================

@admin_bp.route('/settings', methods=['GET', 'OPTIONS'], strict_slashes=False)
@jwt_required
@permission_required('admin_access')
def list_settings():
    if request.method == 'OPTIONS':
        return jsonify({}), 200

    existing = {s.key: s for s in SystemSetting.query.all()}
    result = []
    # Walk the known-settings catalog (not just whatever rows exist) so a
    # setting nobody has touched yet still shows up with its default and
    # description instead of being invisible.
    for key, meta in DEFAULT_SETTINGS.items():
        row = existing.get(key)
        result.append({
            "key": key,
            "value": row.value if row else meta['value'],
            "description": meta['description'],
            "updated_at": row.updated_at.isoformat() if row and row.updated_at else None,
            "updated_by": row.user.full_name if row and row.updated_by and row.user else None,
        })
    return jsonify({"status": "success", "data": result}), 200


@admin_bp.route('/settings/<key>', methods=['PUT', 'OPTIONS'], strict_slashes=False)
@jwt_required
@permission_required('admin_access')
def update_setting(key):
    if request.method == 'OPTIONS':
        return jsonify({}), 200

    if key not in DEFAULT_SETTINGS:
        return jsonify({"error": f"Unknown setting '{key}'"}), 404

    data = request.get_json(silent=True) or {}
    if 'value' not in data:
        return jsonify({"error": "value is required"}), 400
    new_value = str(data['value'])

    if key == 'default_wastage_percent':
        try:
            parsed = float(new_value)
            if parsed < 0 or parsed > 100:
                raise ValueError()
        except ValueError:
            return jsonify({"error": "default_wastage_percent must be a number between 0 and 100"}), 400

    setting = SystemSetting.query.get(key)
    before_value = setting.value if setting else DEFAULT_SETTINGS[key]['value']
    if not setting:
        setting = SystemSetting(key=key)
        db.session.add(setting)

    setting.value = new_value
    setting.updated_by = g.current_user.id

    log_audit(
        'settings.update', 'system_setting', key,
        payload_before={"value": before_value},
        payload_after={"value": new_value},
    )

    try:
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        return jsonify({"error": str(e)}), 500

    return jsonify({"status": "success", "message": f"'{key}' updated", "value": new_value}), 200


# ==========================================
# AUDIT LOGS — read-only, immutable. Supports the filters/sort the
# Transaction History-style pages already use elsewhere in the app; the
# frontend layers its usual useSortable/useSearch on top of whatever this
# returns.
# ==========================================

@admin_bp.route('/audit-logs', methods=['GET', 'OPTIONS'], strict_slashes=False)
@jwt_required
@permission_required('admin_access')
def list_audit_logs():
    if request.method == 'OPTIONS':
        return jsonify({}), 200

    query = AuditLog.query

    action = request.args.get('action')
    if action:
        query = query.filter(AuditLog.action == action)

    resource_type = request.args.get('resource_type')
    if resource_type:
        query = query.filter(AuditLog.resource_type == resource_type)

    user_id = request.args.get('user_id')
    if user_id:
        query = query.filter(AuditLog.user_id == user_id)

    date_from = request.args.get('date_from')  # YYYY-MM-DD
    if date_from:
        query = query.filter(AuditLog.created_at >= date_from)
    date_to = request.args.get('date_to')  # YYYY-MM-DD
    if date_to:
        query = query.filter(AuditLog.created_at < f"{date_to} 23:59:59")

    limit = min(request.args.get('limit', 500, type=int) or 500, 2000)

    logs = query.order_by(AuditLog.created_at.desc()).limit(limit).all()

    return jsonify({
        "status": "success",
        "data": [{
            "id": l.id,
            "user_id": l.user_id,
            "user_label": l.user_label,
            "action": l.action,
            "resource_type": l.resource_type,
            "resource_id": l.resource_id,
            "payload_before": l.payload_before,
            "payload_after": l.payload_after,
            "ip_address": l.ip_address,
            "created_at": l.created_at.isoformat() if l.created_at else None,
        } for l in logs],
    }), 200



