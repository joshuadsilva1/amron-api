from flask import Blueprint, request, jsonify, g
from datetime import datetime
from app import db
from app.models.chat import ChatChannel, ChatChannelMember, ChatMessage
from app.models.user import User
from app.core.decorators import jwt_required

chat_bp = Blueprint('chat', __name__)


def _user_label(user):
    if not user:
        return "Unknown User"
    return user.full_name or user.phone_number or "Unknown User"


def _require_membership(channel_id, user_id):
    return ChatChannelMember.query.filter_by(channel_id=channel_id, user_id=user_id).first()


@chat_bp.route('/users', methods=['GET', 'OPTIONS'], strict_slashes=False)
@jwt_required
def get_chat_directory():
    """Every active user in the system, for starting a DM or picking group members."""
    if request.method == 'OPTIONS':
        return jsonify({}), 200

    users = User.query.filter(User.is_active == True, User.id != g.current_user.id).all()
    return jsonify({
        "status": "success",
        "users": [{
            "id": u.id,
            "name": _user_label(u),
            "role_name": u.role_data.name if u.role_data else None,
            "department_id": u.department_id,
        } for u in users]
    }), 200


@chat_bp.route('/channels', methods=['GET', 'OPTIONS'], strict_slashes=False)
@jwt_required
def get_channels():
    """Every DM/group channel the current user belongs to, newest activity first."""
    if request.method == 'OPTIONS':
        return jsonify({}), 200

    memberships = ChatChannelMember.query.filter_by(user_id=g.current_user.id).all()

    result = []
    for membership in memberships:
        channel = ChatChannel.query.get(membership.channel_id)
        if not channel:
            continue

        last_message = ChatMessage.query.filter_by(channel_id=channel.id) \
            .order_by(ChatMessage.created_at.desc()).first()

        if channel.type == 'DM':
            other_membership = ChatChannelMember.query.filter(
                ChatChannelMember.channel_id == channel.id,
                ChatChannelMember.user_id != g.current_user.id
            ).first()
            other_user = User.query.get(other_membership.user_id) if other_membership else None
            display_name = _user_label(other_user)
        else:
            display_name = channel.name or "Group"

        unread_count = ChatMessage.query.filter(
            ChatMessage.channel_id == channel.id,
            ChatMessage.sender_id != g.current_user.id,
            ChatMessage.created_at > (membership.last_read_at or datetime.min)
        ).count()

        result.append({
            "channel_id": channel.id,
            "type": channel.type,
            "name": display_name,
            "last_message": last_message.body if last_message else None,
            "last_message_at": last_message.created_at.isoformat() if last_message else channel.created_at.isoformat(),
            "unread_count": unread_count,
        })

    result.sort(key=lambda c: c["last_message_at"], reverse=True)
    return jsonify({"status": "success", "channels": result}), 200


@chat_bp.route('/dm', methods=['POST', 'OPTIONS'], strict_slashes=False)
@jwt_required
def open_dm():
    """Finds the existing DM channel with the given user, or creates one."""
    if request.method == 'OPTIONS':
        return jsonify({}), 200

    data = request.get_json(silent=True) or {}
    other_user_id = data.get('user_id')

    if not other_user_id:
        return jsonify({"error": "user_id is required"}), 400
    if other_user_id == g.current_user.id:
        return jsonify({"error": "Cannot start a DM with yourself"}), 400

    other_user = User.query.get(other_user_id)
    if not other_user:
        return jsonify({"error": "User not found"}), 404

    my_dm_channel_ids = {
        m.channel_id for m in ChatChannelMember.query.filter_by(user_id=g.current_user.id).all()
    }
    their_dm_channel_ids = {
        m.channel_id for m in ChatChannelMember.query.filter_by(user_id=other_user_id).all()
    }
    shared_ids = my_dm_channel_ids & their_dm_channel_ids
    if shared_ids:
        existing = ChatChannel.query.filter(
            ChatChannel.id.in_(shared_ids), ChatChannel.type == 'DM'
        ).first()
        if existing:
            return jsonify({"status": "success", "channel_id": existing.id}), 200

    new_channel = ChatChannel(type='DM', created_by=g.current_user.id)
    db.session.add(new_channel)
    db.session.flush()

    db.session.add(ChatChannelMember(channel_id=new_channel.id, user_id=g.current_user.id))
    db.session.add(ChatChannelMember(channel_id=new_channel.id, user_id=other_user_id))

    try:
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        return jsonify({"error": str(e)}), 500

    return jsonify({"status": "success", "channel_id": new_channel.id}), 201


