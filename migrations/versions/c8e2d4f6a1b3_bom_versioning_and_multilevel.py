"""BOM versioning + multi-level support

Revision ID: c8e2d4f6a1b3
Revises: b3f7a1c5e9d2
Create Date: 2026-08-18 01:00:00.000000

"""
from alembic import op
import sqlalchemy as sa
from datetime import datetime
import uuid


revision = 'c8e2d4f6a1b3'
down_revision = 'b3f7a1c5e9d2'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'bom_versions',
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('finished_good_id', sa.String(length=36), nullable=False),
        sa.Column('version', sa.Integer(), nullable=False),
        sa.Column('is_active', sa.Boolean(), nullable=True),
        sa.Column('notes', sa.Text(), nullable=True),
        sa.Column('created_by', sa.String(length=36), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['finished_good_id'], ['internal_products.id'], name=op.f('fk_bom_versions_finished_good_id_internal_products')),
        sa.ForeignKeyConstraint(['created_by'], ['users.id'], name=op.f('fk_bom_versions_created_by_users')),
        sa.PrimaryKeyConstraint('id', name=op.f('pk_bom_versions')),
        sa.UniqueConstraint('finished_good_id', 'version', name='uq_bom_version'),
    )

    op.add_column('product_bom', sa.Column('bom_version_id', sa.String(length=36), nullable=True))

    # --- Backfill: one BOMVersion (v1, active) per distinct existing
    # finished_good_id, then point its rows at it ---
    conn = op.get_bind()
    distinct_fgs = conn.execute(sa.text(
        "SELECT DISTINCT finished_good_id FROM product_bom WHERE finished_good_id IS NOT NULL"
    )).fetchall()

    now = datetime.utcnow()
    for (fg_id,) in distinct_fgs:
        version_id = str(uuid.uuid4())
        conn.execute(sa.text(
            "INSERT INTO bom_versions (id, finished_good_id, version, is_active, created_at) "
            "VALUES (:id, :fg_id, 1, true, :now)"
        ), {"id": version_id, "fg_id": fg_id, "now": now})
        conn.execute(sa.text(
            "UPDATE product_bom SET bom_version_id = :version_id WHERE finished_good_id = :fg_id"
        ), {"version_id": version_id, "fg_id": fg_id})

    with op.batch_alter_table('product_bom') as batch_op:
        batch_op.alter_column('bom_version_id', nullable=False)
        batch_op.create_foreign_key(
            op.f('fk_product_bom_bom_version_id_bom_versions'), 'bom_versions', ['bom_version_id'], ['id']
        )
        batch_op.drop_constraint('fk_finished_good_id_internal_products', type_='foreignkey')
        batch_op.drop_column('finished_good_id')


def downgrade():
    op.add_column('product_bom', sa.Column('finished_good_id', sa.String(length=36), nullable=True))

    conn = op.get_bind()
    conn.execute(sa.text(
        "UPDATE product_bom SET finished_good_id = bv.finished_good_id "
        "FROM bom_versions bv WHERE product_bom.bom_version_id = bv.id"
    ))

    with op.batch_alter_table('product_bom') as batch_op:
        batch_op.drop_constraint(op.f('fk_product_bom_bom_version_id_bom_versions'), type_='foreignkey')
        batch_op.drop_column('bom_version_id')
        batch_op.create_foreign_key(
            'fk_finished_good_id_internal_products', 'internal_products', ['finished_good_id'], ['id']
        )

    op.drop_table('bom_versions')
