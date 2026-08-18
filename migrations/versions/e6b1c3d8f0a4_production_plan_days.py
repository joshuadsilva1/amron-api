"""production plan day lifecycle + variance reason

Revision ID: e6b1c3d8f0a4
Revises: d4a9f2b7e5c1
Create Date: 2026-08-19 01:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


revision = 'e6b1c3d8f0a4'
down_revision = 'd4a9f2b7e5c1'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'production_plan_days',
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('plan_date', sa.Date(), nullable=False),
        sa.Column('status', sa.String(length=20), nullable=True),
        sa.Column('created_by', sa.String(length=36), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.Column('updated_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['created_by'], ['users.id'], name=op.f('fk_production_plan_days_created_by_users')),
        sa.PrimaryKeyConstraint('id', name=op.f('pk_production_plan_days')),
        sa.UniqueConstraint('plan_date', name='uq_production_plan_day_date'),
    )
    op.add_column('daily_production_plans', sa.Column('variance_reason', sa.String(length=50), nullable=True))


def downgrade():
    op.drop_column('daily_production_plans', 'variance_reason')
    op.drop_table('production_plan_days')
