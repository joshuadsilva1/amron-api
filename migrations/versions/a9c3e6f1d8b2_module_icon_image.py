"""app_modules.icon_image_url — an optional uploaded PNG in place of a
named Feather icon. `icon` (the Feather name) is kept either way: it's
used directly when no image is set, and as the fallback render if the
image URL fails to load.

Revision ID: a9c3e6f1d8b2
Revises: f8a2c5e7b1d4
Create Date: 2026-09-25 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


revision = 'a9c3e6f1d8b2'
down_revision = 'f8a2c5e7b1d4'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('app_modules', sa.Column('icon_image_url', sa.String(length=500), nullable=True))


def downgrade():
    op.drop_column('app_modules', 'icon_image_url')
