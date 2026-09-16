"""internal department POs (auto-raised from a customer PO's direct BOM,
fulfilled only by real production — see app/core/department_po.py)

Revision ID: a3b7c9d1e2f4
Revises: f1a2b3c4d5e6
Create Date: 2026-09-15 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


revision = 'a3b7c9d1e2f4'
down_revision = 'f1a2b3c4d5e6'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'department_pos',
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('department_id', sa.String(length=36), nullable=False),
        sa.Column('source_po_id', sa.String(length=36), nullable=True),
        sa.Column('status', sa.String(length=20), nullable=True),
        sa.Column('is_urgent', sa.Integer(), nullable=True),
        sa.Column('notes', sa.Text(), nullable=True),
        sa.Column('created_by', sa.String(length=36), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.Column('fulfilled_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['department_id'], ['departments.id'], name=op.f('fk_department_pos_department_id_departments')),
        sa.ForeignKeyConstraint(['source_po_id'], ['purchase_orders.id'], name=op.f('fk_department_pos_source_po_id_purchase_orders')),
        sa.ForeignKeyConstraint(['created_by'], ['users.id'], name=op.f('fk_department_pos_created_by_users')),
        sa.PrimaryKeyConstraint('id', name=op.f('pk_department_pos')),
    )
    op.create_table(
        'department_po_items',
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('department_po_id', sa.String(length=36), nullable=False),
        sa.Column('component_id', sa.String(length=36), nullable=False),
        sa.Column('quantity_requested', sa.Float(), nullable=False),
        sa.Column('quantity_fulfilled', sa.Float(), nullable=True),
        sa.ForeignKeyConstraint(['department_po_id'], ['department_pos.id'], name=op.f('fk_department_po_items_department_po_id_department_pos')),
        sa.ForeignKeyConstraint(['component_id'], ['internal_products.id'], name=op.f('fk_department_po_items_component_id_internal_products')),
        sa.PrimaryKeyConstraint('id', name=op.f('pk_department_po_items')),
    )


def downgrade():
    op.drop_table('department_po_items')
    op.drop_table('department_pos')
