from flask import Blueprint, request, jsonify, g
from app import db
from app.models.production import DailyProductionPlan, ProductionPlanDay, PLAN_DAY_STATUSES, VARIANCE_REASONS
from app.models.item import InternalProduct, OEMCompanyCode
from app.models.department import Department
from app.models.order import PurchaseOrder
from app.models.client import Client
from app.core.mrp import compute_shortages
from app.core.bom import explode_product_quantity
from datetime import datetime, timedelta
from app.core.decorators import jwt_required
from app.core.notify import create_notification


production_bp = Blueprint('production', __name__)

CLOSED_PO_STAGES = {'Dispatched', 'Closed'}

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


@production_bp.route('/<plan_id>', methods=['PUT', 'OPTIONS'], strict_slashes=False)
@jwt_required
def update_plan(plan_id):
    """Updates a plan row's target/completed quantity, priority, or
    status. Marking a row Completed while short of target requires a
    variance_reason — accountability for why the number was missed,
    instead of it just silently not matching."""
    if request.method == 'OPTIONS':
        return jsonify({}), 200

    plan = DailyProductionPlan.query.get(plan_id)
    if not plan:
        return jsonify({"error": "Plan not found"}), 404

    data = request.get_json(silent=True) or {}

    if 'target_quantity' in data:
        plan.target_quantity = int(data['target_quantity'])
    if 'completed_quantity' in data:
        plan.completed_quantity = int(data['completed_quantity'])
    if 'priority' in data:
        plan.priority = data['priority']
    if 'variance_reason' in data:
        if data['variance_reason'] and data['variance_reason'] not in VARIANCE_REASONS:
            return jsonify({"error": f"variance_reason must be one of {VARIANCE_REASONS}"}), 400
        plan.variance_reason = data['variance_reason']

    new_status = data.get('status')
    if new_status:
        if new_status not in ('Pending', 'In_Progress', 'Completed'):
            return jsonify({"error": "status must be Pending, In_Progress, or Completed"}), 400
        if new_status == 'Completed' and plan.completed_quantity < plan.target_quantity and not plan.variance_reason:
            return jsonify({"error": "This is short of target — a variance_reason is required to mark it Completed."}), 400
        plan.status = new_status

    try:
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        return jsonify({"error": str(e)}), 500

    return jsonify({
        "status": "success",
        "plan_id": plan.id,
        "target_quantity": plan.target_quantity,
        "completed_quantity": plan.completed_quantity,
        "plan_status": plan.status,
        "variance_reason": plan.variance_reason,
    }), 200


@production_bp.route('/<plan_id>', methods=['DELETE', 'OPTIONS'], strict_slashes=False)
@jwt_required
def delete_plan(plan_id):
    if request.method == 'OPTIONS':
        return jsonify({}), 200

    plan = DailyProductionPlan.query.get(plan_id)
    if not plan:
        return jsonify({"error": "Plan not found"}), 404

    db.session.delete(plan)
    try:
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        return jsonify({"error": str(e)}), 500

    return jsonify({"status": "success"}), 200


@production_bp.route('/plan-day/<date_str>/status', methods=['PUT', 'OPTIONS'], strict_slashes=False)
@jwt_required
def set_plan_day_status(date_str):
    """Moves a whole day's plan through Draft -> Validated -> Approved ->
    Released. Only a Released plan is considered live/departments' actual
    instructions — earlier statuses are working drafts."""
    if request.method == 'OPTIONS':
        return jsonify({}), 200

    try:
        plan_date = datetime.strptime(date_str, "%Y-%m-%d").date()
    except ValueError:
        return jsonify({"error": "Invalid date format. Use YYYY-MM-DD"}), 400

    data = request.get_json(silent=True) or {}
    new_status = data.get('status')
    if new_status not in PLAN_DAY_STATUSES:
        return jsonify({"error": f"status must be one of {PLAN_DAY_STATUSES}"}), 400

    plan_day = ProductionPlanDay.query.filter_by(plan_date=plan_date).first()
    if not plan_day:
        plan_day = ProductionPlanDay(plan_date=plan_date, status=new_status, created_by=g.current_user.id)
        db.session.add(plan_day)
    else:
        plan_day.status = new_status

    try:
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        return jsonify({"error": str(e)}), 500

    return jsonify({"status": "success", "plan_date": date_str, "plan_status": plan_day.status}), 200


