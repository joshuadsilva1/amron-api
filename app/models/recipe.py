from app import db
from app.core.utils import generate_uuid
from datetime import datetime


class BOMVersion(db.Model):
    """A revision of a finished good's (or component's) recipe. Saving a
    recipe never overwrites history — it creates a new version and marks
    the previous one inactive, so old versions stay retrievable."""
    __tablename__ = 'bom_versions'

    id = db.Column(db.String(36), primary_key=True, default=generate_uuid)

    # The item this recipe builds — a finished good OR an intermediate
    # component/subassembly that itself has a recipe. Not restricted to
    # FINAL-department items, which is what makes multi-level BOMs
    # possible: a component can have its own BOMVersion pointing further
    # down at raw materials.
    finished_good_id = db.Column(db.String(36), db.ForeignKey('internal_products.id'), nullable=False)

    version = db.Column(db.Integer, nullable=False)
    is_active = db.Column(db.Boolean, default=True)
    notes = db.Column(db.Text, nullable=True)
    created_by = db.Column(db.String(36), db.ForeignKey('users.id'), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    components = db.relationship('ProductBOM', backref='bom_version', lazy=True, cascade='all, delete-orphan')

    __table_args__ = (
        db.UniqueConstraint('finished_good_id', 'version', name='uq_bom_version'),
    )


class ProductBOM(db.Model):
    __tablename__ = 'product_bom'

    id = db.Column(db.String(36), primary_key=True, default=generate_uuid)

    bom_version_id = db.Column(db.String(36), db.ForeignKey('bom_versions.id'), nullable=False)

    # The component required (e.g., Brasspart, Box, Label) — may itself
    # have its own active BOMVersion, in which case explosion recurses
    # into it instead of treating it as a raw material.
    component_id = db.Column(db.String(36), db.ForeignKey('internal_products.id'), nullable=False)

    quantity_required = db.Column(db.Float, nullable=False)
    lazer_needed = db.Column(db.Boolean, default=False)
