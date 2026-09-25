import os
import uuid
from flask import Blueprint, request, jsonify, current_app, g
from werkzeug.utils import secure_filename
from app import db
from app.models.supplier import Supplier
from app.models.supplier_order import SupplierOrder, SupplierOrderItem, SupplierOrderMaterial
from app.models.item import InternalProduct
from app.models.recipe import BOMVersion
from app.models.department_po import DepartmentPO, DepartmentPOItem
from app.core.department_levels import is_finished_good
from app.core.decorators import jwt_required, permission_required
from app.core.notify import create_notification
from app.core.storage import upload_file

ALLOWED_ORDER_STATUSES = {'Approved', 'Rejected'}

suppliers_bp = Blueprint('suppliers', __name__)

ALLOWED_IMAGE_EXT = {'.jpg', '.jpeg', '.png', '.webp', '.heic'}

@suppliers_bp.route('/', methods=['POST', 'OPTIONS'], strict_slashes=False)
@jwt_required
@permission_required('manage_suppliers')
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
@permission_required('manage_suppliers')
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
@permission_required('manage_suppliers')
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

def materials_to_send(product_id, quantity):
    """Job work: what we must send a supplier so they can make `quantity`
    of `product_id` for us — its active recipe's direct components,
    scaled up and including each row's wastage %. e.g. 300 caps at
    0.012 kg powder/cap + 5% wastage -> 3.78 kg powder.
    [] for an item with no recipe (a plain purchase)."""
    bom_version = BOMVersion.query.filter_by(finished_good_id=product_id, is_active=True).first()
    if not bom_version:
        return []
    out = []
    for row in bom_version.components:
        comp = InternalProduct.query.get(row.component_id)
        if not comp:
            continue
        qty = row.quantity_required * quantity * (1 + (row.wastage_percent or 0) / 100)
        out.append({
            "product_id": comp.id,
            "item_code": comp.item_code,
            "name": comp.name,
            "unit_of_measure": comp.unit_of_measure,
            "per_unit": row.quantity_required,
            "wastage_percent": row.wastage_percent or 0,
            "quantity": round(qty, 3),
        })
    return out


def _item_brief(item):
    return {
        "id": item.id,
        "item_code": item.item_code,
        "name": item.name,
        "unit_of_measure": item.unit_of_measure,
        "department_id": item.department_id,
    }


@suppliers_bp.route('/orderable-items', methods=['GET'], strict_slashes=False)
@jwt_required
def orderable_items():
    """What a department can order from a supplier — never finished
    goods. Two kinds:
      - "job_work": parts this department makes, which can instead be
        made by a supplier (we send them the recipe's materials);
        includes how many are still owed on open internal POs.
      - "purchase": raw materials this department's recipes use that
        aren't made in-house (no recipe), plus any other no-recipe item
        sitting in this department (e.g. powder in a Raw Material Store).
    ?department_id= required."""
    department_id = request.args.get('department_id')
    if not department_id:
        return jsonify({"error": "department_id is required"}), 400

    recipe_ids = {bv.finished_good_id for bv in BOMVersion.query.filter_by(is_active=True).all()}
    own_items = InternalProduct.query.filter_by(department_id=department_id, is_active=1).all()

    outstanding = {}
    open_rows = DepartmentPOItem.query.join(DepartmentPO).filter(
        DepartmentPO.department_id == department_id,
        DepartmentPO.status != 'Fulfilled',
    ).all()
    for r in open_rows:
        left = (r.quantity_requested or 0) - (r.quantity_fulfilled or 0)
        if left > 0:
            outstanding[r.component_id] = outstanding.get(r.component_id, 0) + left

    job_work, purchase, seen = [], [], set()
    for item in own_items:
        if is_finished_good(item):
            continue
        seen.add(item.id)
        if item.id in recipe_ids:
            job_work.append({**_item_brief(item), "kind": "job_work",
                             "owed_on_internal_pos": round(outstanding.get(item.id, 0), 3)})
        else:
            purchase.append({**_item_brief(item), "kind": "purchase",
                             "owed_on_internal_pos": round(outstanding.get(item.id, 0), 3)})

    # Raw materials this department's own recipes consume.
    for item in own_items:
        # A finished good's parts come from the production departments,
        # not from a supplier to the finished-goods department.
        if item.id not in recipe_ids or is_finished_good(item):
            continue
        bv = BOMVersion.query.filter_by(finished_good_id=item.id, is_active=True).first()
        for row in bv.components:
            if row.component_id in seen or row.component_id in recipe_ids:
                continue
            comp = InternalProduct.query.get(row.component_id)
            if not comp or is_finished_good(comp):
                continue
            seen.add(comp.id)
            purchase.append({**_item_brief(comp), "kind": "purchase", "owed_on_internal_pos": 0})

    return jsonify({"status": "success", "data": job_work + purchase}), 200


@suppliers_bp.route('/materials-preview', methods=['GET'], strict_slashes=False)
@jwt_required
def materials_preview():
    """?product_id=&quantity= -> the materials_to_send list, so the order
    form can show "send the supplier 3.78 kg powder" while typing."""
    product_id = request.args.get('product_id')
    try:
        quantity = float(request.args.get('quantity') or 0)
    except ValueError:
        return jsonify({"error": "quantity must be a number"}), 400
    if not product_id:
        return jsonify({"error": "product_id is required"}), 400
    return jsonify({"status": "success", "data": materials_to_send(product_id, quantity)}), 200

@suppliers_bp.route('/orders', methods=['POST','OPTIONS'], strict_slashes=False)
@jwt_required
@permission_required('manage_suppliers')
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
        try:
            ordered_qty = float(item.get('ordered_qty'))
        except (TypeError, ValueError):
            ordered_qty = 0
        if not item.get('product_id') or ordered_qty <= 0:
            db.session.rollback()
            return jsonify({"error": "Each item needs a product and a quantity greater than zero"}), 400
        line_item = SupplierOrderItem(
            supplier_order_id=new_order.id,
            product_id=item.get('product_id'),
            ordered_qty=ordered_qty
        )
        db.session.add(line_item)

        # Job work: record what we have to send the supplier for this line.
        for m in materials_to_send(item.get('product_id'), ordered_qty):
            db.session.add(SupplierOrderMaterial(
                supplier_order_id=new_order.id,
                product_id=m["product_id"],
                for_product_id=item.get('product_id'),
                quantity=m["quantity"],
            ))

    try:
        db.session.commit()
        return jsonify({"status": "success", "order_id": new_order.id}), 201
    except Exception as e:
        db.session.rollback()
        return jsonify({"error": str(e)}), 500

@suppliers_bp.route('/orders/<order_id>/status', methods=['PUT', 'OPTIONS'], strict_slashes=False)
@jwt_required
@permission_required('manage_suppliers')
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
@permission_required('manage_suppliers')
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

def _sum_materials(rows):
    totals = {}
    for r in rows:
        totals[r.product_id] = totals.get(r.product_id, 0) + (r.quantity or 0)
    out = []
    for pid, qty in totals.items():
        p = InternalProduct.query.get(pid)
        out.append({
            "product_id": pid,
            "item_code": p.item_code if p else None,
            "name": p.name if p else "Unknown Item",
            "unit_of_measure": p.unit_of_measure if p else None,
            "quantity": round(qty, 3),
        })
    return out


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
                "item_code": product.item_code if product else None,
                "unit_of_measure": product.unit_of_measure if product else None,
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
            "items": items_data,
            # Job work: what we send the supplier, summed per material.
            "materials_to_send": _sum_materials(order.materials),
        })
        
    return jsonify({"status": "success", "data": result}), 200