@production_bp.route('/plan-day', methods=['GET', 'OPTIONS'], strict_slashes=False)
@jwt_required
def get_plan_day():
    """
    The 7:30 AM screen's data bundle for a given date (defaults to
    tomorrow): yesterday's plan-vs-actual, today's/this date's plan rows
    grouped by department, the day's lifecycle status, and BOM/MRP-aware
    readiness for every open PO's remaining quantity — so the Production
    Manager sees what's actually achievable, not just a wishlist.
    """
    if request.method == 'OPTIONS':
        return jsonify({}), 200

    date_str = request.args.get('date')
    if date_str:
        try:
            target_date = datetime.strptime(date_str, "%Y-%m-%d").date()
        except ValueError:
            return jsonify({"error": "Invalid date format. Use YYYY-MM-DD"}), 400
    else:
        target_date = datetime.utcnow().date() + timedelta(days=1)

    previous_date = target_date - timedelta(days=1)

    # --- Previous day variance ---
    prev_rows = db.session.query(DailyProductionPlan, InternalProduct).join(
        InternalProduct, DailyProductionPlan.product_id == InternalProduct.id
    ).filter(DailyProductionPlan.production_date == previous_date).all()

    prev_lines = []
    prev_planned_total = 0
    prev_completed_total = 0
    for plan, product in prev_rows:
        prev_planned_total += plan.target_quantity
        prev_completed_total += plan.completed_quantity or 0
        prev_lines.append({
            "plan_id": plan.id,
            "product_name": product.name,
            "department": plan.department_name,
            "target_quantity": plan.target_quantity,
            "completed_quantity": plan.completed_quantity or 0,
            "variance": (plan.completed_quantity or 0) - plan.target_quantity,
            "variance_reason": plan.variance_reason,
            "status": plan.status,
        })

    # --- This date's plan rows, grouped by department ---
    rows = db.session.query(DailyProductionPlan, InternalProduct).join(
        InternalProduct, DailyProductionPlan.product_id == InternalProduct.id
    ).filter(DailyProductionPlan.production_date == target_date).order_by(
        db.case({'Urgent': 1, 'Normal': 2}, value=DailyProductionPlan.priority)
    ).all()

    by_department = {}
    for plan, product in rows:
        by_department.setdefault(plan.department_name, []).append({
            "plan_id": plan.id,
            "product_id": product.id,
            "product_name": product.name,
            "internal_code": product.item_code,
            "target_quantity": plan.target_quantity,
            "completed_quantity": plan.completed_quantity or 0,
            "priority": plan.priority,
            "status": plan.status,
        })

    # --- Plan day lifecycle status ---
    plan_day = ProductionPlanDay.query.filter_by(plan_date=target_date).first()

    # --- PO material readiness (BOM/MRP-aware) ---
    shortages = compute_shortages()
    shortage_item_ids = {item_id for item_id, row in shortages.items() if row['shortage'] > 0}

    active_pos = PurchaseOrder.query.filter(
        PurchaseOrder.is_active == 1,
        ~PurchaseOrder.status.in_(CLOSED_PO_STAGES)
    ).all()

    demand_readiness = []
    for po in active_pos:
        client = Client.query.get(po.client_id)
        for li in po.items:
            remaining = (li.quantity or 0) - (li.produced_qty or 0)
            if remaining <= 0:
                continue
            mapping = OEMCompanyCode.query.get(li.mapping_id)
            if not mapping:
                continue
            product = InternalProduct.query.get(mapping.internal_product_id)
            if not product:
                continue
            try:
                exploded = explode_product_quantity(mapping.internal_product_id, remaining)
            except ValueError:
                exploded = {}
            needed_ids = set(exploded.keys())
            blocked = needed_ids & shortage_item_ids
            readiness = 'RED' if blocked else 'GREEN'

            demand_readiness.append({
                "po_id": po.id,
                "customer": client.name if client else "Unknown",
                "product_name": product.name,
                "product_id": product.id,
                "remaining_quantity": remaining,
                "due_date": po.required_date.isoformat() if po.required_date else None,
                "is_urgent": bool(po.is_urgent),
                "readiness": readiness,
                "blocked_by": [shortages[i]['item_name'] for i in blocked],
            })

    readiness_order = {'RED': 0, 'GREEN': 1}
    demand_readiness.sort(key=lambda r: (readiness_order.get(r['readiness'], 2), r['due_date'] or '9999'))

    return jsonify({
        "status": "success",
        "plan_date": target_date.isoformat(),
        "plan_status": plan_day.status if plan_day else 'Draft',
        "previous_day": {
            "date": previous_date.isoformat(),
            "planned_total": prev_planned_total,
            "completed_total": prev_completed_total,
            "variance": prev_completed_total - prev_planned_total,
            "lines": prev_lines,
        },
        "by_department": by_department,
        "demand_readiness": demand_readiness,
        "variance_reasons": VARIANCE_REASONS,
    }), 200