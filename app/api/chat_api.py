from functools import wraps

from flask import Blueprint, request, jsonify, g
from datetime import datetime
from app import db
from app.models.chat import ChatChannel, ChatChannelMember, ChatMessage
from app.models.department import Department
from app.models.user import User
from app.core.decorators import jwt_required

chat_bp = Blueprint('chat', __name__)

MAX_MESSAGE_LEN = 4000
MAX_GROUP_NAME_LEN = 100
MAX_GROUP_MEMBERS = 200
SEARCH_LIMIT = 30


def _is_approved(user):
    """A real, active, role-approved account. New sign-ups sit in the
    PENDING role until an admin approves them — they must not be able to
    read the directory or message anyone, and shouldn't appear in it."""
    return bool(user and user.is_active and user.role_data and user.role_data.name != 'PENDING')


def chat_access_required(f):
    """Chat is for approved, active accounts only. Stack under @jwt_required."""
    @wraps(f)
    def decorated(*args, **kwargs):
        if request.method == 'OPTIONS':
            return jsonify({}), 200
        if not _is_approved(g.current_user):
            return jsonify({"error": "Chat isn't available until your account is approved."}), 403
        return f(*args, **kwargs)
    return decorated


def _user_label(user):
    if not user:
        return "Unknown User"
    if user.full_name and user.full_name.strip() and user.full_name != 'Unknown':
        return user.full_name.strip()
    # Never fall back to the full phone number — that would show every
    # colleague's number to everyone. Last 4 digits is enough to tell apart.
    tail = (user.phone_number or '')[-4:]
    return f"User ••{tail}" if tail else "Unknown User"


def _department_names():
    return {d.id: d.name for d in Department.query.all()}


def _user_payload(user, dept_names):
    return {
        "id": user.id,
        "name": _user_label(user),
        "role_name": user.role_data.name if user.role_data else None,
        "department_id": user.department_id,
        "department_name": dept_names.get(user.department_id) if user.department_id else None,
    }


def _require_membership(channel_id, user_id):
    return ChatChannelMember.query.filter_by(channel_id=channel_id, user_id=user_id).first()


@chat_bp.route('/users', methods=['GET', 'OPTIONS'], strict_slashes=False)
@jwt_required
@chat_access_required
def get_chat_directory():
    """Active, approved colleagues you can start a DM with or add to a group."""
    if request.method == 'OPTIONS':
        return jsonify({}), 200

    dept_names = _department_names()
    users = [u for u in User.query.filter(User.is_active == True, User.id != g.current_user.id).all() if _is_approved(u)]
    return jsonify({
        "status": "success",
        "users": [_user_payload(u, dept_names) for u in users]
    }), 200


@chat_bp.route('/channels', methods=['GET', 'OPTIONS'], strict_slashes=False)
@jwt_required
@chat_access_required
def get_channels():
    """Every DM/group channel the current user belongs to, newest activity first."""
    if request.method == 'OPTIONS':
        return jsonify({}), 200

    memberships = ChatChannelMember.query.filter_by(user_id=g.current_user.id).all()
    dept_names = _department_names()

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
            other_payload = _user_payload(other_user, dept_names) if other_user else None
            member_count = 2
        else:
            display_name = channel.name or "Group"
            other_payload = None
            member_count = ChatChannelMember.query.filter_by(channel_id=channel.id).count()

        unread_count = ChatMessage.query.filter(
            ChatMessage.channel_id == channel.id,
            ChatMessage.sender_id != g.current_user.id,
            ChatMessage.created_at > (membership.last_read_at or datetime.min)
        ).count()

        result.append({
            "channel_id": channel.id,
            "type": channel.type,
            "name": display_name,
            "other_user": other_payload,
            "member_count": member_count,
            "last_message": last_message.body if last_message else None,
            "last_message_at": last_message.created_at.isoformat() if last_message else channel.created_at.isoformat(),
            "unread_count": unread_count,
        })

    result.sort(key=lambda c: c["last_message_at"], reverse=True)
    return jsonify({"status": "success", "channels": result}), 200


