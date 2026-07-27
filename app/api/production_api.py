from flask import Blueprint, request, jsonify
from app import db
from app.models.production import DailyProductionPlan
from app.models.item import InternalProduct
from datetime import datetime

production_bp = Blueprint('production', __name__)

@production_bp.route('/', methods=['POST'])
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
            "message": f"Allocated {target_quantity} {product.unit} of {product.name} to {department_name}",
            "plan_id": new_plan.id
        }), 201
    except Exception as e:
        db.session.rollback()
        return jsonify({"error": str(e)}), 500


@production_bp.route('/', methods=['GET'])
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
            "internal_code": product.internal_code,
            "target_quantity": plan.target_quantity,
            "completed_quantity": plan.completed_quantity,
            "priority": plan.priority,
            "status": plan.status
        })
        
    return jsonify({"status": "success", "data": formatted_data}), 200