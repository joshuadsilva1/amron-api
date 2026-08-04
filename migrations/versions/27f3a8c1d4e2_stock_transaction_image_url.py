"""stock_transaction image_url

Revision ID: 27f3a8c1d4e2
Revises: 16143b6947a9
Create Date: 2026-08-03 00:00:01.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '27f3a8c1d4e2'
down_revision = '16143b6947a9'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('stock_transactions', schema=None) as batch_op:
        batch_op.add_column(sa.Column('image_url', sa.String(length=255), nullable=True))


def downgrade():
    with op.batch_alter_table('stock_transactions', schema=None) as batch_op:
        batch_op.drop_column('image_url')
