import os
import uuid
from flask import Blueprint, request, jsonify, current_app
from werkzeug.utils import secure_filename
from app import db
from app.models.qr_code import QRCodeRegistry
from app.models.quality import QualityInspectionLog
from app.models.qc_template import QCTemplate, QCSection, QCCheckpoint, QCInspection, QCObservation
from app.core.decorators import jwt_required
from app.core.storage import upload_file

qc_bp = Blueprint('qc', __name__)

ALLOWED_IMAGE_EXT = {'.jpg', '.jpeg', '.png', '.webp', '.heic'}

@qc_bp.route('/inspect', methods=['POST'])

@jwt_required
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


# ==========================================
# QC TEMPLATES (Admin authoring)
# ==========================================

def _serialize_checkpoint(cp):
    return {
        "id": cp.id,
        "serial_no": cp.serial_no,
        "check_point": cp.check_point,
        "standard_criteria": cp.standard_criteria,
        "entry_labels": cp.entry_labels,
        "sort_order": cp.sort_order,
    }


def _serialize_section(section):
    return {
        "id": section.id,
        "title": section.title,
        "sort_order": section.sort_order,
        "checkpoints": [_serialize_checkpoint(cp) for cp in section.checkpoints],
    }


def _serialize_template(template, with_sections=False):
    data = {
        "id": template.id,
        "name": template.name,
        "qc_type": template.qc_type,
        "category": template.category,
        "header_fields": template.header_fields,
        "is_active": template.is_active == 1,
    }
    if with_sections:
        data["sections"] = [_serialize_section(s) for s in template.sections]
    return data


@qc_bp.route('/templates', methods=['GET', 'OPTIONS'], strict_slashes=False)
@jwt_required
def list_templates():
    if request.method == 'OPTIONS':
        return jsonify({}), 200

    query = QCTemplate.query.filter_by(is_active=1)
    qc_type = request.args.get('qc_type')
    category = request.args.get('category')
    if qc_type:
        query = query.filter_by(qc_type=qc_type)
    if category:
        query = query.filter(db.func.lower(QCTemplate.category) == category.strip().lower())

    templates = query.order_by(QCTemplate.name).all()
    return jsonify({"status": "success", "data": [_serialize_template(t) for t in templates]}), 200


@qc_bp.route('/templates/<template_id>', methods=['GET', 'OPTIONS'], strict_slashes=False)
@jwt_required
def get_template(template_id):
    if request.method == 'OPTIONS':
        return jsonify({}), 200

    template = QCTemplate.query.get(template_id)
    if not template:
        return jsonify({"error": "Template not found"}), 404
    return jsonify({"status": "success", "data": _serialize_template(template, with_sections=True)}), 200


@qc_bp.route('/templates', methods=['POST', 'OPTIONS'], strict_slashes=False)
@jwt_required
def create_template():
    if request.method == 'OPTIONS':
        return jsonify({}), 200

    data = request.get_json(silent=True) or {}
    name = data.get('name')
    qc_type = data.get('qc_type')

    if not name or not qc_type:
        return jsonify({"error": "name and qc_type are required"}), 400
    if qc_type not in ['IQC', 'PQC', 'OQC', 'ASSEMBLY']:
        return jsonify({"error": "qc_type must be one of IQC, PQC, OQC, ASSEMBLY"}), 400

    template = QCTemplate(
        name=name,
        qc_type=qc_type,
        category=data.get('category'),
        header_fields=data.get('header_fields', []),
    )

    try:
        db.session.add(template)
        db.session.commit()
        return jsonify({"status": "success", "message": "Template created", "id": template.id}), 201
    except Exception as e:
        db.session.rollback()
        return jsonify({"error": str(e)}), 500


@qc_bp.route('/templates/<template_id>', methods=['PUT', 'OPTIONS'], strict_slashes=False)
@jwt_required
def update_template(template_id):
    if request.method == 'OPTIONS':
        return jsonify({}), 200

    template = QCTemplate.query.get(template_id)
    if not template:
        return jsonify({"error": "Template not found"}), 404

    data = request.get_json(silent=True) or {}
    if 'name' in data: template.name = data['name']
    if 'category' in data: template.category = data['category']
    if 'header_fields' in data: template.header_fields = data['header_fields']
    if 'qc_type' in data:
        if data['qc_type'] not in ['IQC', 'PQC', 'OQC', 'ASSEMBLY']:
            return jsonify({"error": "qc_type must be one of IQC, PQC, OQC, ASSEMBLY"}), 400
        template.qc_type = data['qc_type']

    try:
        db.session.commit()
        return jsonify({"status": "success", "message": "Template updated"}), 200
    except Exception as e:
        db.session.rollback()
        return jsonify({"error": str(e)}), 500


