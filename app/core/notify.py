from app import db
from app.models.notification import Notification


def create_notification(title, message, department_id=None):
    note = Notification(title=title, message=message, department_id=department_id)
    db.session.add(note)
    return note


def check_low_stock(item, department_id=None):
    """Creates a low-stock notification if `item` is at or below its
    reorder level. Call this right after any operation that decreases
    stock. No-op for items with no reorder_level set (default 0), and
    won't spam — skips if an unread low-stock notification for this exact
    item is already outstanding.
    """
    if not item or not item.reorder_level or item.reorder_level <= 0:
        return None
    if item.current_stock > item.reorder_level:
        return None

    existing = Notification.query.filter(
        Notification.title == f"Low Stock: {item.name}",
        Notification.is_read == 0,
    ).first()
    if existing:
        return None

    return create_notification(
        title=f"Low Stock: {item.name}",
        message=(
            f"{item.name} ({item.item_code or 'no code'}) is at {item.current_stock} "
            f"{item.unit_of_measure}, at or below its reorder level of {item.reorder_level}."
        ),
        department_id=department_id or item.department_id,
    )
