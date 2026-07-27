from flask import Blueprint, request, jsonify
from app import db
from app.models.supplier import Supplier

suppliers_bp = Blueprint('suppliers', __name__)

@suppliers_bp.route('/', methods=['POST'])
def create_supplier():
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
def get_suppliers():
    suppliers = Supplier.query.filter_by(is_active=1).all()
    return jsonify({"status": "success", "suppliers": [{"id": s.id, "name": s.name} for s in suppliers]}), 200