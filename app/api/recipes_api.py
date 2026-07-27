from flask import Blueprint, request, jsonify
from app import db
from app.models.recipe import ProductBOM
from app.models.item import InternalProduct

recipes_bp = Blueprint('recipes', __name__)


from flask import Blueprint, request, jsonify
from app import db
from app.models.recipe import Recipe, RecipeItem
from app.models.item import InternalProduct

recipes_bp = Blueprint('recipes', __name__)

@recipes_bp.route('/', methods=['POST'])
def create_recipe():
    data = request.get_json()
    
    output_item_id = data.get('output_item_id')
    ingredients = data.get('ingredients', []) # [{"input_item_id": "...", "quantity_required": 0.5}]
    
    if not output_item_id or not ingredients:
        return jsonify({"error": "output_item_id and an array of ingredients are required"}), 400

    # Ensure the output item actually exists
    output_item = InternalProduct.query.get(output_item_id)
    if not output_item:
        return jsonify({"error": "Output item not found in catalog"}), 404

    # Check if a recipe already exists for this item
    existing_recipe = Recipe.query.filter_by(output_item_id=output_item_id).first()
    if existing_recipe:
        return jsonify({"error": f"A recipe already exists for {output_item.name}"}), 409

    # 1. Create the Master Recipe
    new_recipe = Recipe(output_item_id=output_item_id)
    db.session.add(new_recipe)
    db.session.flush() # Get the new_recipe.id before committing

    # 2. Add all the Ingredients
    for ing in ingredients:
        input_item_id = ing.get('input_item_id')
        qty = float(ing.get('quantity_required', 0))
        
        if qty <= 0:
            db.session.rollback()
            return jsonify({"error": "Ingredient quantities must be greater than zero"}), 400
            
        # Verify the ingredient exists
        if not InternalProduct.query.get(input_item_id):
            db.session.rollback()
            return jsonify({"error": f"Ingredient ID {input_item_id} not found"}), 404
            
        recipe_item = RecipeItem(
            recipe_id=new_recipe.id,
            input_item_id=input_item_id,
            quantity_required=qty
        )
        db.session.add(recipe_item)

    try:
        db.session.commit()
        return jsonify({"status": "success", "message": f"Recipe created for {output_item.name}"}), 201
    except Exception as e:
        db.session.rollback()
        return jsonify({"error": str(e)}), 500



@recipes_bp.route('/explode', methods=['POST'])
def explode_orders():
    """
    The Engine: Takes a list of clubbed orders and explodes them 
    into total aggregated raw material requirements, accounting for complex units.
    """
    data = request.get_json()
    orders = data.get('orders', [])

    if not orders:
        return jsonify({"error": "No orders provided for explosion"}), 400

    raw_materials_needed = {} 
    
    # Unit conversion dictionary to normalize everything to pieces
    unit_multiplier = {
        "pieces": 1,
        "pcs": 1,
        "gross": 144,
        "dozen": 12
    }

    for order in orders:
        fg_id = order.get('product_id')
        order_qty = order.get('quantity', 0)

        boms = ProductBOM.query.filter_by(finished_good_id=fg_id).all()

        for bom in boms:
            comp_id = bom.component_id
            comp = InternalProduct.query.get(comp_id)
            
            if not comp:
                continue

            # Determine the multiplier based on the raw material's unit
            comp_unit = str(comp.unit).lower() if comp.unit else "pieces"
            multiplier = unit_multiplier.get(comp_unit, 1)

            # Convert the BOM requirement into a normalized quantity
            required_qty = (bom.quantity_required * multiplier) * order_qty

            if comp_id in raw_materials_needed:
                raw_materials_needed[comp_id] += required_qty
            else:
                raw_materials_needed[comp_id] = required_qty

    result = []
    for comp_id, total_qty in raw_materials_needed.items():
        comp = InternalProduct.query.get(comp_id)
        if comp:
            result.append({
                "component_id": comp_id,
                "internal_code": comp.internal_code,
                "component_name": comp.name,
                "category": comp.category,
                "sub_category": comp.sub_category,
                "total_required_normalized": total_qty, # Output is always normalized to base pieces
                "original_unit": comp.unit
            })

    return jsonify({"status": "success", "data": result}), 200