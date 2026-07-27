from app import db
from app.core.utils import generate_uuid
from datetime import datetime

class DailyProductionPlan(db.Model):
    __tablename__ = 'daily_production_plans'
    
    id = db.Column(db.String(36), primary_key=True, default=generate_uuid)
    production_date = db.Column(db.Date, nullable=False)
    
    product_id = db.Column(db.String(36), db.ForeignKey('internal_products.id'), nullable=False)
    department_name = db.Column(db.String(100), nullable=False) # e.g., 'Moulding', 'Brasspart'
    
    target_quantity = db.Column(db.Integer, nullable=False)
    completed_quantity = db.Column(db.Integer, default=0)
    
    priority = db.Column(db.String(50), default='Normal') # Normal, Urgent
    status = db.Column(db.String(50), default='Pending')  # Pending, In_Progress, Completed
    
    created_at = db.Column(db.DateTime, default=datetime.utcnow)