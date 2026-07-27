from flask import Blueprint, request, jsonify
from app import db
from app.models.order import PurchaseOrder, POLineItem
from app.models.item import InternalProduct, OEMCompanyCode
from sqlalchemy import func

orders_bp = Blueprint('orders', __name__)

@orders_bp.route('/', methods=['POST'])
def create_po():
    """Endpoint for Production Manager to enter a Client PO"""
    data = request.get_json()
    
    new_po = PurchaseOrder(
        client_id=data.get('client_id'),
        notes=data.get('notes'),
        is_urgent=data.get('is_urgent', 0),
        # Convert string dates to datetime objects in production
    )
    db.session.add(new_po)
    db.session.flush() # Get the new_po.id without committing yet
    
    # Add the line items
    items = data.get('items', [])
    for item in items:
        line_item = POLineItem(
            order_id=new_po.id,
            mapping_id=item.get('mapping_id'), # The OEM code they ordered under
            quantity=item.get('quantity')
        )
        db.session.add(line_item)
        
    try:
        db.session.commit()
        return jsonify({"status": "success", "message": "PO Created", "po_id": new_po.id}), 201
    except Exception as e:
        db.session.rollback()
        return jsonify({"error": str(e)}), 500


@orders_bp.route('/clubbed', methods=['GET'])
def get_clubbed_orders():
    """
    The Clubbing Engine: Aggregates all pending POs by translating 
    OEM codes into Internal Master SKUs and summing the quantities.
    """
    clubbed_data = db.session.query(
        InternalProduct.internal_code,
        InternalProduct.name,
        InternalProduct.category,
        func.sum(POLineItem.quantity).label('total_required')
    ).join(
        OEMCompanyCode, POLineItem.mapping_id == OEMCompanyCode.id
    ).join(
        InternalProduct, OEMCompanyCode.internal_product_id == InternalProduct.id
    ).join(
        PurchaseOrder, POLineItem.order_id == PurchaseOrder.id
    ).filter(
        PurchaseOrder.status == 'Pending'
    ).group_by(
        InternalProduct.id
    ).all()

    result = []
    for row in clubbed_data:
        result.append({
            "internal_code": row.internal_code,
            "product_name": row.name,
            "category": row.category,
            "total_quantity_to_manufacture": row.total_required
        })

    return jsonify({"status": "success", "data": result}), 200