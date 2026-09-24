import os
import uuid
from flask import Blueprint, jsonify, request, g
from werkzeug.utils import secure_filename
from app import db
from app.models.user import User, Role
from app.models.department import DepartmentRoute
from app.models.department import Department
from app.models.user import Permission
# Assuming you have a jwt_required decorator, import it here
from app.core.decorators import jwt_required, permission_required
from app.core.utils import normalize_phone_number
from app.core.storage import upload_file
from app.models.system_setting import SystemSetting, DEFAULT_SETTINGS
from app.models.audit_log import AuditLog
from app.models.nav_route import NavRoute
from app.core.audit import log_audit
import re

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
            "icon_image_url": m.icon_image_url,
            "is_active": m.is_active,
            "route": m.route,
            "permission_id": m.permission_id,
            "permission_name": m.required_permission.name if m.required_permission else None,
        })

    return jsonify({"modules": modules_data}), 200


@admin_bp.route('/modules', methods=['POST', 'OPTIONS'], strict_slashes=False)
@jwt_required
@permission_required('admin_access')
def create_module():
    """Creates a new nav-gating module: a (route, required permission) pair.
    See utils/moduleAccess.ts on the frontend for how this is used — a
    route with no module row at all stays visible to everyone, so this is
    how an Admin opts a route INTO being gated."""
    if request.method == 'OPTIONS':
        return jsonify({}), 200

    data = request.get_json(silent=True) or {}
    name = (data.get('name') or '').strip()
    route = (data.get('route') or '').strip()
    permission_id = data.get('permission_id')
    icon = (data.get('icon') or 'grid').strip() or 'grid'
    icon_image_url = (data.get('icon_image_url') or '').strip() or None
    description = (data.get('description') or '').strip() or None

    if not name or not route or not permission_id:
        return jsonify({"message": "name, route, and permission_id are required"}), 400

    if not route.startswith('/(protected)/'):
        return jsonify({"message": "route should look like /(protected)/manager/items"}), 400

    if not Permission.query.get(permission_id):
        return jsonify({"message": "That permission doesn't exist"}), 404

    if AppModule.query.filter_by(route=route).first():
        return jsonify({"message": f"A module already exists for route '{route}'"}), 409

    module = AppModule(
        name=name, route=route, icon=icon, icon_image_url=icon_image_url, description=description,
        permission_id=permission_id, is_active=True,
    )
    db.session.add(module)
    db.session.flush()

    log_audit(
        'module.create', 'app_module', module.id,
        payload_after={"name": name, "route": route, "permission_id": permission_id},
    )

    try:
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        return jsonify({"error": str(e)}), 500

    return jsonify({"status": "success", "message": f"Module '{name}' created", "id": module.id}), 201


@admin_bp.route('/modules/<int:module_id>', methods=['PUT', 'OPTIONS'], strict_slashes=False)
@jwt_required
@permission_required('admin_access')
def update_module(module_id):
    """Full edit — distinct from /toggle (which only flips is_active)."""
    if request.method == 'OPTIONS':
        return jsonify({}), 200

    module = AppModule.query.get(module_id)
    if not module:
        return jsonify({"message": "Module not found"}), 404

    data = request.get_json(silent=True) or {}
    before = {
        "name": module.name, "route": module.route, "icon": module.icon,
        "icon_image_url": module.icon_image_url, "description": module.description,
        "permission_id": module.permission_id,
    }

    if 'name' in data:
        new_name = (data['name'] or '').strip()
        if not new_name:
            return jsonify({"message": "name can't be blank"}), 400
        module.name = new_name
    if 'route' in data:
        new_route = (data['route'] or '').strip()
        if not new_route.startswith('/(protected)/'):
            return jsonify({"message": "route should look like /(protected)/manager/items"}), 400
        existing = AppModule.query.filter(AppModule.route == new_route, AppModule.id != module_id).first()
        if existing:
            return jsonify({"message": f"A module already exists for route '{new_route}'"}), 409
        module.route = new_route
    if 'permission_id' in data:
        if not Permission.query.get(data['permission_id']):
            return jsonify({"message": "That permission doesn't exist"}), 404
        module.permission_id = data['permission_id']
    if 'icon' in data:
        module.icon = (data['icon'] or 'grid').strip() or 'grid'
    if 'icon_image_url' in data:
        module.icon_image_url = (data['icon_image_url'] or '').strip() or None
    if 'description' in data:
        module.description = (data['description'] or '').strip() or None

    log_audit(
        'module.update', 'app_module', module_id,
        payload_before=before,
        payload_after={
            "name": module.name, "route": module.route, "icon": module.icon,
            "icon_image_url": module.icon_image_url, "description": module.description,
            "permission_id": module.permission_id,
        },
    )

    try:
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        return jsonify({"error": str(e)}), 500

    return jsonify({"status": "success", "message": f"Module '{module.name}' updated"}), 200


ALLOWED_ICON_EXT = {'.png'}


