"""Add QC template system

Revision ID: d752ed65a94a
Revises: 1cae1743a090
Create Date: 2026-08-03 13:10:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'd752ed65a94a'
down_revision = '1cae1743a090'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'qc_templates',
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('name', sa.String(length=150), nullable=False),
        sa.Column('qc_type', sa.String(length=20), nullable=False),
        sa.Column('category', sa.String(length=100), nullable=True),
        sa.Column('header_fields', sa.JSON(), nullable=False),
        sa.Column('is_active', sa.Integer(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint('id'),
    )

    op.create_table(
        'qc_sections',
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('template_id', sa.String(length=36), nullable=False),
        sa.Column('title', sa.String(length=150), nullable=False),
        sa.Column('sort_order', sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(['template_id'], ['qc_templates.id']),
        sa.PrimaryKeyConstraint('id'),
    )

    op.create_table(
        'qc_checkpoints',
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('section_id', sa.String(length=36), nullable=False),
        sa.Column('serial_no', sa.Integer(), nullable=True),
        sa.Column('check_point', sa.Text(), nullable=False),
        sa.Column('standard_criteria', sa.Text(), nullable=True),
        sa.Column('entry_labels', sa.JSON(), nullable=False),
        sa.Column('sort_order', sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(['section_id'], ['qc_sections.id']),
        sa.PrimaryKeyConstraint('id'),
    )

    op.create_table(
        'qc_inspections',
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('template_id', sa.String(length=36), nullable=False),
        sa.Column('reference_type', sa.String(length=20), nullable=False),
        sa.Column('qr_code_string', sa.String(length=100), nullable=True),
        sa.Column('item_id', sa.String(length=36), nullable=True),
        sa.Column('department_id', sa.String(length=36), nullable=True),
        sa.Column('header_data', sa.JSON(), nullable=False),
        sa.Column('inspector_name', sa.String(length=100), nullable=False),
        sa.Column('inspection_date', sa.DateTime(), nullable=True),
        sa.Column('overall_result', sa.String(length=30), nullable=True),
        sa.Column('overall_remarks', sa.Text(), nullable=True),
        sa.Column('supervisor_approval', sa.String(length=100), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['template_id'], ['qc_templates.id']),
        sa.ForeignKeyConstraint(['qr_code_string'], ['qr_code_registry.qr_code_string']),
        sa.ForeignKeyConstraint(['item_id'], ['internal_products.id']),
        sa.ForeignKeyConstraint(['department_id'], ['departments.id']),
        sa.PrimaryKeyConstraint('id'),
    )

    op.create_table(
        'qc_observations',
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('inspection_id', sa.String(length=36), nullable=False),
        sa.Column('checkpoint_id', sa.String(length=36), nullable=False),
        sa.Column('entry_label', sa.String(length=50), nullable=False),
        sa.Column('result', sa.String(length=10), nullable=False),
        sa.Column('remark', sa.Text(), nullable=True),
        sa.Column('image_url', sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(['inspection_id'], ['qc_inspections.id']),
        sa.ForeignKeyConstraint(['checkpoint_id'], ['qc_checkpoints.id']),
        sa.PrimaryKeyConstraint('id'),
    )


def downgrade():
    op.drop_table('qc_observations')
    op.drop_table('qc_inspections')
    op.drop_table('qc_checkpoints')
    op.drop_table('qc_sections')
    op.drop_table('qc_templates')
