from flask import Blueprint, request, jsonify
from app import db
from app.models.dispatch import DispatchChallan, DispatchChallanItem
from app.models.client import Client
from app.models.item import InternalProduct
from app.core.decorators import jwt_required

dispatch_bp = Blueprint('dispatch', __name__)

@dispatch_bp.route('/challans', methods=['POST'])
@jwt_required
def create_dispatch_challan():
    """Creates a new outbound dispatch challan manually (Planned Dispatch)"""
    data = request.get_json()
    
    challan_number = data.get('challan_number')
    client_id = data.get('client_id')
    purchase_order_id = data.get('purchase_order_id')
    notes = data.get('note')
    items = data.get('items', [])
    
    if not challan_number or not items:
        return jsonify({"error": "Challan number and at least one item are required"}), 400

    # Create the Master Challan
    new_challan = DispatchChallan(
        challan_number=challan_number,
        client_id=client_id if client_id else None,
        purchase_order_id=purchase_order_id if purchase_order_id else None,
        notes=notes,
        status="Pending",
        created_by=data.get('user_name', 'Manager') # You can pass this from frontend context later
    )
    db.session.add(new_challan)
    db.session.flush() # Get the new_challan.id without committing

    # Create the Line Items
    for item in items:
        item_id = item.get('item_id')
        try:
            qty = float(item.get('qty'))
        except (TypeError, ValueError):
            qty = None
        if not item_id or qty is None or qty <= 0:
            db.session.rollback()
            return jsonify({"error": "Each item needs a valid item_id and a positive qty"}), 400

        new_item = DispatchChallanItem(
            dispatch_challan_id=new_challan.id,
            item_id=item_id,
            quantity=qty
        )
        db.session.add(new_item)

    try:
        db.session.commit()
        return jsonify({
            "status": "success",
            "message": "Dispatch challan created successfully",
            "challan_id": new_challan.id
        }), 201
    except Exception as e:
        db.session.rollback()
        return jsonify({"error": str(e)}), 500

@dispatch_bp.route('/challans', methods=['GET'])
@jwt_required
def get_dispatch_challans():
    """Fetches outbound dispatch challans for the UI tabs"""
    challans = DispatchChallan.query.order_by(DispatchChallan.created_at.desc()).all()
    result = []
    
    for challan in challans:
        client = Client.query.get(challan.client_id) if challan.client_id else None
        
        items_data = []
        for item in challan.items:
            product = InternalProduct.query.get(item.item_id)
            items_data.append({
                "item_id": item.item_id,
                "item_name": product.name if product else "Unknown Item",
                "quantity": item.quantity
            })

        result.append({
            "id": challan.id,
            "challan_number": challan.challan_number,
            "client_name": client.name if client else "Optional",
            "purchase_order_id": challan.purchase_order_id,
            "status": challan.status,
            "notes": challan.notes,
            "created_at": challan.created_at.isoformat() if challan.created_at else None,
            "items": items_data
        })
        
    return jsonify({"status": "success", "data": result}), 200