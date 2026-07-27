from app import db
from app.core.utils import generate_uuid
from datetime import datetime
import enum



class DepartmentRoute(db.Model):
    """Dynamic routing rules defining allowed material movement"""
    __tablename__ = 'department_routes'
    
    id = db.Column(db.String(36), primary_key=True, default=generate_uuid)
    
    from_department_id = db.Column(db.String(36), db.ForeignKey('departments.id'), nullable=False)
    to_department_id = db.Column(db.String(36), db.ForeignKey('departments.id'), nullable=False)
    
    is_active = db.Column(db.Integer, default=1)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    # This prevents the admin from accidentally creating the same rule twice
    __table_args__ = (
        db.UniqueConstraint('from_department_id', 'to_department_id', name='uq_route_from_to'),
    )

class DeptLevel(enum.IntEnum):
    MIDDLE = 0
    TOP_LEVEL = 1
    FINAL = 2

class Department(db.Model):
    __tablename__ = 'departments'
    
    id = db.Column(db.String(36), primary_key=True, default=generate_uuid)
    
    department_code = db.Column(db.Integer, unique=True, nullable=True) 
    
    name = db.Column(db.String(100), unique=True, nullable=False)
    department_level = db.Column(db.Integer, default=DeptLevel.MIDDLE.value, nullable=False) 
    is_active = db.Column(db.Integer, default=1)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)