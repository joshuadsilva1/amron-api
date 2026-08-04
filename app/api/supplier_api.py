import os
import uuid
from flask import Blueprint, request, jsonify, current_app, g
from werkzeug.utils import secure_filename
from app import db
from app.models.supplier import Supplier
from app.models.supplier_order import SupplierOrder, SupplierOrderItem
from app.models.item import InternalProduct
from app.core.decorators import jwt_required
from app.core.notify import create_notification
from app.core.storage import upload_file

ALLOWED_ORDER_STATUSES = {'Approved', 'Rejected'}

suppliers_bp = Blueprint('suppliers', __name__)

ALLOWED_IMAGE_EXT = {'.jpg', '.jpeg', '.png', '.webp', '.heic'}

@suppliers_bp.route('/', methods=['POST', 'OPTIONS'], strict_slashes=False)
@jwt_required
def create_supplier():
    if request.method == 'OPTIONS':
        return jsonify({}), 200
    data = request.get_json()
    if not data or not data.get('name'):
        return jsonify({"error": "Supplier name is required"}), 400
        
    if Supplier.query.filter_by(name=data['name']).first():
        return jsonify({"error": "Supplier with this name already exists"}), 400
        
    new_supplier = Supplier(
        name=data['name'],
        contact_email=data.get('contact_email'),
        phone=data.get('phone'),
        address=data.get('address')
    )
    db.session.add(new_supplier)
    db.session.commit()
    
    return jsonify({"status": "success", "supplier_id": new_supplier.id}), 201

@suppliers_bp.route('/', methods=['GET'])
@jwt_required
def get_suppliers():
    suppliers = Supplier.query.filter_by(is_active=1).all()
    return jsonify({"status": "success", "suppliers": [{
        "id": s.id,
        "name": s.name,
        "contact_email": s.contact_email,
        "phone": s.phone,
        "address": s.address,
    } for s in suppliers]}), 200

@suppliers_bp.route('/<supplier_id>', methods=['PUT', 'OPTIONS'], strict_slashes=False)
@jwt_required
def update_supplier(supplier_id):
    if request.method == 'OPTIONS':
        return jsonify({}), 200

    supplier = Supplier.query.get(supplier_id)
    if not supplier or not supplier.is_active:
        return jsonify({"error": "Supplier not found"}), 404

    data = request.get_json(silent=True) or {}

    if 'name' in data:
        if not data['name']:
            return jsonify({"error": "Supplier name is required"}), 400
        existing = Supplier.query.filter(Supplier.name == data['name'], Supplier.id != supplier_id).first()
        if existing:
            return jsonify({"error": "Supplier with this name already exists"}), 400
        supplier.name = data['name']
    if 'contact_email' in data:
        supplier.contact_email = data['contact_email']
    if 'phone' in data:
        supplier.phone = data['phone']
    if 'address' in data:
        supplier.address = data['address']

    try:
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        return jsonify({"error": str(e)}), 500

    return jsonify({"status": "success", "message": f"Supplier '{supplier.name}' updated"}), 200

@suppliers_bp.route('/<supplier_id>', methods=['DELETE', 'OPTIONS'], strict_slashes=False)
@jwt_required
def delete_supplier(supplier_id):
    if request.method == 'OPTIONS':
        return jsonify({}), 200

    supplier = Supplier.query.get(supplier_id)
    if not supplier or not supplier.is_active:
        return jsonify({"error": "Supplier not found"}), 404

    orders_count = SupplierOrder.query.filter_by(supplier_id=supplier_id).count()
    supplier.is_active = 0

    try:
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        return jsonify({"error": str(e)}), 500

    message = (
        f"Supplier '{supplier.name}' deactivated ({orders_count} existing order(s) kept for history)"
        if orders_count > 0 else f"Supplier '{supplier.name}' deleted"
    )
    return jsonify({"status": "success", "message": message}), 200

# ==========================================
# NEW: SUPPLIER ORDERS ROUTES
# ==========================================

@suppliers_bp.route('/orders', methods=['POST','OPTIONS'], strict_slashes=False)
@jwt_required
def create_supplier_order():
    if request.method == 'OPTIONS':
            return jsonify({}), 200
    data = request.get_json()
    supplier_id = data.get('supplier_id')
    items = data.get('items', [])

    if not supplier_id or not items:
        return jsonify({"error": "supplier_id and items are required"}), 400

    new_order = SupplierOrder(
        supplier_id=supplier_id,
        department_id=data.get('department_id'),
        notes=data.get('notes'),
        is_urgent=data.get('is_urgent', 0)
    )
    db.session.add(new_order)
    db.session.flush() # Get the new_order.id without committing

    for item in items:
        line_item = SupplierOrderItem(
            supplier_order_id=new_order.id,
            product_id=item.get('product_id'),
            ordered_qty=item.get('ordered_qty')
        )
        db.session.add(line_item)

    try:
        db.session.commit()
        return jsonify({"status": "success", "order_id": new_order.id}), 201
    except Exception as e:
        db.session.rollback()
        return jsonify({"error": str(e)}), 500

