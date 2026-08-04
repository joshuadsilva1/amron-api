from app import db
from app.core.utils import generate_uuid
from datetime import datetime

# Association table for the many-to-many relationship
role_permissions = db.Table('role_permissions',
    db.Column('role_id', db.Integer, db.ForeignKey('roles.id'), primary_key=True),
    db.Column('permission_id', db.Integer, db.ForeignKey('permissions.id'), primary_key=True)
)

# app/models/user.py (or wherever your Role/Permission models are)

class AppModule(db.Model):
    __tablename__ = "app_modules"
    
    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    name = db.Column(db.String(100), nullable=False)             # e.g., "Products & Recipes"
    route = db.Column(db.String(255), nullable=False)            # e.g., "/(protected)/manager/items"
    icon = db.Column(db.String(50), default="grid")              # e.g., "box"
    description = db.Column(db.String(255))                      # e.g., "Manage BOM and items"
    
    # Link to the Permission table. A module requires a specific permission to be viewed.
    permission_id = db.Column(db.Integer, db.ForeignKey('permissions.id'), nullable=False)
    required_permission = db.relationship('Permission', backref='modules')
    
    # Allows the admin to temporarily hide a module for maintenance without deleting it
    is_active = db.Column(db.Boolean, default=True)

class Permission(db.Model):
    __tablename__ = "permissions"
    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    name = db.Column(db.String(50), unique=True, nullable=False) # e.g., 'manage_recipes', 'scan_inventory'
    description = db.Column(db.String(255))

class Role(db.Model):
    __tablename__ = "roles"
    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    name = db.Column(db.String(50), unique=True, nullable=False)
    description = db.Column(db.String(255))
    
    # Allows you to access role.permissions easily
    permissions = db.relationship('Permission', secondary=role_permissions, lazy='subquery')

class User(db.Model):
    __tablename__ = "users"
    id = db.Column(db.String(36), primary_key=True, default=generate_uuid)
    phone_number = db.Column(db.String(20), unique=True, nullable=False)
    full_name = db.Column(db.String(100))
    role_id = db.Column(db.Integer, db.ForeignKey('roles.id'), default=1)
    department_id = db.Column(db.String(36), db.ForeignKey("departments.id"))
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    role_data = db.relationship('Role', backref='users')