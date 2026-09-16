"""wastage %, colour routing, LR number, auto-drafted challans

Revision ID: f1a2b3c4d5e6
Revises: e6b1c3d8f0a4
Create Date: 2026-09-11 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


revision = 'f1a2b3c4d5e6'
down_revision = 'e6b1c3d8f0a4'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('product_bom', sa.Column('colour_needed', sa.Boolean(), nullable=True, server_default=sa.false()))
    op.add_column('product_bom', sa.Column('wastage_percent', sa.Float(), nullable=False, server_default='0'))

    op.add_column('internal_challans', sa.Column('lr_number', sa.String(length=100), nullable=True))
    op.add_column('internal_challans', sa.Column('auto_generated', sa.Boolean(), nullable=True, server_default=sa.false()))


def downgrade():
    op.drop_column('internal_challans', 'auto_generated')
    op.drop_column('internal_challans', 'lr_number')

    op.drop_column('product_bom', 'wastage_percent')
    op.drop_column('product_bom', 'colour_needed')
