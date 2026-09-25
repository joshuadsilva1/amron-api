from app import db
from datetime import datetime


class UnitOfMeasure(db.Model):
    """The list of units an item can be counted in (pcs, kg, ...).
    Managed from the Items screen — was a hardcoded list in the app.
    Items store the unit's name as plain text (internal_products.
    unit_of_measure), not a foreign key, so renaming/removing a unit
    never breaks an existing item."""
    __tablename__ = 'units_of_measure'

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    name = db.Column(db.String(20), unique=True, nullable=False)
    description = db.Column(db.String(100), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
