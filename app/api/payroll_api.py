from flask import Blueprint, request, jsonify
from app import db
from app.models.employee import Employee, AttendanceRecord
import calendar
from app.core.decorators import jwt_required

payroll_bp = Blueprint('payroll', __name__)

@payroll_bp.route('/report', methods=['GET'])
@jwt_required
def get_payroll_report():
    """
    Calculates monthly payroll based on attendance records and base salary.
    Expected query param: ?month=YYYY-MM (e.g., ?month=2026-07)
    """
    month_param = request.args.get('month')
    
    if not month_param:
        return jsonify({"error": "Month parameter (YYYY-MM) is required"}), 400
        
    try:
        year_str, month_str = month_param.split('-')
        year = int(year_str)
        month = int(month_str)
    except ValueError:
        return jsonify({"error": "Invalid month format. Use YYYY-MM"}), 400

    # Get total days in the specified month for daily rate calculation
    days_in_month = calendar.monthrange(year, month)[1]
    
    # Fetch all active employees
    employees = Employee.query.filter_by(is_active=1).all()
    payroll_summaries = []
    
    for emp in employees:
        # Fetch all attendance entries for this employee for this specific month
        records = AttendanceRecord.query.filter(
            AttendanceRecord.employee_id == emp.id,
            AttendanceRecord.date_string.like(f"{month_param}-%")
        ).all()
        
        # 1. Calculate days worked
        # Present = 1.0 day, Half-Day = 0.5 day, Absent = 0.0
        days_worked = 0.0
        for record in records:
            status = record.status.capitalize()
            if status == 'Present':
                days_worked += 1.0
            elif status in ['Half-day', 'Half-Day']:
                days_worked += 0.5
                
        # 2. Calculate proportional base salary based on attendance
        base_salary = emp.base_monthly_salary or 0.0
        daily_rate = base_salary / days_in_month if days_in_month > 0 else 0.0
        calculated_base = daily_rate * days_worked
        
        # 3. Handle bonuses or Overtime if applicable 
        # (Using 0 or pulling from record if your model tracks it)
        bonus = 0.0 
        
        total_payable = calculated_base + bonus
        
        payroll_summaries.append({
            "user_id": emp.id,
            "worker_name": emp.name,
            "total_days_worked": days_worked,
            "base_salary": round(base_salary, 2),
            "bonus": round(bonus, 2),
            "total_payable": round(total_payable, 2)
        })

    return jsonify({
        "status": "success",
        "data": payroll_summaries
    }), 200