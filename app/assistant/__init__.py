# app/assistant/__init__.py
from datetime import datetime, timedelta
from threading import Lock
from typing import Optional

from flask import (
    Blueprint,
    render_template,
    request,
    session,
    jsonify,
    redirect,
    current_app,
)
from flask_login import current_user
from flask_socketio import SocketIO, emit, join_room, leave_room
from sqlalchemy import desc

from app import db
from app.models import ChatSession, ChatMessage, User, Seller, Stockist

# --------------------------------------------------------------------
# Socket.IO: created here; initialized in app.create_app(...) via
# assistant_socketio.init_app(app, message_queue=app.config.get("REDIS_URL"))
# --------------------------------------------------------------------
socketio = SocketIO(cors_allowed_origins="*")

assistant_bp = Blueprint("assistant", __name__, url_prefix="/assistant")

# --------------------------------------------------------------------
# Text & constants
# --------------------------------------------------------------------
WELCOME_TMPL = "{name} जी, स्वागत है! हम आपको एडमिन से जोड़ रहे हैं…"
NO_ADMIN_FALLBACK = (
    "इस समय कोई एडमिन उपलब्ध नहीं है। कृपया अपना संदेश लिख दें; "
    "आपको उपयुक्त उत्तर बाद में दिया जाएगा जिसे आप बाद में देख सकते हैं।"
)

# Guards to avoid duplicates across threads/workers
_pending_timeouts = set()     # sessions with a timer running
_fallback_fired = set()       # sessions where fallback already posted
_timeouts_lock = Lock()
_fallback_lock = Lock()

# --------------------------------------------------------------------
# Helpers
# --------------------------------------------------------------------
def room_name(session_id: int) -> str:
    return f"chat_session_{session_id}"


def _authorized_for_session(s: ChatSession) -> bool:
    """
    Admin can see all; user can see only his/her own mobile session.
    Uses flask session flags you already set during auth.
    """
    if session.get("is_admin"):
        return True
    mob = session.get("mobile")
    return bool(mob and s and s.user_mobile == mob)


def get_or_create_account_session(user_mobile: str) -> ChatSession:
    s = (
        ChatSession.query.filter_by(user_mobile=user_mobile, status="open")
        .order_by(desc(ChatSession.created_at))
        .first()
    )
    if s:
        return s
    s = ChatSession(user_mobile=user_mobile, status="open", last_activity=datetime.utcnow())
    db.session.add(s)
    db.session.commit()
    return s


def _has_fallback_in_db(session_id: int) -> bool:
    return (
        db.session.query(ChatMessage.id)
        .filter(
            ChatMessage.session_id == session_id,
            ChatMessage.sender_type == "system",
            ChatMessage.message == NO_ADMIN_FALLBACK,
        )
        .first()
        is not None
    )


def _schedule_admin_timeout(session_id: int) -> None:
    """
    After 60s, if no admin joined and fallback not yet posted, post it ONCE.
    Uses socketio.start_background_task so it works with eventlet/gevent/threading.
    """
    # If already posted (or found in DB), mark and skip
    with _fallback_lock:
        if session_id in _fallback_fired or _has_fallback_in_db(session_id):
            _fallback_fired.add(session_id)
            return

    # Ensure only one timer per session
    with _timeouts_lock:
        if session_id in _pending_timeouts:
            return
        _pending_timeouts.add(session_id)

    app_obj = current_app._get_current_object()

    def worker(sid: int, _app):
        # Sleep without blocking workers
        socketio.sleep(60)
        with _app.app_context():
            try:
                s = ChatSession.query.get(sid)
                if not s:
                    return
                # If an admin joined or fallback already there, skip
                if s.assigned_agent or _has_fallback_in_db(sid):
                    return

                db.session.add(
                    ChatMessage(
                        session_id=sid,
                        sender_type="system",
                        message=NO_ADMIN_FALLBACK,
                    )
                )
                db.session.commit()

                with _fallback_lock:
                    _fallback_fired.add(sid)

                socketio.emit(
                    "message",
                    {"sender": "system", "text": NO_ADMIN_FALLBACK, "alert": True},
                    room=room_name(sid),
                )
            finally:
                with _timeouts_lock:
                    _pending_timeouts.discard(sid)

    socketio.start_background_task(worker, session_id, app_obj)


