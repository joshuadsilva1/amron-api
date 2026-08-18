"""MRP shortage calculation, shared between the MRP summary endpoint and
the Control Tower's material_shortages metric so the two never disagree.
"""
from app.models.order import PurchaseOrder
from app.models.item import InternalProduct, OEMCompanyCode
from app.models.supplier import Supplier, SupplierItem
from app.models.supplier_order import SupplierOrder
from app.core.bom import explode_product_quantity

CLOSED_STAGES = {'Dispatched', 'Closed'}


def compute_shortages():
    """The MRP engine: explodes every open PO's remaining (unproduced)
    quantity through the BOM down to raw materials, aggregates total
    demand per item, and nets it against physical stock, safety stock
    (reorder_level), and incoming supplier orders.

    Returns a dict {item_id: {...}} for every item with any demand,
    incoming, or existing stock — callers filter for shortage > 0 as
    needed (the Control Tower wants a count, the MRP screen wants the
    full breakdown).
    """
    active_pos = PurchaseOrder.query.filter(
        PurchaseOrder.is_active == 1,
        ~PurchaseOrder.status.in_(CLOSED_STAGES)
    ).all()

    demand = {}
    for po in active_pos:
        for li in po.items:
            remaining = (li.quantity or 0) - (li.produced_qty or 0)
            if remaining <= 0:
                continue
            mapping = OEMCompanyCode.query.get(li.mapping_id)
            if not mapping:
                continue
            product_id = mapping.internal_product_id
            try:
                exploded = explode_product_quantity(product_id, remaining)
            except ValueError:
                # A broken/circular recipe shouldn't take down the whole
                # MRP calculation — skip just this line's contribution.
                continue
            for item_id, qty in exploded.items():
                demand[item_id] = demand.get(item_id, 0) + qty

    # Incoming: approved supplier orders not yet fully received
    incoming = {}
    for so in SupplierOrder.query.filter(SupplierOrder.is_active == 1, SupplierOrder.status == 'Approved').all():
        for item in so.items:
            outstanding = (item.ordered_qty or 0) - (item.received_qty or 0)
            if outstanding > 0:
                incoming[item.product_id] = incoming.get(item.product_id, 0) + outstanding

    all_item_ids = set(demand.keys()) | set(incoming.keys())

    result = {}
    for item_id in all_item_ids:
        product = InternalProduct.query.get(item_id)
        if not product:
            continue
        reserved = demand.get(item_id, 0)
        physical = product.current_stock or 0
        safety_stock = product.reorder_level or 0
        incoming_qty = incoming.get(item_id, 0)
        shortage = max(0, reserved + safety_stock - physical - incoming_qty)

        suppliers = [
            {"id": s.id, "name": s.name}
            for s in Supplier.query.join(SupplierItem, SupplierItem.supplier_id == Supplier.id)
            .filter(SupplierItem.item_id == item_id, Supplier.is_active == 1).all()
        ]

        result[item_id] = {
            "item_id": item_id,
            "item_code": product.item_code,
            "item_name": product.name,
            "category": product.category,
            "physical_stock": physical,
            "reserved": reserved,
            "available": physical - reserved,
            "safety_stock": safety_stock,
            "incoming": incoming_qty,
            "shortage": shortage,
            "suppliers": suppliers,
        }

    return result
