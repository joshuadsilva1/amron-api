from app import db
from app.core.utils import generate_uuid


from app import db
from app.core.utils import generate_uuid
from datetime import datetime

class Recipe(db.Model):
    """The master recipe for a finished or semi-finished good"""
    __tablename__ = 'recipes'
    
    id = db.Column(db.String(36), primary_key=True, default=generate_uuid)
    
    # The item this recipe creates
    output_item_id = db.Column(db.String(36), db.ForeignKey('internal_products.id'), nullable=False, unique=True)
    
    is_active = db.Column(db.Integer, default=1)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class RecipeItem(db.Model):
    """The individual ingredients required for the recipe"""
    __tablename__ = 'recipe_items'
    
    id = db.Column(db.String(36), primary_key=True, default=generate_uuid)
    
    recipe_id = db.Column(db.String(36), db.ForeignKey('recipes.id'), nullable=False)
    
    # The raw material or component being consumed
    input_item_id = db.Column(db.String(36), db.ForeignKey('internal_products.id'), nullable=False)
    
    # How much of this input is needed to make exactly ONE output item
    quantity_required = db.Column(db.Float, nullable=False)

class ProductBOM(db.Model):
    __tablename__ = 'product_bom'
    
    id = db.Column(db.String(36), primary_key=True, default=generate_uuid)
    
    # The item being built (e.g., The Switch)
    finished_good_id = db.Column(db.String(36), db.ForeignKey('internal_products.id'), nullable=False)
    
    # The component required (e.g., Brasspart, Box, Label)
    component_id = db.Column(db.String(36), db.ForeignKey('internal_products.id'), nullable=False)
    
    quantity_required = db.Column(db.Float, nullable=False)
    lazer_needed = db.Column(db.Boolean, default=False)