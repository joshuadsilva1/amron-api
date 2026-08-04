from app import db
from app.core.utils import generate_uuid


class ProductBOM(db.Model):
    __tablename__ = 'product_bom'
    
    id = db.Column(db.String(36), primary_key=True, default=generate_uuid)
    
    # The item being built (e.g., The Switch)
    finished_good_id = db.Column(db.String(36), db.ForeignKey('internal_products.id'), nullable=False)
    
    # The component required (e.g., Brasspart, Box, Label)
    component_id = db.Column(db.String(36), db.ForeignKey('internal_products.id'), nullable=False)
    
    quantity_required = db.Column(db.Float, nullable=False)
    lazer_needed = db.Column(db.Boolean, default=False)