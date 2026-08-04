from app import db
from app.core.utils import generate_uuid
from datetime import datetime

class Employee(db.Model):
    """Master record for factory staff"""
    __tablename__ = 'employees'
    
    id = db.Column(db.String(36), primary_key=True, default=generate_uuid)
    name = db.Column(db.String(150), nullable=False)
    phone = db.Column(db.String(20), nullable=True)
    department_id = db.Column(db.String(36), db.ForeignKey('departments.id'), nullable=True)
    base_monthly_salary = db.Column(db.Float, default=0.0)
    
    is_active = db.Column(db.Integer, default=1)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class AttendanceRecord(db.Model):
    """Daily attendance log for payroll calculation"""
    __tablename__ = 'attendance_records'
    
    id = db.Column(db.String(36), primary_key=True, default=generate_uuid)
    employee_id = db.Column(db.String(36), db.ForeignKey('employees.id'), nullable=False)
    
    # Stored as YYYY-MM-DD for easy querying
    date_string = db.Column(db.String(10), nullable=False) 
    
    status = db.Column(db.String(20), default='Present') # Present, Absent, Half-day, Leave
    ot_hours = db.Column(db.Float, default=0.0)
    
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Ensure only one record per employee per day
    __table_args__ = (
        db.UniqueConstraint('employee_id', 'date_string', name='uq_employee_date'),
    )