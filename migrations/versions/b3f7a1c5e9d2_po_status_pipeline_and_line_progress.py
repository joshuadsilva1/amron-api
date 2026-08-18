"""expand PO status pipeline, add produced_qty to line items

Revision ID: b3f7a1c5e9d2
Revises: 9c1e6a4d7f2b
Create Date: 2026-08-18 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


revision = 'b3f7a1c5e9d2'
down_revision = '9c1e6a4d7f2b'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('po_line_items', sa.Column('produced_qty', sa.Integer(), nullable=True))
    op.execute("UPDATE po_line_items SET produced_qty = 0 WHERE produced_qty IS NULL")

    # Backfill old informal status values into the real pipeline.
    op.execute("UPDATE purchase_orders SET status = 'Received' WHERE status = 'Pending'")
    op.execute("UPDATE purchase_orders SET status = 'Verified' WHERE status = 'Clubbed'")
    op.execute("UPDATE purchase_orders SET status = 'In Production' WHERE status = 'In_Production'")
    # 'Dispatched' already matches the new pipeline as-is.


def downgrade():
    op.execute("UPDATE purchase_orders SET status = 'Pending' WHERE status = 'Received'")
    op.execute("UPDATE purchase_orders SET status = 'Clubbed' WHERE status = 'Verified'")
    op.execute("UPDATE purchase_orders SET status = 'In_Production' WHERE status = 'In Production'")
    op.drop_column('po_line_items', 'produced_qty')
