from app import db
from app.core.utils import generate_uuid
from datetime import datetime

class Rack(db.Model):
    __tablename__ = 'racks'
    
    id = db.Column(db.String(36), primary_key=True, default=generate_uuid)
    rack_code = db.Column(db.String(50), unique=True, nullable=False) # e.g., 'RACK-A1'
    department_id = db.Column(db.String(36), db.ForeignKey('departments.id'), nullable=False)
    
    description = db.Column(db.String(255), nullable=True)
    max_capacity_kg = db.Column(db.Float, default=0.0) # 0 means unlimited
    
    is_active = db.Column(db.Integer, default=1)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    # Relationship to easily grab the department name
    department = db.relationship('Department', backref='racks')