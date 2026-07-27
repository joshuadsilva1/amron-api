from flask import Blueprint, request, jsonify
from app import db
from app.models.client import Client

clients_bp = Blueprint('clients', __name__)

@clients_bp.route('/', methods=['POST'])
def create_client():
    """Adds a new client to the master database"""
    data = request.get_json()
    
    if not data or not data.get('name'):
        return jsonify({"error": "Client name is required"}), 400
        
    # Check if client already exists
    if Client.query.filter_by(name=data['name']).first():
        return jsonify({"error": "Client with this name already exists"}), 400
        
    new_client = Client(
        name=data['name'],
        contact_email=data.get('contact_email'),
        phone=data.get('phone'),
        shipping_address=data.get('shipping_address')
    )
    
    try:
        db.session.add(new_client)
        db.session.commit()
        return jsonify({
            "status": "success",
            "message": "Client created",
            "client_id": new_client.id
        }), 201
    except Exception as e:
        db.session.rollback()
        return jsonify({"error": str(e)}), 500

@clients_bp.route('/', methods=['GET'])
def get_clients():
    """Fetches all active clients"""
    clients = Client.query.filter_by(is_active=1).all()
    result = [{"id": c.id, "name": c.name} for c in clients]
    return jsonify({"status": "success", "clients": result}), 200