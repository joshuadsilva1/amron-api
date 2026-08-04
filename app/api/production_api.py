from flask import Blueprint, request, jsonify
from app import db
from app.models.production import DailyProductionPlan
from app.models.item import InternalProduct
from app.models.department import Department
from datetime import datetime
from app.core.decorators import jwt_required
from app.core.notify import create_notification


production_bp = Blueprint('production', __name__)

@production_bp.route('/', methods=['POST'])
@jwt_required
def create_plan():
    """
    Creates a daily production allocation.
    Expected payload: 
    {
        "production_date": "2026-07-17",
        "product_id": "uuid-here",
        "department_name": "Moulding",
        "target_quantity": 5000,
        "priority": "Normal"
    }
    """
    data = request.get_json()
    
    product_id = data.get('product_id')
    department_name = data.get('department_name')
    target_quantity = data.get('target_quantity')
    production_date_str = data.get('production_date')
    
    if not all([product_id, department_name, target_quantity, production_date_str]):
        return jsonify({"error": "Missing required fields"}), 400

    # Validate Date
    try:
        prod_date = datetime.strptime(production_date_str, "%Y-%m-%d").date()
    except ValueError:
        return jsonify({"error": "Invalid date format. Use YYYY-MM-DD"}), 400

    # Ensure product exists
    product = InternalProduct.query.get(product_id)
    if not product:
        return jsonify({"error": "Product not found"}), 404

    new_plan = DailyProductionPlan(
        production_date=prod_date,
        product_id=product.id,
        department_name=department_name,
        target_quantity=int(target_quantity),
        priority=data.get('priority', 'Normal'),
        status='Pending'
    )

    try:
        db.session.add(new_plan)
        db.session.commit()
        return jsonify({
            "status": "success", 
            "message": f"Allocated {target_quantity} {product.unit_of_measure} of {product.name} to {department_name}",
            "plan_id": new_plan.id
        }), 201
    except Exception as e:
        db.session.rollback()
        return jsonify({"error": str(e)}), 500


@production_bp.route('/', methods=['GET'])
@jwt_required
def get_plans():
    """
    Fetches production plans. Can be filtered by date or department.
    e.g., /api/production?date=2026-07-17&department=Moulding
    """
    target_date = request.args.get('date')
    department = request.args.get('department')
    
    query = db.session.query(DailyProductionPlan, InternalProduct).join(
        InternalProduct, DailyProductionPlan.product_id == InternalProduct.id
    )
    
    if target_date:
        try:
            date_obj = datetime.strptime(target_date, "%Y-%m-%d").date()
            query = query.filter(DailyProductionPlan.production_date == date_obj)
        except ValueError:
            return jsonify({"error": "Invalid date format. Use YYYY-MM-DD"}), 400
            
    if department:
        query = query.filter(DailyProductionPlan.department_name == department)
        
    # Order by priority (Urgent first) and then by creation date
    results = query.order_by(
        db.case({ 'Urgent': 1, 'Normal': 2 }, value=DailyProductionPlan.priority),
        DailyProductionPlan.created_at.asc()
    ).all()
    
    formatted_data = []
    for plan, product in results:
        formatted_data.append({
            "plan_id": plan.id,
            "production_date": plan.production_date.strftime("%Y-%m-%d"),
            "department": plan.department_name,
            "product_name": product.name,
            "internal_code": product.item_code,
            "target_quantity": plan.target_quantity,
            "completed_quantity": plan.completed_quantity,
            "priority": plan.priority,
            "status": plan.status
        })
        
    return jsonify({"status": "success", "data": formatted_data}), 200


@production_bp.route('/send-schedule', methods=['POST', 'OPTIONS'], strict_slashes=False)
@jwt_required
def send_schedule():
    """Production Manager pushes the day's work allotment out to a
    department as a single notification, which floor workers see in their
    Notifications list."""
    if request.method == 'OPTIONS':
        return jsonify({}), 200

    data = request.get_json(silent=True) or {}
    department_name = data.get('department_name')
    production_date_str = data.get('production_date')

    if not department_name or not production_date_str:
        return jsonify({"error": "department_name and production_date are required"}), 400

    try:
        prod_date = datetime.strptime(production_date_str, "%Y-%m-%d").date()
    except ValueError:
        return jsonify({"error": "Invalid date format. Use YYYY-MM-DD"}), 400

    department = Department.query.filter_by(name=department_name).first()
    if not department:
        return jsonify({"error": f"Department '{department_name}' not found"}), 404

    results = db.session.query(DailyProductionPlan, InternalProduct).join(
        InternalProduct, DailyProductionPlan.product_id == InternalProduct.id
    ).filter(
        DailyProductionPlan.department_name == department_name,
        DailyProductionPlan.production_date == prod_date
    ).order_by(
        db.case({'Urgent': 1, 'Normal': 2}, value=DailyProductionPlan.priority)
    ).all()

    if not results:
        return jsonify({"error": f"No work allotted for {department_name} on {production_date_str} yet."}), 400

    lines = []
    for plan, product in results:
        urgent_tag = " (URGENT)" if plan.priority == 'Urgent' else ""
        lines.append(f"• {product.name}: {plan.target_quantity} {product.unit_of_measure}{urgent_tag}")

    note = create_notification(
        title=f"Today's Schedule — {department_name}",
        message=f"{production_date_str}\n" + "\n".join(lines),
        department_id=department.id,
    )

    try:
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        return jsonify({"error": str(e)}), 500

    return jsonify({
        "status": "success",
        "message": f"Schedule sent to {department_name} ({len(results)} item(s)).",
        "notification_id": note.id,
    }), 201