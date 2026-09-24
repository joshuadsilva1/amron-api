"""powder colour on internal_products (White/Grey/Black moulded parts)

Revision ID: c2d5e8f1a3b7
Revises: b8d4f2a6c1e9
Create Date: 2026-09-22 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


revision = 'c2d5e8f1a3b7'
down_revision = 'b8d4f2a6c1e9'
branch_labels = None
depends_on = None


def upgrade():
    # Only meaningful for moulded components (Moulding department items).
    # NULL means "not a colour-tracked moulded part" (e.g. brass, boxes,
    # labels) — validation only kicks in once this is set to 'White', which
    # blocks that component from ever being flagged colour_needed on a BOM
    # row (see recipes_api.create_recipe / import_api bulk import).
    op.add_column('internal_products', sa.Column('powder_colour', sa.String(length=10), nullable=True))


def downgrade():
    op.drop_column('internal_products', 'powder_colour')
