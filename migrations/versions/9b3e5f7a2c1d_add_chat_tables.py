"""add chat tables

Revision ID: 9b3e5f7a2c1d
Revises: 27f3a8c1d4e2
Create Date: 2026-08-03 00:00:02.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '9b3e5f7a2c1d'
down_revision = '27f3a8c1d4e2'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'chat_channels',
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('type', sa.String(length=10), nullable=False),
        sa.Column('name', sa.String(length=150), nullable=True),
        sa.Column('created_by', sa.String(length=36), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['created_by'], ['users.id'], name=op.f('fk_created_by_users')),
        sa.PrimaryKeyConstraint('id', name=op.f('pk_chat_channels')),
    )

    op.create_table(
        'chat_channel_members',
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('channel_id', sa.String(length=36), nullable=False),
        sa.Column('user_id', sa.String(length=36), nullable=False),
        sa.Column('joined_at', sa.DateTime(), nullable=True),
        sa.Column('last_read_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['channel_id'], ['chat_channels.id'], name=op.f('fk_channel_id_chat_channels')),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], name=op.f('fk_user_id_users')),
        sa.PrimaryKeyConstraint('id', name=op.f('pk_chat_channel_members')),
        sa.UniqueConstraint('channel_id', 'user_id', name='uq_chat_channel_user'),
    )

    op.create_table(
        'chat_messages',
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('channel_id', sa.String(length=36), nullable=False),
        sa.Column('sender_id', sa.String(length=36), nullable=False),
        sa.Column('body', sa.Text(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['channel_id'], ['chat_channels.id'], name=op.f('fk_channel_id_chat_channels')),
        sa.ForeignKeyConstraint(['sender_id'], ['users.id'], name=op.f('fk_sender_id_users')),
        sa.PrimaryKeyConstraint('id', name=op.f('pk_chat_messages')),
    )


def downgrade():
    op.drop_table('chat_messages')
    op.drop_table('chat_channel_members')
    op.drop_table('chat_channels')
