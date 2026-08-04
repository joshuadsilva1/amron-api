from app import db
from app.core.utils import generate_uuid
from datetime import datetime


class QCTemplate(db.Model):
    """A reusable inspection form definition — one per product/material type
    (e.g. 'Spring IQC', 'Switch OQC', 'Switches Assembly Check Sheet')."""
    __tablename__ = 'qc_templates'

    id = db.Column(db.String(36), primary_key=True, default=generate_uuid)
    name = db.Column(db.String(150), nullable=False)

    # 'IQC' | 'PQC' | 'OQC' | 'ASSEMBLY'
    qc_type = db.Column(db.String(20), nullable=False)

    # Freeform match key (material/product name or category) used to
    # auto-select a template for a scanned item — not a hard FK since IQC
    # templates key off raw-material names that don't exist as InternalProduct
    # categories.
    category = db.Column(db.String(100), nullable=True)

    # Which header fields this template's inspection form needs, e.g.
    # ["invoice_no", "supplier_name", "received_qty"] for IQC, or
    # ["po_no", "batch_no", "lot_qty", "sample_size"] for OQC. Rendered
    # dynamically on the frontend instead of one column per possible field.
    header_fields = db.Column(db.JSON, nullable=False, default=list)

    is_active = db.Column(db.Integer, default=1)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    sections = db.relationship(
        'QCSection', backref='template', order_by='QCSection.sort_order',
        cascade='all, delete-orphan'
    )


class QCSection(db.Model):
    """A named group of checkpoints within a template (e.g. 'Aesthetics Inspection')."""
    __tablename__ = 'qc_sections'

    id = db.Column(db.String(36), primary_key=True, default=generate_uuid)
    template_id = db.Column(db.String(36), db.ForeignKey('qc_templates.id'), nullable=False)

    title = db.Column(db.String(150), nullable=False)
    sort_order = db.Column(db.Integer, default=0)

    checkpoints = db.relationship(
        'QCCheckpoint', backref='section', order_by='QCCheckpoint.sort_order',
        cascade='all, delete-orphan'
    )


class QCCheckpoint(db.Model):
    """One inspectable point within a section."""
    __tablename__ = 'qc_checkpoints'

    id = db.Column(db.String(36), primary_key=True, default=generate_uuid)
    section_id = db.Column(db.String(36), db.ForeignKey('qc_sections.id'), nullable=False)

    serial_no = db.Column(db.Integer, nullable=True)
    check_point = db.Column(db.Text, nullable=False)
    standard_criteria = db.Column(db.Text, nullable=True)

    # e.g. ["Sample 1", "Sample 2", "Sample 3"] or the 9 hourly slot labels,
    # or just ["Result"] for a single pass/fail checkpoint. Each label gets
    # its own QCObservation when an inspection is submitted.
    entry_labels = db.Column(db.JSON, nullable=False, default=lambda: ["Result"])

    sort_order = db.Column(db.Integer, default=0)


class QCInspection(db.Model):
    """One completed (or in-progress) inspection run against a template."""
    __tablename__ = 'qc_inspections'

    id = db.Column(db.String(36), primary_key=True, default=generate_uuid)
    template_id = db.Column(db.String(36), db.ForeignKey('qc_templates.id'), nullable=False)
    template = db.relationship('QCTemplate')

    # 'BIN' (PQC/OQC against a QR-tracked bin) | 'SUPPLIER_DELIVERY' (IQC,
    # not yet a bin) | 'PRODUCTION_LINE' (assembly hourly check sheet)
    reference_type = db.Column(db.String(20), nullable=False)

    qr_code_string = db.Column(db.String(100), db.ForeignKey('qr_code_registry.qr_code_string'), nullable=True)
    item_id = db.Column(db.String(36), db.ForeignKey('internal_products.id'), nullable=True)
    department_id = db.Column(db.String(36), db.ForeignKey('departments.id'), nullable=True)

    # Freeform values for whatever fields template.header_fields declares
    # (PO no, invoice no, batch, supplier, lot qty, sample size, verified
    # by, approved by, report no, etc.)
    header_data = db.Column(db.JSON, nullable=False, default=dict)

    inspector_name = db.Column(db.String(100), nullable=False)
    inspection_date = db.Column(db.DateTime, default=datetime.utcnow)

    # 'Pending' | 'Approved' | 'Approved_With_Observation' | 'Rejected'
    overall_result = db.Column(db.String(30), default='Pending')
    overall_remarks = db.Column(db.Text, nullable=True)
    supervisor_approval = db.Column(db.String(100), nullable=True)

    # Mandatory drop-test evidence photos, attached in a second step after
    # the inspection record is created (see /inspections/<id>/photos).
    drop_test_photo_1_url = db.Column(db.String(255), nullable=True)
    drop_test_photo_2_url = db.Column(db.String(255), nullable=True)

    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    observations = db.relationship(
        'QCObservation', backref='inspection', cascade='all, delete-orphan'
    )


class QCObservation(db.Model):
    """One Pass/Fail/N-A entry for a single checkpoint x entry label."""
    __tablename__ = 'qc_observations'

    id = db.Column(db.String(36), primary_key=True, default=generate_uuid)
    inspection_id = db.Column(db.String(36), db.ForeignKey('qc_inspections.id'), nullable=False)
    checkpoint_id = db.Column(db.String(36), db.ForeignKey('qc_checkpoints.id'), nullable=False)

    entry_label = db.Column(db.String(50), nullable=False)

    # 'Pass' | 'Fail' | 'NA'
    result = db.Column(db.String(10), nullable=False)
    remark = db.Column(db.Text, nullable=True)
    image_url = db.Column(db.Text, nullable=True)
