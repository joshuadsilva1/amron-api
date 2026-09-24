"""daily WhatsApp report subscriptions (recipient + send time per report)

Revision ID: b8d4f2a6c1e9
Revises: a3b7c9d1e2f4
Create Date: 2026-09-19 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


revision = 'b8d4f2a6c1e9'
down_revision = 'a3b7c9d1e2f4'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'report_subscriptions',
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('department_id', sa.String(length=36), nullable=True),
        sa.Column('recipient_number', sa.String(length=20), nullable=False),
        sa.Column('send_time', sa.String(length=5), nullable=False),
        sa.Column('is_enabled', sa.Integer(), nullable=True),
        sa.Column('last_sent_on', sa.Date(), nullable=True),
        sa.Column('last_status', sa.String(length=20), nullable=True),
        sa.Column('last_error', sa.Text(), nullable=True),
        sa.Column('updated_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['department_id'], ['departments.id']),
        sa.PrimaryKeyConstraint('id'),
    )


def downgrade():
    op.drop_table('report_subscriptions')