@chat_bp.route('/dm', methods=['POST', 'OPTIONS'], strict_slashes=False)
@jwt_required
@chat_access_required
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
    if not other_user or not _is_approved(other_user):
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
@chat_access_required
def create_group_channel():
    if request.method == 'OPTIONS':
        return jsonify({}), 200

    data = request.get_json(silent=True) or {}
    name = (data.get('name') or '').strip()
    member_ids = data.get('member_ids') or []

    if not name:
        return jsonify({"error": "Channel name is required"}), 400
    if len(name) > MAX_GROUP_NAME_LEN:
        return jsonify({"error": f"Group name can be at most {MAX_GROUP_NAME_LEN} characters"}), 400
    if not isinstance(member_ids, list) or not all(isinstance(m, str) for m in member_ids):
        return jsonify({"error": "member_ids must be a list of user ids"}), 400
    member_ids = list({m for m in member_ids if m != g.current_user.id})
    if len(member_ids) == 0:
        return jsonify({"error": "At least one other member is required"}), 400
    if len(member_ids) > MAX_GROUP_MEMBERS:
        return jsonify({"error": f"A group can have at most {MAX_GROUP_MEMBERS} members"}), 400

    valid_users = [u for u in User.query.filter(User.id.in_(member_ids)).all() if _is_approved(u)]
    if len(valid_users) != len(member_ids):
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
@chat_access_required
def get_messages(channel_id):
    if request.method == 'OPTIONS':
        return jsonify({}), 200

    if not _require_membership(channel_id, g.current_user.id):
        return jsonify({"error": "You are not a member of this channel"}), 403

    after_id = request.args.get('after')
    query = ChatMessage.query.filter_by(channel_id=channel_id)

    # The cursor only counts if it's a message in THIS channel; anything
    # else (stale/foreign id) falls back to the latest page instead of
    # dumping the whole history.
    cursor_message = ChatMessage.query.filter_by(id=after_id, channel_id=channel_id).first() if after_id else None
    if cursor_message:
        messages = query.filter(ChatMessage.created_at > cursor_message.created_at) \
            .order_by(ChatMessage.created_at.asc()).limit(500).all()
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
@chat_access_required
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
    if len(body) > MAX_MESSAGE_LEN:
        return jsonify({"error": f"Message is too long (max {MAX_MESSAGE_LEN} characters)"}), 400

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
@chat_access_required
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


@chat_bp.route('/channels/<channel_id>/members', methods=['GET', 'OPTIONS'], strict_slashes=False)
@jwt_required
@chat_access_required
def get_channel_members(channel_id):
    """Who's in a conversation — with role and department. Members only."""
    if request.method == 'OPTIONS':
        return jsonify({}), 200

    if not _require_membership(channel_id, g.current_user.id):
        return jsonify({"error": "You are not a member of this channel"}), 403

    dept_names = _department_names()
    member_ids = [m.user_id for m in ChatChannelMember.query.filter_by(channel_id=channel_id).all()]
    users = User.query.filter(User.id.in_(member_ids)).all() if member_ids else []
    return jsonify({
        "status": "success",
        "members": [{**_user_payload(u, dept_names), "is_me": u.id == g.current_user.id} for u in users]
    }), 200


@chat_bp.route('/search', methods=['GET', 'OPTIONS'], strict_slashes=False)
@jwt_required
@chat_access_required
def search_messages():
    """Full-text-ish search over message bodies — ONLY in channels the
    current user is a member of (the join on membership is what guarantees
    nobody can search into a conversation they aren't part of)."""
    if request.method == 'OPTIONS':
        return jsonify({}), 200

    q = (request.args.get('q') or '').strip()
    if len(q) < 2:
        return jsonify({"status": "success", "results": []}), 200

    # Escape LIKE wildcards so "50%" or "a_b" search literally.
    escaped = q.replace('\\', '\\\\').replace('%', '\\%').replace('_', '\\_')
    rows = db.session.query(ChatMessage).join(
        ChatChannelMember,
        db.and_(ChatChannelMember.channel_id == ChatMessage.channel_id,
                ChatChannelMember.user_id == g.current_user.id)
    ).filter(
        ChatMessage.body.ilike(f"%{escaped}%", escape='\\')
    ).order_by(ChatMessage.created_at.desc()).limit(SEARCH_LIMIT).all()

    channels = {c.id: c for c in ChatChannel.query.filter(ChatChannel.id.in_({m.channel_id for m in rows})).all()} if rows else {}
    senders = {u.id: u for u in User.query.filter(User.id.in_({m.sender_id for m in rows})).all()} if rows else {}

    results = []
    for m in rows:
        channel = channels.get(m.channel_id)
        if not channel:
            continue
        if channel.type == 'DM':
            other = ChatChannelMember.query.filter(
                ChatChannelMember.channel_id == channel.id, ChatChannelMember.user_id != g.current_user.id
            ).first()
            channel_name = _user_label(User.query.get(other.user_id)) if other else "Direct message"
        else:
            channel_name = channel.name or "Group"
        results.append({
            "message_id": m.id,
            "channel_id": channel.id,
            "channel_type": channel.type,
            "channel_name": channel_name,
            "sender_name": _user_label(senders.get(m.sender_id)),
            "body": m.body,
            "created_at": m.created_at.isoformat(),
        })
    return jsonify({"status": "success", "results": results}), 200
