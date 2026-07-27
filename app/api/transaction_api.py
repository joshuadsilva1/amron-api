from flask import Blueprint, request, jsonify
from app import db
from app.models.transaction import StockTransaction, InternalChallan
from app.models.item import InternalProduct
from app.models.department import Department
import datetime

transactions_bp = Blueprint('transactions', __name__)


from app.models.client import Client

@transactions_bp.route('/dispatch', methods=['POST'])
def dispatch_goods():
    data = request.get_json()
    
    qr_codes = data.get('qr_codes', [])
    client_id = data.get('client_id') # Changed from client_name
    
    if not qr_codes or not client_id:
        return jsonify({"error": "QR codes and a valid client_id are required"}), 400
        
    # Verify the client exists in the database
    client = Client.query.get(client_id)
    if not client:
        return jsonify({"error": "Invalid client_id"}), 404
        
    dispatched_items = []
    
    for qr_string in qr_codes:
        # 1. Find the active bin
        bin_record = QRCodeRegistry.query.filter_by(qr_code_string=qr_string, is_active=1).first()
        
        if not bin_record:
            db.session.rollback()
            return jsonify({"error": f"Invalid or already dispatched QR Code: {qr_string}"}), 404
            
        # 2. FINAL SAFETY NET: Ensure it actually passed QC before leaving the building
        if bin_record.qc_status != 'Passed':
            db.session.rollback()
            return jsonify({
                "error": f"Dispatch Blocked: Cannot ship bin {qr_string}. QC Status is '{bin_record.qc_status}'."
            }), 403
            
        qty_to_remove = bin_record.quantity
        item_id = bin_record.item_id
        dept_id = bin_record.department_id
        
        # 3. Deduct from Department's loose stock
        dept_stock = DepartmentStock.query.filter_by(item_id=item_id, department_id=dept_id).with_for_update().first()
        if dept_stock and dept_stock.quantity >= qty_to_remove:
            dept_stock.quantity -= qty_to_remove
        else:
            db.session.rollback()
            return jsonify({"error": f"System mismatch: Department does not have enough stock to dispatch bin {qr_string}"}), 500
            
        # 4. Deduct from the Factory Grand Total
        global_item = InternalProduct.query.get(item_id)
        if global_item:
            global_item.current_stock -= qty_to_remove
            
        # 5. Deactivate the QR Code (It has left the building)
        bin_record.is_active = 0
        
        dispatched_items.append({
            "qr": qr_string,
            "item_name": global_item.name if global_item else "Unknown Item",
            "quantity": qty_to_remove
        })
        
    # 6. Commit the final transaction
    try:
        db.session.commit()
        return jsonify({
            "status": "success",
            "message": f"Successfully dispatched {len(qr_codes)} bin(s) to {client.name}",
            "details": dispatched_items
        }), 200
    except Exception as e:
        db.session.rollback()
        return jsonify({"error": str(e)}), 500


# Make sure to import these if they aren't already at the top
from app.models.transaction import InternalChallan, ChallanItem
from app.models.item import InternalProduct
from app.models.department import Department  # Import it from its correct file

@transactions_bp.route('/challan/history', methods=['GET'])
def get_challan_history():
    """Fetches a complete audit trail of all internal factory movements"""
    
    # Get all challans, newest first
    challans = InternalChallan.query.order_by(InternalChallan.created_at.desc()).all()
    
    history_log = []
    
    for challan in challans:
        # Resolve the department names (handling cases where a department might have been deleted)
        from_dept = Department.query.get(challan.from_department_id)
        to_dept = Department.query.get(challan.to_department_id)
        
        from_dept_name = from_dept.name if from_dept else "Unknown Origin"
        to_dept_name = to_dept.name if to_dept else "Unknown Destination"
        
        # Fetch the items that were inside this specific challan
        items_moved = []
        challan_items = ChallanItem.query.filter_by(challan_id=challan.id).all()
        
        for c_item in challan_items:
            product = InternalProduct.query.get(c_item.item_id)
            items_moved.append({
                "item_name": product.name if product else "Unknown Item",
                "item_code": product.item_code if product else "N/A",
                "quantity": c_item.quantity
            })
            
        # Build the final record
        history_log.append({
            "challan_number": challan.challan_number,
            "movement_type": challan.movement_type,
            "origin": from_dept_name,
            "destination": to_dept_name,
            "created_by": challan.created_by,
            "timestamp": challan.created_at.isoformat(),
            "items": items_moved
        })
        
    return jsonify({
        "status": "success",
        "total_records": len(history_log),
        "history": history_log
    }), 200

