"""stock_transaction quantity float

Revision ID: 16143b6947a9
Revises: 952cf21a9067
Create Date: 2026-08-03 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '16143b6947a9'
down_revision = '952cf21a9067'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('stock_transactions', schema=None) as batch_op:
        batch_op.alter_column(
            'quantity',
            existing_type=sa.Integer(),
            type_=sa.Float(),
            existing_nullable=False,
        )


def downgrade():
    with op.batch_alter_table('stock_transactions', schema=None) as batch_op:
        batch_op.alter_column(
            'quantity',
            existing_type=sa.Float(),
            type_=sa.Integer(),
            existing_nullable=False,
        )