@chat_bp.route('/channels', methods=['POST', 'OPTIONS'], strict_slashes=False)
@jwt_required
def create_group_channel():
    if request.method == 'OPTIONS':
        return jsonify({}), 200

    data = request.get_json(silent=True) or {}
    name = (data.get('name') or '').strip()
    member_ids = data.get('member_ids') or []

    if not name:
        return jsonify({"error": "Channel name is required"}), 400
    if not isinstance(member_ids, list) or len(member_ids) == 0:
        return jsonify({"error": "At least one other member is required"}), 400

    valid_users = User.query.filter(User.id.in_(member_ids)).all()
    if len(valid_users) != len(set(member_ids)):
        return jsonify({"error": "One or more selected members were not found"}), 404

    new_channel = ChatChannel(type='GROUP', name=name, created_by=g.current_user.id)
    db.session.add(new_channel)
    db.session.flush()

    all_member_ids = set(member_ids) | {g.current_user.id}
    for uid in all_member_ids:
        db.session.add(ChatChannelMember(channel_id=new_channel.id, user_id=uid))

    try:
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        return jsonify({"error": str(e)}), 500

    return jsonify({"status": "success", "channel_id": new_channel.id}), 201


@chat_bp.route('/channels/<channel_id>/messages', methods=['GET', 'OPTIONS'], strict_slashes=False)
@jwt_required
def get_messages(channel_id):
    if request.method == 'OPTIONS':
        return jsonify({}), 200

    if not _require_membership(channel_id, g.current_user.id):
        return jsonify({"error": "You are not a member of this channel"}), 403

    after_id = request.args.get('after')
    query = ChatMessage.query.filter_by(channel_id=channel_id)

    if after_id:
        cursor_message = ChatMessage.query.get(after_id)
        if cursor_message:
            query = query.filter(ChatMessage.created_at > cursor_message.created_at)
        messages = query.order_by(ChatMessage.created_at.asc()).all()
    else:
        messages = query.order_by(ChatMessage.created_at.desc()).limit(100).all()
        messages.reverse()

    sender_ids = {m.sender_id for m in messages}
    senders = {u.id: u for u in User.query.filter(User.id.in_(sender_ids)).all()} if sender_ids else {}

    return jsonify({
        "status": "success",
        "messages": [{
            "id": m.id,
            "sender_id": m.sender_id,
            "sender_name": _user_label(senders.get(m.sender_id)),
            "body": m.body,
            "created_at": m.created_at.isoformat(),
        } for m in messages]
    }), 200


@chat_bp.route('/channels/<channel_id>/messages', methods=['POST', 'OPTIONS'], strict_slashes=False)
@jwt_required
def send_message(channel_id):
    if request.method == 'OPTIONS':
        return jsonify({}), 200

    membership = _require_membership(channel_id, g.current_user.id)
    if not membership:
        return jsonify({"error": "You are not a member of this channel"}), 403

    data = request.get_json(silent=True) or {}
    body = (data.get('body') or '').strip()
    if not body:
        return jsonify({"error": "Message body is required"}), 400

    new_message = ChatMessage(channel_id=channel_id, sender_id=g.current_user.id, body=body)
    db.session.add(new_message)
    membership.last_read_at = datetime.utcnow()

    try:
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        return jsonify({"error": str(e)}), 500

    return jsonify({
        "status": "success",
        "message": {
            "id": new_message.id,
            "sender_id": new_message.sender_id,
            "sender_name": _user_label(g.current_user),
            "body": new_message.body,
            "created_at": new_message.created_at.isoformat(),
        }
    }), 201


@chat_bp.route('/channels/<channel_id>/read', methods=['POST', 'OPTIONS'], strict_slashes=False)
@jwt_required
def mark_channel_read(channel_id):
    if request.method == 'OPTIONS':
        return jsonify({}), 200

    membership = _require_membership(channel_id, g.current_user.id)
    if not membership:
        return jsonify({"error": "You are not a member of this channel"}), 403

    membership.last_read_at = datetime.utcnow()

    try:
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        return jsonify({"error": str(e)}), 500

    return jsonify({"status": "success"}), 200
