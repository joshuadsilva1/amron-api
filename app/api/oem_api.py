from flask import Blueprint, request, jsonify
from app import db
from app.models.item import OEMCompanyCode, InternalProduct
from app.models.client import Client
from app.core.decorators import jwt_required

oem_bp = Blueprint('oem', __name__)

@oem_bp.route('/', methods=['GET'], strict_slashes=False)
@jwt_required
def get_mappings():
    """Fetches all OEM mappings and resolves the foreign keys to readable names"""
    mappings = OEMCompanyCode.query.all()
    result = []

    for m in mappings:
        client = Client.query.get(m.client_id)
        product = InternalProduct.query.get(m.internal_product_id)

        result.append({
            "id": m.id,
            "client_id": m.client_id,
            "party_name": client.name if client else "Unknown Client",
            "party_code": m.client_product_code,
            "client_product_name": m.client_product_name,
            "internal_product": product.name if product else "Unknown Product",
            "internal_code": product.item_code if product else None,
            "box_type": m.box_type,
            "pieces_per_box": m.pieces_per_box,
            "pouch_type": m.pouch_type,
            "pieces_per_pouch": m.pieces_per_pouch,
            "carton_type": m.carton_type,
            "pieces_per_carton": m.pieces_per_carton,
            "label_type": m.label_type,
        })

    return jsonify({"status": "success", "mappings": result}), 200

@oem_bp.route('/', methods=['POST'], strict_slashes=False)
@jwt_required
def create_mapping():
    """Creates a new OEM mapping by looking up the client and product names"""
    data = request.get_json()

    party_name = data.get('party_name')
    party_code = data.get('party_code')
    internal_product_name = data.get('internal_product')

    if not all([party_name, party_code, internal_product_name]):
        return jsonify({"error": "Party name, Party Code, and Internal Product are required"}), 400

    client = Client.query.filter_by(name=party_name).first()
    if not client:
        return jsonify({"error": f"Client '{party_name}' not found. Please add them in the Clients tab first."}), 404

    product = InternalProduct.query.filter_by(name=internal_product_name).first()
    if not product:
        return jsonify({"error": f"Internal Product '{internal_product_name}' not found."}), 404

    new_mapping = OEMCompanyCode(
        client_id=client.id,
        internal_product_id=product.id,
        client_product_code=party_code,
        client_product_name=data.get('client_product_name'),
        box_type=data.get('box_type'),
        pieces_per_box=data.get('pieces_per_box'),
        pouch_type=data.get('pouch_type'),
        pieces_per_pouch=data.get('pieces_per_pouch'),
        carton_type=data.get('carton_type'),
        pieces_per_carton=data.get('pieces_per_carton'),
        label_type=data.get('label_type'),
    )

    try:
        db.session.add(new_mapping)
        db.session.commit()
        return jsonify({
            "status": "success",
            "message": "Mapping created",
            "mapping_id": new_mapping.id
        }), 201
    except Exception as e:
        db.session.rollback()
        return jsonify({"error": str(e)}), 500


@oem_bp.route('/lookup', methods=['GET'], strict_slashes=False)
@jwt_required
def lookup_mapping():
    """
    Resolve a client's OEM product code straight to a mapping_id, so the PO
    entry screen can convert 'their code' -> internal code as the user types.
    Usage: GET /api/oem/lookup?client_id=...&party_code=HA101
    """
    client_id = request.args.get('client_id')
    party_code = request.args.get('party_code')

    if not client_id or not party_code:
        return jsonify({"error": "client_id and party_code are required"}), 400

    mapping = OEMCompanyCode.query.filter_by(
        client_id=client_id, client_product_code=party_code
    ).first()

    if not mapping:
        return jsonify({"error": f"No mapping found for code '{party_code}' for this client. Create one first in OEM mappings."}), 404

    product = InternalProduct.query.get(mapping.internal_product_id)
    return jsonify({
        "status": "success",
        "mapping_id": mapping.id,
        "internal_code": product.item_code if product else None,
        "internal_name": product.name if product else None,
    }), 200