from app.models.adjustment import InventoryAdjustment

@transactions_bp.route('/adjust', methods=['POST'])
def adjust_stock():
    """Handles manual inventory corrections (scrap, loss, audits)"""
    data = request.get_json()
    
    item_id = data.get('item_id')
    department_id = data.get('department_id')
    adjustment_qty = data.get('adjustment_qty') # Can be negative (scrap) or positive (audit correction)
    reason = data.get('reason')
    reported_by = data.get('reported_by', 'System Admin')
    qr_code_string = data.get('qr_code_string') # Optional
    
    if not all([item_id, department_id, adjustment_qty, reason]):
        return jsonify({"error": "item_id, department_id, adjustment_qty, and reason are required"}), 400

    try:
        adjustment_qty = float(adjustment_qty)
    except ValueError:
        return jsonify({"error": "adjustment_qty must be a number"}), 400

    # 1. Update the Department's loose stock
    dept_stock = DepartmentStock.query.filter_by(
        item_id=item_id, department_id=department_id
    ).with_for_update().first()
    
    if not dept_stock:
        if adjustment_qty < 0:
            return jsonify({"error": "Cannot deduct stock. Department has 0 quantity."}), 400
        dept_stock = DepartmentStock(item_id=item_id, department_id=department_id, quantity=0)
        db.session.add(dept_stock)
        
    if dept_stock.quantity + adjustment_qty < 0:
        return jsonify({"error": f"Adjustment blocked. Department only has {dept_stock.quantity} in stock."}), 400
        
    dept_stock.quantity += adjustment_qty

    # 2. Update Factory Grand Total
    global_item = InternalProduct.query.get(item_id)
    if global_item:
        global_item.current_stock += adjustment_qty

    # 3. If a specific QR code bin was damaged, adjust its quantity too
    if qr_code_string:
        bin_record = QRCodeRegistry.query.filter_by(qr_code_string=qr_code_string, is_active=1).first()
        if bin_record:
            bin_record.quantity += adjustment_qty
            # If the bin is now empty, destroy the QR code
            if bin_record.quantity <= 0:
                bin_record.quantity = 0
                bin_record.is_active = 0 

    # 4. Log the audit record
    new_adjustment = InventoryAdjustment(
        item_id=item_id,
        department_id=department_id,
        adjustment_qty=adjustment_qty,
        reason=reason,
        qr_code_string=qr_code_string,
        reported_by=reported_by
    )
    db.session.add(new_adjustment)

    try:
        db.session.commit()
        return jsonify({
            "status": "success",
            "message": f"Successfully adjusted stock by {adjustment_qty} units. Reason: {reason}"
        }), 201
    except Exception as e:
        db.session.rollback()
        return jsonify({"error": str(e)}), 500

from app.models.department import Department

@transactions_bp.route('/bin/<string:qr_code_string>', methods=['GET'])
def get_bin_details(qr_code_string):
    """Fetches all live data for a specific physical bin"""
    
    # 1. Find the bin
    bin_record = QRCodeRegistry.query.filter_by(qr_code_string=qr_code_string).first()
    
    if not bin_record:
        return jsonify({"error": "QR Code not found in registry"}), 404
        
    # 2. Get the readable names for the Item and Department
    item = InternalProduct.query.get(bin_record.item_id)
    department = Department.query.get(bin_record.department_id)
    
    if not item or not department:
        return jsonify({"error": "Database integrity error: Linked item or department missing"}), 500

    # 3. Return the full profile to the React Native app
    return jsonify({
        "status": "success",
        "data": {
            "qr_code_string": bin_record.qr_code_string,
            "item_name": item.name,
            "item_code": item.item_code,
            "category": item.category,
            "quantity": bin_record.quantity,
            "unit_of_measure": item.unit_of_measure,
            "current_department": department.name,
            "qc_status": bin_record.qc_status,
            "is_active": True if bin_record.is_active == 1 else False,
            "created_at": bin_record.created_at
        }
    }), 200

