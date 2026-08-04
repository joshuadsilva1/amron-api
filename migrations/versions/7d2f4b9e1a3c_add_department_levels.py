"""add department levels table

Revision ID: 7d2f4b9e1a3c
Revises: 4a7c9e2f6b8d
Create Date: 2026-08-05 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '7d2f4b9e1a3c'
down_revision = '4a7c9e2f6b8d'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'department_levels',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('name', sa.String(length=50), nullable=False),
        sa.Column('rank', sa.Integer(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint('id', name=op.f('pk_department_levels')),
        sa.UniqueConstraint('name', name=op.f('uq_department_levels_name')),
        sa.UniqueConstraint('rank', name=op.f('uq_department_levels_rank')),
    )

    # Seed with the 3 levels already in use, matching the names the admin
    # UI already displayed (Bottom/Middle/Top) so nothing changes for
    # existing departments — this just makes the set editable going forward.
    department_levels = sa.table(
        'department_levels',
        sa.column('name', sa.String),
        sa.column('rank', sa.Integer),
    )
    op.bulk_insert(department_levels, [
        {'name': 'Bottom', 'rank': 0},
        {'name': 'Middle', 'rank': 1},
        {'name': 'Top', 'rank': 2},
    ])


def downgrade():
    op.drop_table('department_levels')
