from flask import Blueprint, request, jsonify
from app import db
from app.models.qr_code import QRCodeRegistry
from app.models.quality import QualityInspectionLog

qc_bp = Blueprint('qc', __name__)

@qc_bp.route('/inspect', methods=['POST'])
def submit_inspection():
    """Logs a QC inspection and updates the bin's status"""
    data = request.get_json()
    
    qr_code_string = data.get('qr_code_string')
    inspector_name = data.get('inspector_name')
    status_given = data.get('status_given') # 'Passed' or 'Rejected'
    checklist_data = data.get('checklist_data', {}) # The N1-N5 data
    
    if not all([qr_code_string, inspector_name, status_given]):
        return jsonify({"error": "qr_code_string, inspector_name, and status_given are required"}), 400

    if status_given not in ['Passed', 'Rejected']:
        return jsonify({"error": "Status must be 'Passed' or 'Rejected'"}), 400

    # 1. Find the bin
    bin_record = QRCodeRegistry.query.filter_by(qr_code_string=qr_code_string, is_active=1).first()
    if not bin_record:
        return jsonify({"error": "Invalid or depleted QR Code"}), 404

    # 2. Update the bin's status
    bin_record.qc_status = status_given

    # 3. Save the permanent audit log
    new_log = QualityInspectionLog(
        qr_code_string=qr_code_string,
        inspector_name=inspector_name,
        status_given=status_given,
        checklist_data=checklist_data
    )
    db.session.add(new_log)

    try:
        db.session.commit()
        return jsonify({
            "status": "success",
            "message": f"Bin {qr_code_string} marked as {status_given}",
            "item_id": bin_record.item_id
        }), 201
    except Exception as e:
        db.session.rollback()
        return jsonify({"error": str(e)}), 500