from datetime import datetime

@transactions_bp.route('/challan/scan', methods=['POST'])
def scanner_challan():
    """Moves physical bins (QR codes) from one department to another"""
    data = request.get_json()
    
    from_department_id = data.get('from_department_id')
    to_department_id = data.get('to_department_id')
    qr_codes = data.get('qr_codes', []) # Expecting a list of strings: ["BIN-FG-BASE-01-123456"]
    
    if not all([from_department_id, to_department_id]) or not qr_codes:
        return jsonify({"error": "Origin, destination, and at least one QR code are required"}), 400

    # 1. VERIFY THE ROUTE
    valid_route = DepartmentRoute.query.filter_by(
        from_department_id=from_department_id,
        to_department_id=to_department_id,
        is_active=1
    ).first()
    
    if not valid_route:
        return jsonify({"error": "Transaction Blocked: Unauthorized route."}), 403

    # 2. CREATE THE CHALLAN RECORD
    date_str = datetime.now().strftime("%Y%m%d")
    unique_suffix = datetime.now().strftime("%H%M%S")
    challan_num = f"SCAN-CH-{date_str}-{unique_suffix}"

    new_challan = InternalChallan(
        challan_number=challan_num,
        movement_type="Scanner Transfer",
        from_department_id=from_department_id,
        to_department_id=to_department_id,
        created_by=data.get('user_name', 'Scanner App')
    )
    db.session.add(new_challan)
    db.session.flush()

    # 3. PROCESS EACH SCANNED BIN
    for qr_string in qr_codes:
        # Find the physical bin
        # Find the physical bin
        bin_record = QRCodeRegistry.query.filter_by(qr_code_string=qr_string, is_active=1).first()
        
        if not bin_record:
            db.session.rollback()
            return jsonify({"error": f"Invalid or depleted QR Code: {qr_string}"}), 404
            
        # --- NEW QC SAFETY CHECK ---
        if bin_record.qc_status != 'Passed':
            db.session.rollback()
            return jsonify({
                "error": f"Transaction Blocked: Bin {qr_string} cannot be moved because its QC status is '{bin_record.qc_status}'."
            }), 403
        # ---------------------------
        
        if bin_record.department_id != from_department_id:
            db.session.rollback()
            return jsonify({"error": f"Bin {qr_string} is not currently located in the sending department!"}), 400

        qty_to_move = bin_record.quantity
        item_id = bin_record.item_id

        # Update Sender's Loose Stock
        sender_stock = DepartmentStock.query.filter_by(
            item_id=item_id, department_id=from_department_id
        ).with_for_update().first()
        
        if not sender_stock or sender_stock.quantity < qty_to_move:
            db.session.rollback()
            return jsonify({"error": f"System mismatch: Department doesn't have enough loose stock to move bin {qr_string}"}), 500
            
        sender_stock.quantity -= qty_to_move

        # Update Receiver's Loose Stock
        receiver_stock = DepartmentStock.query.filter_by(
            item_id=item_id, department_id=to_department_id
        ).first()
        
        if receiver_stock:
            receiver_stock.quantity += qty_to_move
        else:
            receiver_stock = DepartmentStock(item_id=item_id, department_id=to_department_id, quantity=qty_to_move)
            db.session.add(receiver_stock)

        # Update the Bin's Physical Location
        bin_record.department_id = to_department_id

        # Log it on the Challan
        new_challan_item = ChallanItem(challan_id=new_challan.id, item_id=item_id, quantity=qty_to_move)
        db.session.add(new_challan_item)

    # 4. COMMIT EVERYTHING
    try:
        db.session.commit()
        return jsonify({
            "status": "success", 
            "message": f"Successfully transferred {len(qr_codes)} bin(s)", 
            "challan_number": new_challan.challan_number
        }), 201
    except Exception as e:
        db.session.rollback()
        return jsonify({"error": str(e)}), 500