@qc_bp.route('/templates/<template_id>', methods=['DELETE', 'OPTIONS'], strict_slashes=False)
@jwt_required
def deactivate_template(template_id):
    if request.method == 'OPTIONS':
        return jsonify({}), 200

    template = QCTemplate.query.get(template_id)
    if not template:
        return jsonify({"error": "Template not found"}), 404

    # Soft delete — past inspections still reference this template.
    template.is_active = 0

    try:
        db.session.commit()
        return jsonify({"status": "success", "message": "Template deactivated"}), 200
    except Exception as e:
        db.session.rollback()
        return jsonify({"error": str(e)}), 500


@qc_bp.route('/templates/<template_id>/sections', methods=['POST', 'OPTIONS'], strict_slashes=False)
@jwt_required
def add_section(template_id):
    if request.method == 'OPTIONS':
        return jsonify({}), 200

    template = QCTemplate.query.get(template_id)
    if not template:
        return jsonify({"error": "Template not found"}), 404

    data = request.get_json(silent=True) or {}
    title = data.get('title')
    if not title:
        return jsonify({"error": "title is required"}), 400

    max_order = db.session.query(db.func.max(QCSection.sort_order)).filter_by(template_id=template_id).scalar()
    section = QCSection(
        template_id=template_id,
        title=title,
        sort_order=data.get('sort_order', (max_order or 0) + 1),
    )

    try:
        db.session.add(section)
        db.session.commit()
        return jsonify({"status": "success", "message": "Section added", "id": section.id}), 201
    except Exception as e:
        db.session.rollback()
        return jsonify({"error": str(e)}), 500


@qc_bp.route('/sections/<section_id>', methods=['PUT', 'OPTIONS'], strict_slashes=False)
@jwt_required
def update_section(section_id):
    if request.method == 'OPTIONS':
        return jsonify({}), 200

    section = QCSection.query.get(section_id)
    if not section:
        return jsonify({"error": "Section not found"}), 404

    data = request.get_json(silent=True) or {}
    if 'title' in data: section.title = data['title']
    if 'sort_order' in data: section.sort_order = data['sort_order']

    try:
        db.session.commit()
        return jsonify({"status": "success", "message": "Section updated"}), 200
    except Exception as e:
        db.session.rollback()
        return jsonify({"error": str(e)}), 500


@qc_bp.route('/sections/<section_id>', methods=['DELETE', 'OPTIONS'], strict_slashes=False)
@jwt_required
def delete_section(section_id):
    if request.method == 'OPTIONS':
        return jsonify({}), 200

    section = QCSection.query.get(section_id)
    if not section:
        return jsonify({"error": "Section not found"}), 404

    try:
        db.session.delete(section)
        db.session.commit()
        return jsonify({"status": "success", "message": "Section deleted"}), 200
    except Exception as e:
        db.session.rollback()
        return jsonify({"error": str(e)}), 500


@qc_bp.route('/sections/<section_id>/checkpoints', methods=['POST', 'OPTIONS'], strict_slashes=False)
@jwt_required
def add_checkpoint(section_id):
    if request.method == 'OPTIONS':
        return jsonify({}), 200

    section = QCSection.query.get(section_id)
    if not section:
        return jsonify({"error": "Section not found"}), 404

    data = request.get_json(silent=True) or {}
    check_point = data.get('check_point')
    if not check_point:
        return jsonify({"error": "check_point is required"}), 400

    max_order = db.session.query(db.func.max(QCCheckpoint.sort_order)).filter_by(section_id=section_id).scalar()
    checkpoint = QCCheckpoint(
        section_id=section_id,
        serial_no=data.get('serial_no'),
        check_point=check_point,
        standard_criteria=data.get('standard_criteria'),
        entry_labels=data.get('entry_labels', ["Result"]),
        sort_order=data.get('sort_order', (max_order or 0) + 1),
    )

    try:
        db.session.add(checkpoint)
        db.session.commit()
        return jsonify({"status": "success", "message": "Checkpoint added", "id": checkpoint.id}), 201
    except Exception as e:
        db.session.rollback()
        return jsonify({"error": str(e)}), 500


@qc_bp.route('/checkpoints/<checkpoint_id>', methods=['PUT', 'OPTIONS'], strict_slashes=False)
@jwt_required
def update_checkpoint(checkpoint_id):
    if request.method == 'OPTIONS':
        return jsonify({}), 200

    checkpoint = QCCheckpoint.query.get(checkpoint_id)
    if not checkpoint:
        return jsonify({"error": "Checkpoint not found"}), 404

    data = request.get_json(silent=True) or {}
    if 'serial_no' in data: checkpoint.serial_no = data['serial_no']
    if 'check_point' in data: checkpoint.check_point = data['check_point']
    if 'standard_criteria' in data: checkpoint.standard_criteria = data['standard_criteria']
    if 'entry_labels' in data: checkpoint.entry_labels = data['entry_labels']
    if 'sort_order' in data: checkpoint.sort_order = data['sort_order']

    try:
        db.session.commit()
        return jsonify({"status": "success", "message": "Checkpoint updated"}), 200
    except Exception as e:
        db.session.rollback()
        return jsonify({"error": str(e)}), 500


