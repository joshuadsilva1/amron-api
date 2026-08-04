from app import db
from app.core.utils import generate_uuid
from datetime import datetime

class Notification(db.Model):
    """System-wide alerts and messages across departments"""
    __tablename__ = 'notifications'
    
    id = db.Column(db.String(36), primary_key=True, default=generate_uuid)
    title = db.Column(db.String(150), nullable=False)
    message = db.Column(db.Text, nullable=False)
    department_id = db.Column(db.String(36), db.ForeignKey('departments.id'), nullable=True)
    
    is_read = db.Column(db.Integer, default=0)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)