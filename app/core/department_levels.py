"""Finished-good detection. A finished good isn't a flag on the item — it's
an item that lives in a department at the highest configured level (see the
note on DepartmentLevel in app/models/department.py), e.g. a "Finished
Goods" department. Recipes use this to keep finished goods out of other
recipes' components."""
from app import db
from app.models.department import Department, DepartmentLevel


def final_level_rank():
    """Rank of the highest configured department level, or None if no
    levels exist yet."""
    return db.session.query(db.func.max(DepartmentLevel.rank)).scalar()


def is_finished_good(item):
    if not item or not item.department_id:
        return False
    rank = final_level_rank()
    if rank is None:
        return False
    dept = Department.query.get(item.department_id)
    return bool(dept and dept.department_level == rank)