@suppliers_bp.route('/orders/<order_id>/status', methods=['PUT', 'OPTIONS'], strict_slashes=False)
@jwt_required
def update_supplier_order_status(order_id):
    """Production Manager approves or rejects a supplier order once it comes in."""
    if request.method == 'OPTIONS':
        return jsonify({}), 200

    order = SupplierOrder.query.get(order_id)
    if not order:
        return jsonify({"error": "Supplier order not found"}), 404

    data = request.get_json(silent=True) or {}
    new_status = data.get('status')

    if new_status not in ALLOWED_ORDER_STATUSES:
        return jsonify({"error": f"status must be one of {sorted(ALLOWED_ORDER_STATUSES)}"}), 400
    if order.status != 'Pending':
        return jsonify({"error": f"Order is already '{order.status}' — only Pending orders can be approved or rejected."}), 400

    order.status = new_status

    supplier = Supplier.query.get(order.supplier_id)
    create_notification(
        title=f"Supplier Order {new_status}",
        message=f"Order to {supplier.name if supplier else 'supplier'} was {new_status.lower()} by {g.current_user.full_name or 'a manager'}.",
        department_id=order.department_id,
    )

    try:
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        return jsonify({"error": str(e)}), 500

    return jsonify({"status": "success", "message": f"Order {new_status.lower()}"}), 200


@suppliers_bp.route('/orders/<order_id>/bill', methods=['POST', 'OPTIONS'], strict_slashes=False)
@jwt_required
def upload_bill_image(order_id):
    """Attach a photo of the supplier's bill/chalan to a supplier order."""
    if request.method == 'OPTIONS':
        return jsonify({}), 200

    order = SupplierOrder.query.get(order_id)
    if not order:
        return jsonify({"error": "Supplier order not found"}), 404

    uploaded_file = None
    for key in ['file', 'image', 'bill', 'chalan']:
        if key in request.files:
            uploaded_file = request.files[key]
            break
    if not uploaded_file and len(request.files) > 0:
        uploaded_file = next(iter(request.files.values()))

    if not uploaded_file or uploaded_file.filename == '':
        return jsonify({"error": "No image uploaded. Expected multipart/form-data with an image file."}), 400

    ext = os.path.splitext(uploaded_file.filename)[1].lower()
    if ext not in ALLOWED_IMAGE_EXT:
        return jsonify({"error": f"Unsupported file type '{ext}'. Use jpg, png, webp, or heic."}), 400

    filename = f"{order_id}_{uuid.uuid4().hex}{ext}"
    filename = secure_filename(filename)
    order.bill_image_url = upload_file(uploaded_file, 'supplier_bills', filename)

    try:
        db.session.commit()
        return jsonify({"status": "success", "bill_image_url": order.bill_image_url}), 200
    except Exception as e:
        db.session.rollback()
        return jsonify({"error": str(e)}), 500

@suppliers_bp.route('/orders', methods=['GET', 'OPTIONS'], strict_slashes=False)
@jwt_required
def get_supplier_orders():
    if request.method == 'OPTIONS':
                return jsonify({}), 200
    
    # Order by newest first
    orders = SupplierOrder.query.order_by(SupplierOrder.order_date.desc()).all()
    result = []
    
    for order in orders:
        supplier = Supplier.query.get(order.supplier_id)
        
        items_data = []
        for item in order.items:
            product = InternalProduct.query.get(item.product_id)
            items_data.append({
                "product_id": item.product_id,
                "product_name": product.name if product else "Unknown Item",
                "ordered_qty": item.ordered_qty,
                "received_qty": item.received_qty
            })

        result.append({
            "id": order.id,
            "supplier_name": supplier.name if supplier else "Unknown Supplier",
            "department_id": order.department_id,
            "status": order.status,
            "notes": order.notes,
            "is_urgent": order.is_urgent,
            "bill_image_url": order.bill_image_url,
            "order_date": order.order_date.isoformat() if order.order_date else None,
            "items": items_data
        })
        
    return jsonify({"status": "success", "data": result}), 200