# ==========================================
# 1. AUTOMATED QR SCANNING
# ==========================================
@transactions_bp.route('/scan', methods=['POST'])
def handle_qr_scan():
    data = request.get_json()
    qr_uuid = data.get('qr_uuid')
    transaction_type = data.get('transaction_type')
    department_id = data.get('department_id') # Changed to expect ID
    
    if not all([qr_uuid, transaction_type, department_id]):
        return jsonify({"error": "Missing required fields"}), 400

    # Validate Department exists
    if not Department.query.get(department_id):
        return jsonify({"error": "Invalid department ID"}), 404

    qr_code = QRCodeRegistry.query.filter_by(qr_uuid=qr_uuid).first()
    if not qr_code:
        return jsonify({"error": "Invalid QR Code."}), 404

    if qr_code.is_consumed == 1:
        return jsonify({"error": "QR code already consumed."}), 400

    product = InternalProduct.query.get(qr_code.product_id)
    if not product:
        return jsonify({"error": "Product not found."}), 404

    new_transaction = StockTransaction(
        product_id=product.id,
        department_id=department_id, # Updated
        transaction_type=transaction_type.upper(),
        quantity=qr_code.quantity,
        qr_id=qr_code.id,
        is_manual=0,
        created_by=data.get('user_name', 'System')
    )

    if transaction_type.upper() == 'IN':
        product.current_stock += qr_code.quantity
    elif transaction_type.upper() == 'OUT':
        product.current_stock -= qr_code.quantity
        qr_code.is_consumed = 1 

    try:
        db.session.add(new_transaction)
        db.session.commit()
        return jsonify({"status": "success", "message": f"Successfully logged {transaction_type}"}), 200
    except Exception as e:
        db.session.rollback()
        return jsonify({"error": str(e)}), 500


# ==========================================
# 2. MANUAL STOCK ADJUSTMENTS
# ==========================================
@transactions_bp.route('/manual', methods=['POST'])
def manual_adjustment():
    data = request.get_json()
    
    product_id = data.get('product_id')
    transaction_type = data.get('transaction_type')
    quantity = data.get('quantity')
    department_id = data.get('department_id') # Changed to expect ID
    reason = data.get('reason')
    
    if not all([product_id, transaction_type, quantity, department_id, reason]):
        return jsonify({"error": "Product, type, quantity, department ID, and reason are required"}), 400

    if not Department.query.get(department_id):
        return jsonify({"error": "Invalid department ID"}), 404

    product = InternalProduct.query.get(product_id)
    if not product:
        return jsonify({"error": "Product not found"}), 404

    new_transaction = StockTransaction(
        product_id=product.id,
        department_id=department_id, # Updated
        transaction_type=transaction_type.upper(),
        quantity=int(quantity),
        is_manual=1,
        reason=reason,
        reference_number=data.get('reference_number'),
        created_by=data.get('user_name', 'Admin')
    )

    if transaction_type.upper() == 'IN':
        product.current_stock += int(quantity)
    elif transaction_type.upper() == 'OUT':
        product.current_stock -= int(quantity)

    try:
        db.session.add(new_transaction)
        db.session.commit()
        return jsonify({"status": "success", "message": f"Manual {transaction_type} logged."}), 200
    except Exception as e:
        db.session.rollback()
        return jsonify({"error": str(e)}), 500
    



from flask import request, jsonify
from app import db
# Make sure these are imported at the top!
from app.models.item import InternalProduct, DepartmentStock
from app.models.department import Department

