"""Job-work supplier orders: materials we send to a supplier so they can
make a part for us (e.g. powder sent to an outside moulder), and
fractional order quantities (powder is ordered in kg, e.g. 3.6).

Revision ID: c5e8f3b1d2a4
Revises: b4d7e2a9c1f3
Create Date: 2026-09-25 15:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


revision = 'c5e8f3b1d2a4'
down_revision = 'b4d7e2a9c1f3'
branch_labels = None
depends_on = None


def upgrade():
    op.alter_column('supplier_order_items', 'ordered_qty', type_=sa.Float(), existing_type=sa.Integer(), existing_nullable=False)
    op.alter_column('supplier_order_items', 'received_qty', type_=sa.Float(), existing_type=sa.Integer(), existing_nullable=True)

    op.create_table(
        'supplier_order_materials',
        sa.Column('id', sa.String(length=36), primary_key=True),
        sa.Column('supplier_order_id', sa.String(length=36), sa.ForeignKey('supplier_orders.id'), nullable=False),
        sa.Column('product_id', sa.String(length=36), sa.ForeignKey('internal_products.id'), nullable=False),
        sa.Column('for_product_id', sa.String(length=36), sa.ForeignKey('internal_products.id'), nullable=True),
        sa.Column('quantity', sa.Float(), nullable=False),
        sa.Column('created_at', sa.DateTime(), server_default=sa.func.now()),
    )


def downgrade():
    op.drop_table('supplier_order_materials')
    op.alter_column('supplier_order_items', 'received_qty', type_=sa.Integer(), existing_type=sa.Float(), existing_nullable=True)
    op.alter_column('supplier_order_items', 'ordered_qty', type_=sa.Integer(), existing_type=sa.Float(), existing_nullable=False)