@admin_bp.route('/modules/icon-upload', methods=['POST', 'OPTIONS'], strict_slashes=False)
@jwt_required
@permission_required('admin_access')
def upload_module_icon():
    """Uploads a custom PNG to use as a module's icon in place of a named
    Feather icon. Returns the public URL to send back as icon_image_url on
    create/update — this endpoint doesn't touch any module row itself."""
    if request.method == 'OPTIONS':
        return jsonify({}), 200

    if 'file' not in request.files:
        return jsonify({"error": "No file uploaded. Expected multipart/form-data with a 'file' field."}), 400

    uploaded_file = request.files['file']
    if not uploaded_file or uploaded_file.filename == '':
        return jsonify({"error": "No file uploaded."}), 400

    ext = os.path.splitext(uploaded_file.filename)[1].lower()
    if ext not in ALLOWED_ICON_EXT:
        return jsonify({"error": "Only .png icons are supported."}), 400

    filename = secure_filename(f"{uuid.uuid4().hex}{ext}")
    url = upload_file(uploaded_file, 'module_icons', filename)

    return jsonify({"status": "success", "url": url}), 200


@admin_bp.route('/modules/<int:module_id>', methods=['DELETE', 'OPTIONS'], strict_slashes=False)
@jwt_required
@permission_required('admin_access')
def delete_module(module_id):
    if request.method == 'OPTIONS':
        return jsonify({}), 200

    module = AppModule.query.get(module_id)
    if not module:
        return jsonify({"message": "Module not found"}), 404

    log_audit(
        'module.delete', 'app_module', module_id,
        payload_before={"name": module.name, "route": module.route},
    )

    db.session.delete(module)
    try:
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        return jsonify({"error": str(e)}), 500

    return jsonify({"status": "success", "message": f"Module '{module.name}' deleted"}), 200


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


# ==========================================
# NAV ROUTES — human-friendly labels for frontend route paths (e.g.
# "/(protected)/admin" -> "Admin Page"), so route pickers elsewhere in the
# admin UI (AppModule's route field) show a name instead of a raw path.
# Unrelated to DepartmentRoute / "Routing Editor" (physical material
# handoff routing) despite the shared word.
# ==========================================

@admin_bp.route('/nav-routes', methods=['GET', 'OPTIONS'], strict_slashes=False)
@jwt_required
@permission_required('admin_access')
def list_nav_routes():
    if request.method == 'OPTIONS':
        return jsonify({}), 200
    routes = NavRoute.query.order_by(NavRoute.label).all()
    return jsonify({
        "status": "success",
        "data": [{"id": r.id, "path": r.path, "label": r.label, "description": r.description} for r in routes],
    }), 200


@admin_bp.route('/nav-routes', methods=['POST', 'OPTIONS'], strict_slashes=False)
@jwt_required
@permission_required('admin_access')
def create_nav_route():
    if request.method == 'OPTIONS':
        return jsonify({}), 200

    data = request.get_json(silent=True) or {}
    path = (data.get('path') or '').strip()
    label = (data.get('label') or '').strip()
    description = (data.get('description') or '').strip() or None

    if not path or not label:
        return jsonify({"message": "path and label are required"}), 400
    if not path.startswith('/'):
        return jsonify({"message": "path should look like /(protected)/manager/items"}), 400
    if NavRoute.query.filter_by(path=path).first():
        return jsonify({"message": f"'{path}' already has a label"}), 409

    route = NavRoute(path=path, label=label, description=description)
    db.session.add(route)
    db.session.flush()
    log_audit('nav_route.create', 'nav_route', route.id, payload_after={"path": path, "label": label})

    try:
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        return jsonify({"error": str(e)}), 500

    return jsonify({"status": "success", "message": f"'{label}' added", "id": route.id}), 201


@admin_bp.route('/nav-routes/<int:route_id>', methods=['PUT', 'OPTIONS'], strict_slashes=False)
@jwt_required
@permission_required('admin_access')
def update_nav_route(route_id):
    if request.method == 'OPTIONS':
        return jsonify({}), 200

    route = NavRoute.query.get(route_id)
    if not route:
        return jsonify({"message": "Route not found"}), 404

    data = request.get_json(silent=True) or {}
    before = {"path": route.path, "label": route.label, "description": route.description}

    if 'label' in data:
        new_label = (data['label'] or '').strip()
        if not new_label:
            return jsonify({"message": "label can't be blank"}), 400
        route.label = new_label
    if 'description' in data:
        route.description = (data['description'] or '').strip() or None
    if 'path' in data:
        new_path = (data['path'] or '').strip()
        if not new_path.startswith('/'):
            return jsonify({"message": "path should look like /(protected)/manager/items"}), 400
        existing = NavRoute.query.filter(NavRoute.path == new_path, NavRoute.id != route_id).first()
        if existing:
            return jsonify({"message": f"'{new_path}' already has a label"}), 409
        route.path = new_path

    log_audit(
        'nav_route.update', 'nav_route', route_id,
        payload_before=before,
        payload_after={"path": route.path, "label": route.label, "description": route.description},
    )

    try:
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        return jsonify({"error": str(e)}), 500

    return jsonify({"status": "success", "message": f"'{route.label}' updated"}), 200


