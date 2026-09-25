"""units_of_measure table (was a hardcoded list in the app) and
internal_products.description (shown next to the product when picking
it on a customer PO).

Seeds the units the app used to hardcode, plus any unit already typed on
an existing item, so no item ends up pointing at a unit that isn't in the
list.

Revision ID: b4d7e2a9c1f3
Revises: a9c3e6f1d8b2
Create Date: 2026-09-25 12:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


revision = 'b4d7e2a9c1f3'
down_revision = 'a9c3e6f1d8b2'
branch_labels = None
depends_on = None

DEFAULT_UNITS = [
    ('pcs', 'Pieces'),
    ('kg', 'Kilograms'),
    ('g', 'Grams'),
    ('boxes', 'Boxes'),
    ('meters', 'Meters'),
    ('dozen', 'Dozen (12 pcs)'),
    ('gross', 'Gross (144 pcs)'),
]


def upgrade():
    op.add_column('internal_products', sa.Column('description', sa.Text(), nullable=True))

    units = op.create_table(
        'units_of_measure',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('name', sa.String(length=20), nullable=False, unique=True),
        sa.Column('description', sa.String(length=100), nullable=True),
        sa.Column('created_at', sa.DateTime(), server_default=sa.func.now()),
    )

    conn = op.get_bind()
    existing = {
        (row[0] or '').strip()
        for row in conn.execute(sa.text("SELECT DISTINCT unit_of_measure FROM internal_products"))
    }
    seeded = {name.lower() for name, _ in DEFAULT_UNITS}
    rows = [{'name': n, 'description': d} for n, d in DEFAULT_UNITS]
    for name in sorted(existing):
        if name and name.lower() not in seeded:
            rows.append({'name': name, 'description': None})
            seeded.add(name.lower())
    op.bulk_insert(units, rows)


def downgrade():
    op.drop_table('units_of_measure')
    op.drop_column('internal_products', 'description')