@transactions_bp.route('/receive', methods=['POST'])
def receive_stock():
    """Receives new raw materials or stock into a specific department"""
    data = request.get_json()
    
    item_id = data.get('item_id')
    department_id = data.get('department_id')
    quantity = data.get('quantity')
    
    # 1. Validation
    if not all([item_id, department_id, quantity]):
        return jsonify({"error": "item_id, department_id, and quantity are required"}), 400
        
    try:
        quantity = float(quantity)
        if quantity <= 0:
            return jsonify({"error": "Quantity must be greater than zero"}), 400
    except ValueError:
        return jsonify({"error": "Quantity must be a number"}), 400

    item = InternalProduct.query.get(item_id)
    department = Department.query.get(department_id)
    
    if not item:
        return jsonify({"error": "Item not found"}), 404
    if not department:
        return jsonify({"error": "Department not found"}), 404

    # 2. Update the specific Department's Stock
    dept_stock = DepartmentStock.query.filter_by(
        item_id=item_id, 
        department_id=department_id
    ).first()
    
    if dept_stock:
        # If the item is already in this room, just add to the pile
        dept_stock.quantity += quantity
    else:
        # If this is the first time this item is in this room, create a new record
        dept_stock = DepartmentStock(
            item_id=item_id,
            department_id=department_id,
            quantity=quantity
        )
        db.session.add(dept_stock)

    # 3. Update the Factory's Grand Total
    item.current_stock += quantity

    try:
        db.session.commit()
        return jsonify({
            "status": "success",
            "message": f"Successfully received {quantity} {item.unit_of_measure} of {item.name} into {department.name}.",
            "new_department_stock": dept_stock.quantity,
            "new_factory_total": item.current_stock
        }), 200
    except Exception as e:
        db.session.rollback()
        return jsonify({"error": str(e)}), 500



from app.models.department import Department, DepartmentRoute
from app.models.item import InternalProduct, DepartmentStock
from app.models.transaction import ChallanItem
# Make sure InternalChallan and ChallanItem are imported here too!

@transactions_bp.route('/challan', methods=['POST'])
def generate_challan():
    data = request.get_json()
    
    from_department_id = data.get('from_department_id')
    to_department_id = data.get('to_department_id')
    movement_type = data.get('movement_type', 'Internal')
    items = data.get('items', []) # Expecting a list: [{"item_id": "...", "quantity": 50}]
    
    if not all([from_department_id, to_department_id]) or not items:
        return jsonify({"error": "Origin, destination, and at least one item are required"}), 400

    # 1. THE ROUTE SAFETY NET
    valid_route = DepartmentRoute.query.filter_by(
        from_department_id=from_department_id,
        to_department_id=to_department_id,
        is_active=1
    ).first()
    
    if not valid_route:
        return jsonify({"error": "Transaction Blocked: Unauthorized route."}), 403

    # 2. CREATE THE CHALLAN RECORD
    date_str = datetime.datetime.now().strftime("%Y%m%d")
    unique_suffix = datetime.datetime.now().strftime("%H%M%S")
    challan_num = f"CH-{date_str}-{unique_suffix}"

    new_challan = InternalChallan(
        challan_number=challan_num,
        movement_type=movement_type,
        from_department_id=from_department_id,
        to_department_id=to_department_id,
        created_by=data.get('user_name', 'System')
    )
    db.session.add(new_challan)
    db.session.flush() # Gets the new_challan.id without permanently committing yet

    # 3. THE INVENTORY SAFETY CHECK & TRANSFER
    for line_item in items:
        item_id = line_item.get('item_id')
        qty_to_move = float(line_item.get('quantity', 0))
        
        if qty_to_move <= 0:
            db.session.rollback()
            return jsonify({"error": "Quantity must be greater than zero"}), 400

        # Check sender's stock
        sender_stock = DepartmentStock.query.filter_by(
            item_id=item_id, department_id=from_department_id
        ).with_for_update().first() # with_for_update() locks the row so two quick scans don't double-spend

        if not sender_stock or sender_stock.quantity < qty_to_move:
            db.session.rollback()
            item_info = InternalProduct.query.get(item_id)
            item_name = item_info.name if item_info else "Unknown Item"
            return jsonify({
                "error": f"Insufficient stock. Department only has {sender_stock.quantity if sender_stock else 0} of {item_name}."
            }), 400

        # Deduct from sender
        sender_stock.quantity -= qty_to_move

        # Add to receiver
        receiver_stock = DepartmentStock.query.filter_by(
            item_id=item_id, department_id=to_department_id
        ).first()
        
        if receiver_stock:
            receiver_stock.quantity += qty_to_move
        else:
            receiver_stock = DepartmentStock(item_id=item_id, department_id=to_department_id, quantity=qty_to_move)
            db.session.add(receiver_stock)

        # Log the line item on the challan
        new_challan_item = ChallanItem(challan_id=new_challan.id, item_id=item_id, quantity=qty_to_move)
        db.session.add(new_challan_item)

    # 4. COMMIT EVERYTHING
    try:
        db.session.commit()
        return jsonify({
            "status": "success", 
            "message": "Transfer complete", 
            "challan_number": new_challan.challan_number
        }), 201
    except Exception as e:
        db.session.rollback()
        return jsonify({"error": str(e)}), 500
