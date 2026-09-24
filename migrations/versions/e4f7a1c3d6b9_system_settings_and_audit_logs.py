"""system_settings (admin-configurable key/value store) and audit_logs
(immutable trail for non-inventory sensitive actions)

Revision ID: e4f7a1c3d6b9
Revises: d3e6f9a2b4c8
Create Date: 2026-09-23 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


revision = 'e4f7a1c3d6b9'
down_revision = 'd3e6f9a2b4c8'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'system_settings',
        sa.Column('key', sa.String(length=100), nullable=False),
        sa.Column('value', sa.Text(), nullable=True),
        sa.Column('description', sa.String(length=255), nullable=True),
        sa.Column('updated_by', sa.String(length=36), nullable=True),
        sa.Column('updated_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['updated_by'], ['users.id']),
        sa.PrimaryKeyConstraint('key'),
    )

    op.create_table(
        'audit_logs',
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('user_id', sa.String(length=36), nullable=True),
        sa.Column('user_label', sa.String(length=150), nullable=True),
        sa.Column('action', sa.String(length=100), nullable=False),
        sa.Column('resource_type', sa.String(length=100), nullable=False),
        sa.Column('resource_id', sa.String(length=100), nullable=True),
        sa.Column('payload_before', sa.JSON(), nullable=True),
        sa.Column('payload_after', sa.JSON(), nullable=True),
        sa.Column('ip_address', sa.String(length=64), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['user_id'], ['users.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_audit_logs_created_at', 'audit_logs', ['created_at'])
    op.create_index('ix_audit_logs_resource_type', 'audit_logs', ['resource_type'])
    op.create_index('ix_audit_logs_user_id', 'audit_logs', ['user_id'])

    # Seed the one known setting so the admin UI has something to show/edit
    # immediately instead of an empty state.
    conn = op.get_bind()
    conn.execute(
        sa.text(
            "INSERT INTO system_settings (key, value, description) "
            "VALUES (:key, :value, :description) "
            "ON CONFLICT (key) DO NOTHING"
        ),
        {
            "key": "default_wastage_percent",
            "value": "10",
            "description": "Pre-filled wastage percent on a brand-new BOM component. "
                            "Each component can still be overridden individually.",
        },
    )


def downgrade():
    op.drop_index('ix_audit_logs_user_id', table_name='audit_logs')
    op.drop_index('ix_audit_logs_resource_type', table_name='audit_logs')
    op.drop_index('ix_audit_logs_created_at', table_name='audit_logs')
    op.drop_table('audit_logs')
    op.drop_table('system_settings')
