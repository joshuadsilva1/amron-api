from app import db
from app.core.utils import generate_uuid
from datetime import datetime

class QualityInspectionLog(db.Model):
    """Permanent record of QC checklist results linked to a specific bin"""
    __tablename__ = 'quality_inspection_logs'
    __table_args__ = {'extend_existing': True}
    
    id = db.Column(db.String(36), primary_key=True, default=generate_uuid)
    
    # Link to the specific bin
    qr_code_string = db.Column(db.String(100), db.ForeignKey('qr_code_registry.qr_code_string'), nullable=False)
    
    inspector_name = db.Column(db.String(100), nullable=False)
    status_given = db.Column(db.String(20), nullable=False) # 'Passed' or 'Rejected'
    
    # We use a JSON column to store the dynamic N1-N5 checklist data from your Excel sheet
    checklist_data = db.Column(db.JSON, nullable=True) 
    
    created_at = db.Column(db.DateTime, default=datetime.utcnow)