@transactions_bp.route('/challan/verify', methods=['PUT'])
def verify_challan():
    data = request.get_json()
    
    challan_id = data.get('challan_id')
    chalan_image_url = data.get('chalan_image_url')
    user_name = data.get('user_name', 'System')
    
    if not challan_id or not chalan_image_url:
        return jsonify({"error": "Challan ID and Photo URL are required for verification"}), 400

    challan = InternalChallan.query.get(challan_id)
    if not challan:
        return jsonify({"error": "Challan not found"}), 404
        
    if challan.status == 'Verified':
        return jsonify({"error": "This challan has already been verified."}), 400

    challan.status = 'Verified'
    challan.chalan_image_url = chalan_image_url

    try:
        db.session.commit()
        return jsonify({"status": "success", "message": f"Challan verified by {user_name}."}), 200
    except Exception as e:
        db.session.rollback()
        return jsonify({"error": str(e)}), 500

# Add this to your imports at the top
from app.models.recipe import Recipe, RecipeItem

@transactions_bp.route('/produce', methods=['POST'])
def log_production():
    """Logs the manufacturing of a product, consuming raw materials based on the BoM"""
    data = request.get_json()
    
    department_id = data.get('department_id')
    item_id = data.get('item_id') # The finished good being created
    quantity_produced = data.get('quantity')
    
    if not all([department_id, item_id, quantity_produced]):
        return jsonify({"error": "department_id, item_id, and quantity are required"}), 400
        
    try:
        quantity_produced = float(quantity_produced)
        if quantity_produced <= 0:
            return jsonify({"error": "Quantity must be greater than zero"}), 400
    except ValueError:
        return jsonify({"error": "Quantity must be a number"}), 400

    # 1. Verify the Recipe Exists
    recipe = Recipe.query.filter_by(output_item_id=item_id, is_active=1).first()
    if not recipe:
        return jsonify({"error": "No recipe found for this item. Cannot manufacture."}), 404
        
    # 2. THE SAFETY NET: Check stock for ALL ingredients before deducting anything
    ingredients = RecipeItem.query.filter_by(recipe_id=recipe.id).all()
    
    # We store the records here to update them efficiently in the next step
    stock_updates = []
    
    for ing in ingredients:
        total_needed = ing.quantity_required * quantity_produced
        
        # Look at the department's physical shelf
        dept_stock = DepartmentStock.query.filter_by(
            item_id=ing.input_item_id, 
            department_id=department_id
        ).with_for_update().first() # Locks the row to prevent double-spending
        
        if not dept_stock or dept_stock.quantity < total_needed:
            db.session.rollback()
            input_item = InternalProduct.query.get(ing.input_item_id)
            item_name = input_item.name if input_item else "Unknown Material"
            available = dept_stock.quantity if dept_stock else 0.0
            return jsonify({
                "error": f"Insufficient raw materials. Need {total_needed} {input_item.unit_of_measure} of {item_name}, but department only has {available}."
            }), 400
            
        stock_updates.append({
            "record": dept_stock,
            "needed": total_needed,
            "input_item_id": ing.input_item_id
        })

    # 3. CONSUME RAW MATERIALS
    for update in stock_updates:
        # Deduct from the department's shelf
        update["record"].quantity -= update["needed"]
        
        # Deduct from the factory's grand total (it is permanently transformed)
        raw_item = InternalProduct.query.get(update["input_item_id"])
        if raw_item:
            raw_item.current_stock -= update["needed"]

    # 4. ADD THE FINISHED GOOD
    fg_stock = DepartmentStock.query.filter_by(
        item_id=item_id, 
        department_id=department_id
    ).first()
    
    if fg_stock:
        fg_stock.quantity += quantity_produced
    else:
        fg_stock = DepartmentStock(
            item_id=item_id,
            department_id=department_id,
            quantity=quantity_produced
        )
        db.session.add(fg_stock)
        
    # Add the newly created good to the factory's grand total
    fg_item = InternalProduct.query.get(item_id)
    if fg_item:
        fg_item.current_stock += quantity_produced

    # 5. COMMIT TRANSACTION
    try:
        db.session.commit()
        return jsonify({
            "status": "success",
            "message": f"Successfully manufactured {quantity_produced} units of {fg_item.name}.",
            "raw_materials_consumed": len(ingredients)
        }), 201
    except Exception as e:
        db.session.rollback()
        return jsonify({"error": str(e)}), 500    

