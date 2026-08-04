"""add whatsapp_config table

Revision ID: 952cf21a9067
Revises: a07ba5ed14b4
Create Date: 2026-08-03 17:05:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '952cf21a9067'
down_revision = 'a07ba5ed14b4'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'whatsapp_config',
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('provider', sa.String(length=50), nullable=True),
        sa.Column('api_key', sa.String(length=255), nullable=True),
        sa.Column('app_name', sa.String(length=100), nullable=True),
        sa.Column('sender_number', sa.String(length=20), nullable=True),
        sa.Column('is_active', sa.Integer(), nullable=True),
        sa.Column('updated_at', sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint('id'),
    )


def downgrade():
    op.drop_table('whatsapp_config')
