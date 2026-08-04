"""add box mappings table

Revision ID: 9c1e6a4d7f2b
Revises: 7d2f4b9e1a3c
Create Date: 2026-08-05 00:00:01.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '9c1e6a4d7f2b'
down_revision = '7d2f4b9e1a3c'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'box_mappings',
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('box_item_id', sa.String(length=36), nullable=False),
        sa.Column('product_id', sa.String(length=36), nullable=False),
        sa.Column('pcs_per_box', sa.Integer(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['box_item_id'], ['internal_products.id'], name=op.f('fk_box_item_id_internal_products')),
        sa.ForeignKeyConstraint(['product_id'], ['internal_products.id'], name=op.f('fk_product_id_internal_products')),
        sa.PrimaryKeyConstraint('id', name=op.f('pk_box_mappings')),
        sa.UniqueConstraint('box_item_id', 'product_id', name='uq_box_mapping_box_product'),
    )


def downgrade():
    op.drop_table('box_mappings')