# Add this to your imports at the top
from app.models.qr_code import QRCodeRegistry
import time

@transactions_bp.route('/generate-qr', methods=['POST'])
def generate_qr():
    """Mints a new QR code for a physical bin of inventory"""
    data = request.get_json()
    
    item_id = data.get('item_id')
    department_id = data.get('department_id')
    quantity = data.get('quantity')
    
    if not all([item_id, department_id, quantity]):
        return jsonify({"error": "item_id, department_id, and quantity are required"}), 400
        
    try:
        quantity = float(quantity)
        if quantity <= 0:
            return jsonify({"error": "Quantity must be greater than zero"}), 400
    except ValueError:
        return jsonify({"error": "Quantity must be a number"}), 400

    item = InternalProduct.query.get(item_id)
    if not item:
        return jsonify({"error": "Item not found"}), 404

    # 1. VERIFY INVENTORY: Does this department actually have enough loose stock to put in this bin?
    dept_stock = DepartmentStock.query.filter_by(
        item_id=item_id, 
        department_id=department_id
    ).first()
    
    if not dept_stock or dept_stock.quantity < quantity:
        available = dept_stock.quantity if dept_stock else 0.0
        return jsonify({
            "error": f"Cannot print QR code. Department only has {available} {item.unit_of_measure} of {item.name}."
        }), 400

    # 2. MINT THE UNIQUE STRING
    # Example output: BIN-FG-BASE-01-849201
    timestamp_suffix = str(int(time.time() * 1000))[-6:] 
    item_prefix = item.item_code if item.item_code else "ITEM"
    unique_qr_string = f"BIN-{item_prefix}-{timestamp_suffix}"

    # 3. REGISTER THE BIN
    new_qr = QRCodeRegistry(
        qr_code_string=unique_qr_string,
        item_id=item_id,
        department_id=department_id,
        quantity=quantity
    )
    
    try:
        db.session.add(new_qr)
        db.session.commit()
        return jsonify({
            "status": "success",
            "qr_code_string": unique_qr_string,
            "message": f"QR code generated for {quantity} {item.unit_of_measure} of {item.name}"
        }), 201
    except Exception as e:
        db.session.rollback()
        return jsonify({"error": str(e)}), 500
    