@qc_bp.route('/checkpoints/<checkpoint_id>', methods=['DELETE', 'OPTIONS'], strict_slashes=False)
@jwt_required
def delete_checkpoint(checkpoint_id):
    if request.method == 'OPTIONS':
        return jsonify({}), 200

    checkpoint = QCCheckpoint.query.get(checkpoint_id)
    if not checkpoint:
        return jsonify({"error": "Checkpoint not found"}), 404

    try:
        db.session.delete(checkpoint)
        db.session.commit()
        return jsonify({"status": "success", "message": "Checkpoint deleted"}), 200
    except Exception as e:
        db.session.rollback()
        return jsonify({"error": str(e)}), 500


# ==========================================
# QC INSPECTIONS (submitting & viewing filled forms)
# ==========================================

def _serialize_observation(obs):
    return {
        "id": obs.id,
        "checkpoint_id": obs.checkpoint_id,
        "entry_label": obs.entry_label,
        "result": obs.result,
        "remark": obs.remark,
        "image_url": obs.image_url,
    }


def _serialize_inspection(inspection, with_observations=False):
    data = {
        "id": inspection.id,
        "template_id": inspection.template_id,
        "template_name": inspection.template.name if inspection.template else None,
        "reference_type": inspection.reference_type,
        "qr_code_string": inspection.qr_code_string,
        "item_id": inspection.item_id,
        "department_id": inspection.department_id,
        "header_data": inspection.header_data,
        "inspector_name": inspection.inspector_name,
        "inspection_date": inspection.inspection_date.isoformat() if inspection.inspection_date else None,
        "overall_result": inspection.overall_result,
        "overall_remarks": inspection.overall_remarks,
        "supervisor_approval": inspection.supervisor_approval,
        "drop_test_photo_1_url": inspection.drop_test_photo_1_url,
        "drop_test_photo_2_url": inspection.drop_test_photo_2_url,
    }
    if with_observations:
        data["observations"] = [_serialize_observation(o) for o in inspection.observations]
    return data


@qc_bp.route('/inspections', methods=['POST', 'OPTIONS'], strict_slashes=False)
@jwt_required
def submit_full_inspection():
    """Submits a completed template-based inspection: header + one
    observation per checkpoint x entry label. If tied to a bin
    (reference_type BIN), the bin's qc_status is updated to match the
    overall result — same gate the old /qc/inspect endpoint provided."""
    if request.method == 'OPTIONS':
        return jsonify({}), 200

    data = request.get_json(silent=True) or {}

    template_id = data.get('template_id')
    reference_type = data.get('reference_type')
    inspector_name = data.get('inspector_name')
    overall_result = data.get('overall_result', 'Pending')
    observations = data.get('observations', [])

    if not all([template_id, reference_type, inspector_name]):
        return jsonify({"error": "template_id, reference_type, and inspector_name are required"}), 400
    if reference_type not in ['BIN', 'SUPPLIER_DELIVERY', 'PRODUCTION_LINE']:
        return jsonify({"error": "reference_type must be one of BIN, SUPPLIER_DELIVERY, PRODUCTION_LINE"}), 400
    if overall_result not in ['Pending', 'Approved', 'Approved_With_Observation', 'Rejected']:
        return jsonify({"error": "Invalid overall_result"}), 400

    template = QCTemplate.query.get(template_id)
    if not template:
        return jsonify({"error": "Template not found"}), 404

    qr_code_string = data.get('qr_code_string')
    bin_record = None
    if reference_type == 'BIN':
        if not qr_code_string:
            return jsonify({"error": "qr_code_string is required when reference_type is BIN"}), 400
        bin_record = QRCodeRegistry.query.filter_by(qr_code_string=qr_code_string, is_active=1).first()
        if not bin_record:
            return jsonify({"error": "Invalid or depleted QR Code"}), 404

    # Mandatory remark on any Fail observation, per spec.
    for obs in observations:
        if obs.get('result') == 'Fail' and not (obs.get('remark') or '').strip():
            return jsonify({"error": f"A remark is required for failed checkpoint {obs.get('checkpoint_id')} ({obs.get('entry_label')})"}), 400

    inspection = QCInspection(
        template_id=template_id,
        reference_type=reference_type,
        qr_code_string=qr_code_string,
        item_id=data.get('item_id'),
        department_id=data.get('department_id'),
        header_data=data.get('header_data', {}),
        inspector_name=inspector_name,
        overall_result=overall_result,
        overall_remarks=data.get('overall_remarks'),
        supervisor_approval=data.get('supervisor_approval'),
    )
    db.session.add(inspection)
    db.session.flush()

    for obs in observations:
        checkpoint_id = obs.get('checkpoint_id')
        result = obs.get('result')
        entry_label = obs.get('entry_label')
        if not all([checkpoint_id, result, entry_label]):
            db.session.rollback()
            return jsonify({"error": "Each observation needs checkpoint_id, entry_label, and result"}), 400
        if result not in ['Pass', 'Fail', 'NA']:
            db.session.rollback()
            return jsonify({"error": f"Invalid result '{result}' — must be Pass, Fail, or NA"}), 400

        db.session.add(QCObservation(
            inspection_id=inspection.id,
            checkpoint_id=checkpoint_id,
            entry_label=entry_label,
            result=result,
            remark=obs.get('remark'),
            image_url=obs.get('image_url'),
        ))

    if bin_record and overall_result in ['Approved', 'Rejected']:
        bin_record.qc_status = 'Passed' if overall_result == 'Approved' else 'Rejected'

    try:
        db.session.commit()
        return jsonify({"status": "success", "message": "Inspection submitted", "id": inspection.id}), 201
    except Exception as e:
        db.session.rollback()
        return jsonify({"error": str(e)}), 500


