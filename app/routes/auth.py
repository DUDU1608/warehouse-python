# auth.py
from flask import Blueprint, render_template, redirect, url_for, request, flash, session
from flask_login import login_user, logout_user, login_required, current_user
from app.models import User
from app import db, login_manager

bp = Blueprint('auth', __name__)

@bp.route('/')
def home():
    return render_template('index.html')

@bp.route("/faq")
def faq():
    return render_template("faq.html")

@bp.route("/how-to")
def guide():
    return render_template("how-to.html")

@bp.route('/login', methods=['GET', 'POST'])
def login():
    # capture ?next=... (GET) or hidden field (POST)
    next_url = request.args.get('next') or request.form.get('next') or url_for('auth.dashboard')

    if request.method == 'POST':
        mobile = request.form.get('mobile', '').strip()
        password = request.form.get('password', '')
        user = User.query.filter_by(mobile=mobile).first()

        if user and user.check_password(password):
            login_user(user)

            # ✅ mark admin so /assistant/admin will pass the check
            is_admin = bool(
                getattr(user, "is_admin", False) or
                (getattr(user, "role", "").lower() == "admin") or
                (mobile == "admin")  # fallback if you don't have a role field yet
            )
            session["is_admin"] = is_admin
            session["admin_name"] = getattr(user, "name", None) or getattr(user, "mobile", "admin")

            return redirect(next_url or url_for('auth.dashboard'))

        flash("Invalid credentials", "danger")

    return render_template('login.html', next_url=next_url)

@bp.route('/logout')
@login_required
def logout():
    logout_user()
    session.pop("is_admin", None)
    session.pop("admin_name", None)
    return redirect(url_for('auth.login'))

@bp.route('/dashboard')
@login_required
def dashboard():
    return render_template('dashboard.html')
