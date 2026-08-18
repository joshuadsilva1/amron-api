from app import db
from app.core.utils import generate_uuid
from datetime import datetime

PLAN_DAY_STATUSES = ['Draft', 'Validated', 'Approved', 'Released']

VARIANCE_REASONS = [
    'Material shortage',
    'Supplier delay',
    'Machine breakdown',
    'Manpower shortage',
    'Quality hold',
    'Packaging shortage',
    'Previous order pending',
    'Customer change',
    'Other',
]


class ProductionPlanDay(db.Model):
    """The lifecycle wrapper around one day's DailyProductionPlan rows —
    lets a whole day's plan be Draft/Validated/Approved/Released as one
    unit, matching the 7:30 AM planning workflow (a plan isn't 'live'
    department instructions until it's Released)."""
    __tablename__ = 'production_plan_days'

    id = db.Column(db.String(36), primary_key=True, default=generate_uuid)
    plan_date = db.Column(db.Date, unique=True, nullable=False)
    status = db.Column(db.String(20), default='Draft')

    created_by = db.Column(db.String(36), db.ForeignKey('users.id'), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


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

    # Required whenever completed_quantity ends up short of target_quantity
    # at day-close — forces the Production Manager to record *why*, so a
    # month of variance can actually be analyzed later instead of just
    # silently missed numbers.
    variance_reason = db.Column(db.String(50), nullable=True)

    created_at = db.Column(db.DateTime, default=datetime.utcnow)
