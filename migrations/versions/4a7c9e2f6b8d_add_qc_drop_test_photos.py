"""add qc drop test photos

Revision ID: 4a7c9e2f6b8d
Revises: 9b3e5f7a2c1d
Create Date: 2026-08-04 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '4a7c9e2f6b8d'
down_revision = '9b3e5f7a2c1d'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('qc_inspections', schema=None) as batch_op:
        batch_op.add_column(sa.Column('drop_test_photo_1_url', sa.String(length=255), nullable=True))
        batch_op.add_column(sa.Column('drop_test_photo_2_url', sa.String(length=255), nullable=True))


def downgrade():
    with op.batch_alter_table('qc_inspections', schema=None) as batch_op:
        batch_op.drop_column('drop_test_photo_2_url')
        batch_op.drop_column('drop_test_photo_1_url')
