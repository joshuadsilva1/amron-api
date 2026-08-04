from flask import Blueprint, request, jsonify
from app import db
from app.models.employee import Employee, AttendanceRecord
from app.models.department import Department
from datetime import datetime
from app.core.decorators import jwt_required

attendance_bp = Blueprint('attendance', __name__)

@attendance_bp.route('/employees', methods=['POST'])
@jwt_required
def add_employee():
    """Creates a new employee from the modal"""
    data = request.get_json()
    
    name = data.get('name')
    if not name:
        return jsonify({"error": "Employee name is required"}), 400
        
    try:
        salary = float(data.get('base_monthly_salary', 0))
    except ValueError:
        return jsonify({"error": "Salary must be a valid number"}), 400

    new_employee = Employee(
        name=name,
        phone=data.get('phone'),
        department_id=data.get('department_id'),
        base_monthly_salary=salary
    )
    
    try:
        db.session.add(new_employee)
        db.session.commit()
        return jsonify({"status": "success", "message": "Employee added"}), 201
    except Exception as e:
        db.session.rollback()
        return jsonify({"error": str(e)}), 500

@attendance_bp.route('/daily', methods=['GET'])
@jwt_required
def get_daily_attendance():
    """Fetches all active employees and their attendance for a specific date"""
    date_str = request.args.get('date') # Expected format: YYYY-MM-DD
    if not date_str:
        date_str = datetime.now().strftime('%Y-%m-%d')
        
    employees = Employee.query.filter_by(is_active=1).all()
    
    attendance_data = []
    present_count = 0
    
    for emp in employees:
        dept = Department.query.get(emp.department_id) if emp.department_id else None
        
        # Check if they have a record for this specific date
        record = AttendanceRecord.query.filter_by(employee_id=emp.id, date_string=date_str).first()
        
        status = record.status if record else None
        ot_hours = record.ot_hours if record else 0.0
        
        if status in ['Present', 'Half-day']:
            present_count += 1
            
        attendance_data.append({
            "employee_id": emp.id,
            "name": emp.name,
            "department": dept.name if dept else "-",
            "status": status,
            "ot_hours": ot_hours
        })
        
    return jsonify({
        "status": "success",
        "summary": {
            "total_staff": len(employees),
            "present_count": present_count,
            "date": date_str
        },
        "data": attendance_data
    }), 200

@attendance_bp.route('/mark', methods=['POST'])
@jwt_required
def mark_attendance():
    """Marks or updates an employee's status/OT for a specific day"""
    data = request.get_json()
    
    employee_id = data.get('employee_id')
    date_str = data.get('date')
    status = data.get('status')
    ot_hours = data.get('ot_hours', 0.0)
    
    if not all([employee_id, date_str, status]):
        return jsonify({"error": "Employee ID, date, and status are required"}), 400
        
    record = AttendanceRecord.query.filter_by(employee_id=employee_id, date_string=date_str).first()
    
    try:
        if record:
            record.status = status
            record.ot_hours = float(ot_hours)
        else:
            new_record = AttendanceRecord(
                employee_id=employee_id,
                date_string=date_str,
                status=status,
                ot_hours=float(ot_hours)
            )
            db.session.add(new_record)
            
        db.session.commit()
        return jsonify({"status": "success", "message": "Attendance saved"}), 200
    except Exception as e:
        db.session.rollback()
        return jsonify({"error": str(e)}), 500