def _lookup_user_name(mobile: Optional[str]) -> Optional[str]:
    if not mobile:
        return None
    u = User.query.filter_by(mobile=str(mobile).strip()).first()
    return (u.name or u.mobile) if u else None


def _display_name_for_mobile(mobile: Optional[str]) -> str:
    """
    Prefer Seller.name, then Stockist.name, then User.name, else the mobile itself.
    """
    if not mobile:
        return "यूज़र"
    m = str(mobile).strip()

    seller = Seller.query.filter_by(mobile=m).first()
    if seller and seller.name:
        return seller.name

    stockist = Stockist.query.filter_by(mobile=m).first()
    if stockist and stockist.name:
        return stockist.name

    user = User.query.filter_by(mobile=m).first()
    if user and (user.name or user.mobile):
        return user.name or user.mobile

    return m


def _post_welcome_and_connecting(s: ChatSession) -> None:
    """
    Send a welcome with the actual user's name, alert admins, and start the 60s fallback timer.
    """
    name = _display_name_for_mobile(s.user_mobile) or s.user_mobile or "यूज़र"
    welcome = WELCOME_TMPL.format(name=name)

    # Persist and emit welcome once
    db.session.add(ChatMessage(session_id=s.id, sender_type="system", message=welcome))
    db.session.commit()
    emit("message", {"sender": "system", "text": welcome}, room=room_name(s.id))

    # Alert admins (toast) and start fallback timer once
    emit("agent_alert", {"session_id": s.id, "user_mobile": s.user_mobile}, room="agents")
    _schedule_admin_timeout(s.id)

# --------------------------------------------------------------------
# Pages
# --------------------------------------------------------------------
@assistant_bp.route("/account", endpoint="account_chat")
def account_chat():
    user_mobile = session.get("mobile")
    if not user_mobile:
        return redirect("/user/login?next=/assistant/account")

    s = get_or_create_account_session(user_mobile)
    msgs = (
        ChatMessage.query.filter_by(session_id=s.id)
        .order_by(ChatMessage.created_at.asc())
        .all()
    )

    user_display_name = _display_name_for_mobile(user_mobile)

    return render_template(
        "assistant/chat.html",
        sess=s,
        messages=msgs,
        scope="account",
        user_display_name=user_display_name,
    )


@assistant_bp.route("/admin", endpoint="admin_console")
def admin_console():
    if not session.get("is_admin"):
        return redirect("/login?next=/assistant/admin")

    since = datetime.utcnow() - timedelta(days=7)
    sessions = (
        ChatSession.query.filter(ChatSession.created_at >= since)
        .order_by(desc(ChatSession.last_activity))
        .all()
    )

    mobiles = {s.user_mobile for s in sessions if s.user_mobile}
    names_map = {m: _display_name_for_mobile(m) for m in mobiles}

    return render_template("assistant/admin.html", sessions=sessions, names_map=names_map)


@assistant_bp.route("/api/session/<int:sid>/messages", endpoint="fetch_messages")
def fetch_messages(sid: int):
    if not session.get("is_admin"):
        return redirect("/login?next=/assistant/admin")
    msgs = (
        ChatMessage.query.filter_by(session_id=sid)
        .order_by(ChatMessage.created_at.asc())
        .all()
    )
    data = [
        {
            "id": m.id,
            "sender_type": m.sender_type,
            "sender_id": m.sender_id,
            "message": m.message,
            "created_at": m.created_at.isoformat() if m.created_at else None,
        }
        for m in msgs
    ]
    return jsonify(data)


@assistant_bp.route("/close/<int:sid>", methods=["POST"], endpoint="close_chat")
def close_chat(sid: int):
    if not session.get("is_admin"):
        return redirect("/login?next=/assistant/admin")
    s = ChatSession.query.get_or_404(sid)
    if s.status != "closed":
        s.status = "closed"
        db.session.add(
            ChatMessage(
                session_id=sid,
                sender_type="system",
                message="यह चैट एडमिन द्वारा बंद कर दी गई है।",
            )
        )
        db.session.commit()
        # Notify both sides to update UI
        socketio.emit(
            "status_update", {"session_id": sid, "status": "closed"}, room=room_name(sid)
        )
        socketio.emit(
            "status_update", {"session_id": sid, "status": "closed"}, room="agents"
        )
        socketio.emit(
            "message",
            {"sender": "system", "text": "यह चैट एडमिन द्वारा बंद कर दी गई है।"},
            room=room_name(sid),
        )
    return ("", 204)