@qc_bp.route('/inspections/<inspection_id>/photos', methods=['POST', 'OPTIONS'], strict_slashes=False)
@jwt_required
def upload_drop_test_photos(inspection_id):
    """Attaches the two mandatory drop-test evidence photos to an already-
    submitted inspection. Expects multipart/form-data with both 'photo_1'
    and 'photo_2' files — both are required, matching the frontend's rule
    that an inspection can't be submitted without both."""
    if request.method == 'OPTIONS':
        return jsonify({}), 200

    inspection = QCInspection.query.get(inspection_id)
    if not inspection:
        return jsonify({"error": "Inspection not found"}), 404

    photo_1 = request.files.get('photo_1')
    photo_2 = request.files.get('photo_2')
    if not photo_1 or photo_1.filename == '' or not photo_2 or photo_2.filename == '':
        return jsonify({"error": "Both photo_1 and photo_2 are required."}), 400

    saved_urls = {}
    for key, photo in (('photo_1', photo_1), ('photo_2', photo_2)):
        ext = os.path.splitext(photo.filename)[1].lower()
        if ext not in ALLOWED_IMAGE_EXT:
            return jsonify({"error": f"Unsupported file type '{ext}' for {key}. Use jpg, png, webp, or heic."}), 400
        filename = secure_filename(f"{inspection_id}_{key}_{uuid.uuid4().hex}{ext}")
        saved_urls[key] = upload_file(photo, 'qc_drop_tests', filename)

    inspection.drop_test_photo_1_url = saved_urls['photo_1']
    inspection.drop_test_photo_2_url = saved_urls['photo_2']

    try:
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        return jsonify({"error": str(e)}), 500

    return jsonify({
        "status": "success",
        "drop_test_photo_1_url": inspection.drop_test_photo_1_url,
        "drop_test_photo_2_url": inspection.drop_test_photo_2_url,
    }), 200


@qc_bp.route('/inspections', methods=['GET', 'OPTIONS'], strict_slashes=False)
@jwt_required
def list_inspections():
    if request.method == 'OPTIONS':
        return jsonify({}), 200

    query = QCInspection.query

    template_id = request.args.get('template_id')
    item_id = request.args.get('item_id')
    qr_code_string = request.args.get('qr_code_string')
    department_id = request.args.get('department_id')
    overall_result = request.args.get('status')
    inspector_name = request.args.get('inspector_name')

    if template_id: query = query.filter_by(template_id=template_id)
    if item_id: query = query.filter_by(item_id=item_id)
    if qr_code_string: query = query.filter_by(qr_code_string=qr_code_string)
    if department_id: query = query.filter_by(department_id=department_id)
    if overall_result: query = query.filter_by(overall_result=overall_result)
    if inspector_name: query = query.filter(db.func.lower(QCInspection.inspector_name) == inspector_name.strip().lower())

    inspections = query.order_by(QCInspection.created_at.desc()).limit(200).all()
    return jsonify({"status": "success", "data": [_serialize_inspection(i) for i in inspections]}), 200


@qc_bp.route('/inspections/<inspection_id>', methods=['GET', 'OPTIONS'], strict_slashes=False)
@jwt_required
def get_inspection(inspection_id):
    if request.method == 'OPTIONS':
        return jsonify({}), 200

    inspection = QCInspection.query.get(inspection_id)
    if not inspection:
        return jsonify({"error": "Inspection not found"}), 404
    return jsonify({"status": "success", "data": _serialize_inspection(inspection, with_observations=True)}), 200