from flask import Blueprint, jsonify
from datetime import datetime, timedelta
from app import db
from app.models.order import PurchaseOrder, POLineItem, PO_STATUS_PIPELINE
from app.models.item import InternalProduct, OEMCompanyCode
from app.models.client import Client
from app.models.production import DailyProductionPlan
from app.models.qc_template import QCInspection
from app.models.supplier_order import SupplierOrder, SupplierOrderItem
from app.core.decorators import jwt_required

control_tower_bp = Blueprint('control_tower', __name__)

# POs at or past this stage are considered "done" and excluded from the
# in-flight table / risk calculation.
CLOSED_STAGES = {'Dispatched', 'Closed'}
LATE_STAGES = {'Packing', 'Dispatched', 'Closed'}


def _po_risk_color(po, total_qty, dispatched_qty):
    if po.status in CLOSED_STAGES:
        return 'GREEN'
    if not po.required_date:
        return 'GREEN'
    days_left = (po.required_date.date() - datetime.utcnow().date()).days
    if days_left < 0:
        return 'RED'
    if days_left <= 2 and po.status not in LATE_STAGES:
        return 'YELLOW'
    return 'GREEN'


@control_tower_bp.route('/summary', methods=['GET', 'OPTIONS'], strict_slashes=False)
@jwt_required
def get_summary():
    from flask import request
    if request.method == 'OPTIONS':
        return jsonify({}), 200

    today = datetime.utcnow().date()
    tomorrow = today + timedelta(days=1)
    today_start = datetime.combine(today, datetime.min.time())
    today_end = datetime.combine(today, datetime.max.time())

    active_pos = PurchaseOrder.query.filter(
        PurchaseOrder.is_active == 1,
        ~PurchaseOrder.status.in_(CLOSED_STAGES)
    ).all()

    total_active_pos = len(active_pos)
    new_today = sum(1 for po in active_pos if po.order_date and today_start <= po.order_date <= today_end)
    urgent = sum(1 for po in active_pos if po.is_urgent)
    due_today = sum(1 for po in active_pos if po.required_date and po.required_date.date() == today)
    due_tomorrow = sum(1 for po in active_pos if po.required_date and po.required_date.date() == tomorrow)
    overdue = sum(1 for po in active_pos if po.required_date and po.required_date.date() < today)

    # Production today
    todays_plans = DailyProductionPlan.query.filter(DailyProductionPlan.production_date == today).all()
    production_planned_today = sum(p.target_quantity for p in todays_plans)
    production_completed_today = sum(p.completed_quantity or 0 for p in todays_plans)
    production_pending_today = max(0, production_planned_today - production_completed_today)

    # Material shortages: items at/below reorder level
    material_shortages = InternalProduct.query.filter(
        InternalProduct.reorder_level > 0,
        InternalProduct.current_stock <= InternalProduct.reorder_level
    ).count()

    # Quality holds: outstanding rejected inspections (no resolve/lift
    # workflow exists yet, so "rejected" is the closest available signal)
    quality_holds = QCInspection.query.filter(QCInspection.overall_result == 'Rejected').count()

    # Supplier pending: approved orders not yet fully received
    pending_supplier_orders = 0
    for so in SupplierOrder.query.filter(SupplierOrder.is_active == 1, SupplierOrder.status == 'Approved').all():
        ordered = sum(i.ordered_qty for i in so.items)
        received = sum(i.received_qty or 0 for i in so.items)
        if received < ordered:
            pending_supplier_orders += 1

    # Dispatch pending: in-flight POs where dispatched qty hasn't caught up
    dispatch_pending = 0
    for po in active_pos:
        total_qty = sum(li.quantity for li in po.items)
        dispatched_qty = sum(li.dispatched_qty or 0 for li in po.items)
        if dispatched_qty < total_qty:
            dispatch_pending += 1

    # --- PO table (matches the Control Tower's daily order board) ---
    order_rows = []
    for po in active_pos:
        client = Client.query.get(po.client_id)
        total_qty = sum(li.quantity for li in po.items)
        dispatched_qty = sum(li.dispatched_qty or 0 for li in po.items)
        produced_qty = sum(li.produced_qty or 0 for li in po.items)

        product_names = []
        for li in po.items:
            mapping = OEMCompanyCode.query.get(li.mapping_id)
            if mapping:
                product = InternalProduct.query.get(mapping.internal_product_id)
                if product:
                    product_names.append(product.name)
        if len(product_names) == 1:
            product_label = product_names[0]
        elif len(product_names) > 1:
            product_label = f"{product_names[0]} +{len(product_names) - 1} more"
        else:
            product_label = "—"

        order_rows.append({
            "po_id": po.id,
            "customer": client.name if client else "Unknown",
            "product": product_label,
            "quantity": total_qty,
            "produced_qty": produced_qty,
            "dispatched_qty": dispatched_qty,
            "due_date": po.required_date.isoformat() if po.required_date else None,
            "is_urgent": bool(po.is_urgent),
            "current_stage": po.status,
            "risk": _po_risk_color(po, total_qty, dispatched_qty),
        })

    # Worst-risk first, then soonest due date
    risk_order = {'RED': 0, 'YELLOW': 1, 'GREEN': 2}
    order_rows.sort(key=lambda r: (risk_order.get(r['risk'], 3), r['due_date'] or '9999'))

    return jsonify({
        "status": "success",
        "generated_at": datetime.utcnow().isoformat(),
        "today": {
            "total_active_pos": total_active_pos,
            "new_today": new_today,
            "urgent": urgent,
            "due_today": due_today,
            "due_tomorrow": due_tomorrow,
            "overdue": overdue,
            "production_planned_today": production_planned_today,
            "production_completed_today": production_completed_today,
            "production_pending_today": production_pending_today,
            "material_shortages": material_shortages,
            "quality_holds": quality_holds,
            "supplier_pending": pending_supplier_orders,
            "dispatch_pending": dispatch_pending,
        },
        "orders": order_rows,
        "status_pipeline": PO_STATUS_PIPELINE,
    }), 200
