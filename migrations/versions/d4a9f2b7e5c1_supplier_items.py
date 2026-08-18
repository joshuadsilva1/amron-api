"""supplier item linkage for MRP grouping

Revision ID: d4a9f2b7e5c1
Revises: c8e2d4f6a1b3
Create Date: 2026-08-19 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


revision = 'd4a9f2b7e5c1'
down_revision = 'c8e2d4f6a1b3'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'supplier_items',
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('supplier_id', sa.String(length=36), nullable=False),
        sa.Column('item_id', sa.String(length=36), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['supplier_id'], ['suppliers.id'], name=op.f('fk_supplier_items_supplier_id_suppliers')),
        sa.ForeignKeyConstraint(['item_id'], ['internal_products.id'], name=op.f('fk_supplier_items_item_id_internal_products')),
        sa.PrimaryKeyConstraint('id', name=op.f('pk_supplier_items')),
        sa.UniqueConstraint('supplier_id', 'item_id', name='uq_supplier_item'),
    )


def downgrade():
    op.drop_table('supplier_items')
