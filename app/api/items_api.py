from flask import Blueprint, request, jsonify
from app import db
from app.models.item import InternalProduct

items_bp = Blueprint('items', __name__)

@items_bp.route('/', methods=['GET'])
def get_items():
    """Fetch active items. Optional: Filter by ?category=Raw Material"""
    category_filter = request.args.get('category')
    query = InternalProduct.query.filter_by(is_active=1)
    
    if category_filter:
        query = query.filter_by(category=category_filter)
        
    items = query.all()
    
    result = [{
        "id": i.id,
        "item_code": i.item_code,
        "oem_company_code": i.oem_company_code,
        "name": i.name,
        "category": i.category,
        "unit_of_measure": i.unit_of_measure,
        "current_stock": i.current_stock
    } for i in items]
    
    return jsonify({"status": "success", "data": result}), 200

@items_bp.route('/', methods=['POST'])
def create_item():
    """Create a new raw material or product."""
    data = request.get_json()
    
    name = data.get('name')
    category = data.get('category')
    item_code = data.get('item_code')
    oem_company_code = data.get('oem_company_code') # Added OEM code
    uom = data.get('unit_of_measure', 'pcs')
    starting_stock = data.get('current_stock', 0.0)
    
    if not name or not category:
        return jsonify({"error": "Item name and category are required"}), 400
        
    if item_code:
        existing = InternalProduct.query.filter_by(item_code=item_code).first()
        if existing:
            return jsonify({"error": f"Item code {item_code} already exists"}), 409
            
    new_item = InternalProduct(
        name=name,
        category=category,
        item_code=item_code,
        oem_company_code=oem_company_code, # Mapped to DB
        unit_of_measure=uom,
        current_stock=float(starting_stock)
    )
    
    try:
        db.session.add(new_item)
        db.session.commit()
        return jsonify({
            "status": "success", 
            "message": f"Item {name} created successfully", 
            "id": new_item.id
        }), 201
    except Exception as e:
        db.session.rollback()
        return jsonify({"error": str(e)}), 500