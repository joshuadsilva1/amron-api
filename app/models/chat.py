from app import db
from app.core.utils import generate_uuid
from datetime import datetime


class ChatChannel(db.Model):
    """A DM thread (exactly 2 members) or a named group channel."""
    __tablename__ = 'chat_channels'

    id = db.Column(db.String(36), primary_key=True, default=generate_uuid)
    type = db.Column(db.String(10), nullable=False)  # 'DM' or 'GROUP'
    name = db.Column(db.String(150), nullable=True)  # required for GROUP, unused for DM

    created_by = db.Column(db.String(36), db.ForeignKey('users.id'), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


class ChatChannelMember(db.Model):
    __tablename__ = 'chat_channel_members'

    id = db.Column(db.String(36), primary_key=True, default=generate_uuid)
    channel_id = db.Column(db.String(36), db.ForeignKey('chat_channels.id'), nullable=False)
    user_id = db.Column(db.String(36), db.ForeignKey('users.id'), nullable=False)

    joined_at = db.Column(db.DateTime, default=datetime.utcnow)
    last_read_at = db.Column(db.DateTime, nullable=True)

    __table_args__ = (
        db.UniqueConstraint('channel_id', 'user_id', name='uq_chat_channel_user'),
    )


class ChatMessage(db.Model):
    __tablename__ = 'chat_messages'

    id = db.Column(db.String(36), primary_key=True, default=generate_uuid)
    channel_id = db.Column(db.String(36), db.ForeignKey('chat_channels.id'), nullable=False)
    sender_id = db.Column(db.String(36), db.ForeignKey('users.id'), nullable=False)

    body = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