# --------------------------------------------------------------------
# Socket.IO Events
# --------------------------------------------------------------------
@socketio.on("join")
def on_join(data):
    sid = int(data["session_id"])
    s = ChatSession.query.get(sid)
    if not s or not _authorized_for_session(s):
        return
    join_room(room_name(sid))


@socketio.on("leave")
def on_leave(data):
    sid = int(data["session_id"])
    s = ChatSession.query.get(sid)
    if not s or not _authorized_for_session(s):
        return
    leave_room(room_name(sid))


@socketio.on("user_message")
def on_user_message(data):
    sid = int(data["session_id"])
    text = (data.get("text") or "").strip()
    if not text:
        return

    s = ChatSession.query.get(sid)
    if not s or not _authorized_for_session(s):
        return

    # If closed, don't accept user messages; inform once
    if s.status != "open":
        emit(
            "message",
            {
                "sender": "system",
                "text": "यह चैट बंद है। कृपया नई चैट शुरू करने हेतु बाद में पुनः प्रयास करें।",
            },
            room=room_name(sid),
        )
        return

    # Store & echo user message
    db.session.add(ChatMessage(session_id=sid, sender_type="user", message=text))
    s.last_activity = datetime.utcnow()
    db.session.commit()
    emit("message", {"sender": "user", "text": text}, room=room_name(sid))

    # First message → escalate & welcome
    if not getattr(s, "escalated", False):
        s.escalated = True
        db.session.commit()
        _post_welcome_and_connecting(s)
        return

    # Already escalated → ping admins; schedule fallback only if never fired
    emit("agent_alert", {"session_id": s.id, "user_mobile": s.user_mobile}, room="agents")
    with _fallback_lock:
        if (s.id not in _fallback_fired) and (not _has_fallback_in_db(s.id)):
            _schedule_admin_timeout(s.id)


@socketio.on("agent_join")
def on_agent_join(data):
    if not session.get("is_admin"):
        return
    join_room("agents")

    if "session_id" in data:
        sid = int(data["session_id"])
        s = ChatSession.query.get(sid)
        if not s:
            return

        join_room(room_name(sid))

        admin_name = session.get("admin_name") or "admin"
        if not s.assigned_agent:
            s.assigned_agent = admin_name
            db.session.commit()

            joined_msg = f"एडमिन {admin_name} ने चैट जॉइन की है।"
            db.session.add(
                ChatMessage(session_id=sid, sender_type="system", message=joined_msg)
            )
            db.session.commit()
            emit(
                "message",
                {"sender": "system", "text": joined_msg},
                room=room_name(sid),
            )

        # prevent future fallbacks
        with _fallback_lock:
            _fallback_fired.add(s.id)


@socketio.on("agent_message")
def on_agent_message(data):
    if not session.get("is_admin"):
        return

    sid = int(data["session_id"])
    text = (data.get("text") or "").strip()
    if not text:
        return

    s = ChatSession.query.get(sid)
    if not s:
        return

    # Don't allow sending into closed chats (keeps logic clean)
    if s.status != "open":
        emit(
            "message",
            {"sender": "system", "text": "यह चैट बंद है; संदेश नहीं भेजा जा सकता।"},
            room=room_name(sid),
        )
        return

    sender_id = session.get("admin_name") or "admin"
    if not s.assigned_agent:
        s.assigned_agent = sender_id

    db.session.add(
        ChatMessage(
            session_id=sid, sender_type="agent", sender_id=sender_id, message=text
        )
    )
    s.last_activity = datetime.utcnow()
    db.session.commit()

    emit(
        "message",
        {"sender": "agent", "text": text, "agent": sender_id},
        room=room_name(sid),
    )

    # ensure fallback won't post later
    with _fallback_lock:
        _fallback_fired.add(s.id)