@admin_bp.route('/nav-routes/<int:route_id>', methods=['DELETE', 'OPTIONS'], strict_slashes=False)
@jwt_required
@permission_required('admin_access')
def delete_nav_route(route_id):
    if request.method == 'OPTIONS':
        return jsonify({}), 200

    route = NavRoute.query.get(route_id)
    if not route:
        return jsonify({"message": "Route not found"}), 404

    if AppModule.query.filter_by(route=route.path).first():
        return jsonify({
            "message": f"'{route.label}' is used by a module — remove or repoint that module first."
        }), 409

    log_audit('nav_route.delete', 'nav_route', route_id, payload_before={"path": route.path, "label": route.label})

    db.session.delete(route)
    try:
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        return jsonify({"error": str(e)}), 500

    return jsonify({"status": "success", "message": f"'{route.label}' deleted"}), 200


# ==========================================
# PERMISSIONS — the building blocks Roles are made of (see admin_api's
# roles endpoints above) and that Modules gate a route behind. A
# permission's `name` is what `@permission_required('name')` decorators
# check for literally throughout the backend, so renaming one after the
# fact would silently break enforcement with no code-level trace — name is
# therefore immutable once created; only its description can be edited.
# ==========================================

PERMISSION_NAME_RE = re.compile(r'^[a-z][a-z0-9_]*$')


@admin_bp.route('/permissions', methods=['GET', 'OPTIONS'], strict_slashes=False)
@jwt_required
@permission_required('admin_access')
def list_permissions():
    if request.method == 'OPTIONS':
        return jsonify({}), 200
    perms = Permission.query.order_by(Permission.name).all()
    return jsonify({
        "status": "success",
        "data": [{
            "id": p.id,
            "name": p.name,
            "description": p.description,
            "role_count": len(p.roles),
        } for p in perms],
    }), 200


@admin_bp.route('/permissions', methods=['POST', 'OPTIONS'], strict_slashes=False)
@jwt_required
@permission_required('admin_access')
def create_permission():
    if request.method == 'OPTIONS':
        return jsonify({}), 200

    data = request.get_json(silent=True) or {}
    name = (data.get('name') or '').strip().lower()
    description = (data.get('description') or '').strip() or None

    if not name:
        return jsonify({"message": "name is required"}), 400
    if name != '*' and not PERMISSION_NAME_RE.match(name):
        return jsonify({"message": "name must be lowercase snake_case, e.g. manage_something"}), 400
    if Permission.query.filter_by(name=name).first():
        return jsonify({"message": f"Permission '{name}' already exists"}), 409

    perm = Permission(name=name, description=description)
    db.session.add(perm)
    db.session.flush()
    log_audit('permission.create', 'permission', perm.id, payload_after={"name": name, "description": description})

    try:
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        return jsonify({"error": str(e)}), 500

    return jsonify({"status": "success", "message": f"Permission '{name}' created", "id": perm.id}), 201


@admin_bp.route('/permissions/<int:permission_id>', methods=['PUT', 'OPTIONS'], strict_slashes=False)
@jwt_required
@permission_required('admin_access')
def update_permission(permission_id):
    """Only description is editable — see the module docstring above for why."""
    if request.method == 'OPTIONS':
        return jsonify({}), 200

    perm = Permission.query.get(permission_id)
    if not perm:
        return jsonify({"message": "Permission not found"}), 404

    data = request.get_json(silent=True) or {}
    before = perm.description
    perm.description = (data.get('description') or '').strip() or None

    log_audit(
        'permission.update', 'permission', permission_id,
        payload_before={"description": before}, payload_after={"description": perm.description},
    )

    try:
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        return jsonify({"error": str(e)}), 500

    return jsonify({"status": "success", "message": f"Permission '{perm.name}' updated"}), 200


@admin_bp.route('/permissions/<int:permission_id>', methods=['DELETE', 'OPTIONS'], strict_slashes=False)
@jwt_required
@permission_required('admin_access')
def delete_permission(permission_id):
    if request.method == 'OPTIONS':
        return jsonify({}), 200

    perm = Permission.query.get(permission_id)
    if not perm:
        return jsonify({"message": "Permission not found"}), 404

    if perm.name == '*':
        return jsonify({"message": "The '*' (Admin wildcard) permission can't be deleted"}), 409

    roles_using = Role.query.filter(Role.permissions.any(id=permission_id)).count()
    if roles_using > 0:
        return jsonify({
            "message": f"'{perm.name}' is assigned to {roles_using} role(s) — remove it from them first."
        }), 409
    if AppModule.query.filter_by(permission_id=permission_id).first():
        return jsonify({
            "message": f"'{perm.name}' gates a module — remove or repoint that module first."
        }), 409

    log_audit('permission.delete', 'permission', permission_id, payload_before={"name": perm.name})

    db.session.delete(perm)
    try:
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        return jsonify({"error": str(e)}), 500

    return jsonify({"status": "success", "message": f"Permission '{perm.name}' deleted"}), 200



