"""Shared multi-level BOM explosion logic, used by both the Recipe
explosion endpoint and MRP shortage calculation so the two can never
drift out of sync on how a PO quantity turns into raw-material demand.
"""
from app.models.recipe import BOMVersion
from app.models.item import InternalProduct

MAX_BOM_DEPTH = 12

UNIT_MULTIPLIER = {
    "pieces": 1,
    "pcs": 1,
    "gross": 144,
    "dozen": 12,
}


def explode_component(component_id, qty_needed, visited, depth):
    """Recurses into a component's own active BOM, if it has one, down to
    raw materials (components with no BOM of their own = leaves).
    Returns {component_id: total_qty} for every leaf reached."""
    if depth > MAX_BOM_DEPTH:
        raise ValueError(f"BOM nesting exceeds {MAX_BOM_DEPTH} levels (likely a circular reference)")
    if component_id in visited:
        raise ValueError("Circular BOM reference detected — a component's recipe refers back to itself")

    active_version = BOMVersion.query.filter_by(finished_good_id=component_id, is_active=True).first()
    if not active_version:
        return {component_id: qty_needed}

    child_visited = visited | {component_id}
    totals = {}
    for row in active_version.components:
        comp = InternalProduct.query.get(row.component_id)
        comp_unit = str(comp.unit_of_measure).lower() if comp and comp.unit_of_measure else "pieces"
        multiplier = UNIT_MULTIPLIER.get(comp_unit, 1)
        sub_qty = (row.quantity_required * multiplier) * qty_needed

        sub_totals = explode_component(row.component_id, sub_qty, child_visited, depth + 1)
        for k, v in sub_totals.items():
            totals[k] = totals.get(k, 0) + v
    return totals


def explode_product_quantity(product_id, quantity):
    """Explodes a single product's order quantity through its own active
    BOM (one level) plus everything beneath. Returns {} if the product has
    no active recipe (nothing to explode)."""
    active_version = BOMVersion.query.filter_by(finished_good_id=product_id, is_active=True).first()
    if not active_version:
        return {}

    totals = {}
    for row in active_version.components:
        comp = InternalProduct.query.get(row.component_id)
        comp_unit = str(comp.unit_of_measure).lower() if comp and comp.unit_of_measure else "pieces"
        multiplier = UNIT_MULTIPLIER.get(comp_unit, 1)
        sub_qty = (row.quantity_required * multiplier) * quantity

        sub_totals = explode_component(row.component_id, sub_qty, {product_id}, 1)
        for k, v in sub_totals.items():
            totals[k] = totals.get(k, 0) + v
    return totals
