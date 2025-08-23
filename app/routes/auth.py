from __future__ import annotations
from datetime import datetime, timedelta
from flask import Blueprint, render_template, redirect, url_for, request, flash, session
from flask_login import login_user, logout_user, login_required, current_user
from app.models import User
from app import db, login_manager

bp = Blueprint("auth", __name__)

# === Auto-logout after 10 minutes of inactivity ===
INACTIVITY_MINUTES = 10
INACTIVITY_DELTA = timedelta(minutes=INACTIVITY_MINUTES)

def _is_admin(user: User) -> bool:
    try:
        return bool(
            getattr(user, "is_admin", False)
            or (getattr(user, "role", "").lower() == "admin")
            or (getattr(user, "mobile", "") == "admin")
        )
    except Exception:
        return False

@bp.before_app_request
def _enforce_inactivity_logout():
    if not current_user.is_authenticated:
        session.pop("last_activity", None)
        return

    endpoint = (request.endpoint or "")
    if endpoint.startswith("static"):
        return

    last = session.get("last_activity")
    now = datetime.utcnow()
    try:
        last_dt = datetime.fromisoformat(last) if isinstance(last, str) else None
    except Exception:
        last_dt = None

    if last_dt and (now - last_dt) > INACTIVITY_DELTA:
        logout_user()
        session.pop("is_admin", None)
        session.pop("admin_name", None)
        session.pop("last_activity", None)
        flash(f"Logged out after {INACTIVITY_MINUTES} minutes of inactivity.", "warning")
        return redirect(url_for("auth.login", next=request.path))

    session["last_activity"] = now.isoformat(timespec="seconds")

@bp.route("/")
def home():
    return render_template("index.html")

@bp.route("/faq")
def faq():
    return render_template("faq.html")

@bp.route("/how-to")
def guide():
    return render_template("how-to.html")

@bp.route("/login", methods=["GET", "POST"])
def login():
    next_url = request.args.get("next") or request.form.get("next") or url_for("auth.dashboard")
    if request.method == "POST":
        mobile = request.form.get("mobile", "").strip()
        password = request.form.get("password", "")
        user = User.query.filter_by(mobile=mobile).first()

        if user and user.check_password(password):
            login_user(user)

            is_admin = _is_admin(user)
            session["is_admin"] = is_admin
            session["admin_name"] = getattr(user, "name", None) or getattr(user, "mobile", "admin")

            session.permanent = True
            session["last_activity"] = datetime.utcnow().isoformat(timespec="seconds")

            return redirect(next_url or url_for("auth.dashboard"))

        flash("Invalid credentials", "danger")

    return render_template("login.html", next_url=next_url)

@bp.route("/logout")
@login_required
def logout():
    logout_user()
    session.pop("is_admin", None)
    session.pop("admin_name", None)
    session.pop("last_activity", None)
    return redirect(url_for("auth.login"))

@bp.route("/dashboard")
@login_required
def dashboard():
    return render_template("dashboard.html")

# ===== Admin: Change Password =====
@bp.route("/admin/change-password", methods=["GET", "POST"])
@login_required
def admin_change_password():
    if not session.get("is_admin") and not _is_admin(current_user):
        flash("You are not authorized to access that page.", "danger")
        return redirect(url_for("auth.dashboard"))

    if request.method == "POST":
        current_pw = request.form.get("current_password", "")
        new_pw = request.form.get("new_password", "")
        confirm_pw = request.form.get("confirm_password", "")

        if not current_user.check_password(current_pw):
            flash("Current password is incorrect.", "danger")
            return redirect(url_for("auth.admin_change_password"))

        if len(new_pw) < 6:
            flash("New password must be at least 6 characters.", "warning")
            return redirect(url_for("auth.admin_change_password"))

        if new_pw != confirm_pw:
            flash("New password and confirmation do not match.", "warning")
            return redirect(url_for("auth.admin_change_password"))

        current_user.set_password(new_pw)
        db.session.commit()
        flash("Password updated successfully.", "success")
        return redirect(url_for("auth.dashboard"))

    admin_name = session.get("admin_name") or getattr(current_user, "name", "Admin")
    # <-- uses templates/change_password.html
    return render_template("change_password.html", admin_name=admin_name)
