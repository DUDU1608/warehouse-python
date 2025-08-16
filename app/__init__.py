# app/__init__.py
import os
import logging
from datetime import datetime
from pathlib import Path

from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager
from flask_migrate import Migrate
from sqlalchemy import MetaData

from utils.hindi import to_hindi_name

# ----------------- Logging -----------------
log = logging.getLogger(__name__)

# ----------------- SQLAlchemy naming (portable across SQLite/Postgres/MySQL) -----------------
NAMING_CONVENTION = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}

# ----------------- Extensions -----------------
db = SQLAlchemy(metadata=MetaData(naming_convention=NAMING_CONVENTION))
login_manager = LoginManager()
migrate = Migrate()


# ----------------- Custom Filters -----------------
def format_inr(value):
    try:
        value = float(value or 0)
        s = f"{value:.2f}"
        int_part, dec_part = s.split(".")
        if len(int_part) <= 3:
            return f"₹{int_part}.{dec_part}"
        last_three = int_part[-3:]
        rest = int_part[:-3]
        # add commas in Indian style
        if rest:
            parts = []
            while len(rest) > 2:
                parts.append(rest[-2:])
                rest = rest[:-2]
            if rest:
                parts.append(rest)
            formatted = ",".join(reversed(parts)) + "," + last_three
        else:
            formatted = last_three
        return f"₹{formatted}.{dec_part}"
    except Exception:
        return "₹0.00"


def kg_to_mt(value):
    try:
        return "{:.2f} MT".format((value or 0) / 1000)
    except Exception:
        return "0.00 MT"


def format_date(value):
    try:
        if hasattr(value, "strftime"):
            return value.strftime("%d-%m-%Y")
        if isinstance(value, str):
            from datetime import datetime as _dt
            for fmt in ("%Y-%m-%d", "%Y-%m-%d %H:%M:%S"):
                try:
                    dt = _dt.strptime(value, fmt)
                    return dt.strftime("%d-%m-%Y")
                except ValueError:
                    continue
        return value
    except Exception:
        return value


# ----------------- App Factory -----------------
def create_app():
    app = Flask(__name__, instance_relative_config=True)

    # Instance path (allow override via env)
    custom_instance = os.environ.get("FLASK_INSTANCE_PATH")
    if custom_instance:
        app.instance_path = custom_instance

    os.makedirs(app.instance_path, exist_ok=True)

    # ---- Database URI resolution (Postgres-ready) ----
    # Prefer SQLALCHEMY_DATABASE_URI, then DATABASE_URL (Heroku-style), else SQLite fallback
    uri = os.environ.get("SQLALCHEMY_DATABASE_URI") or os.environ.get("DATABASE_URL")
    if not uri:
        db_path = Path(app.instance_path) / "warehouse.db"
        uri = f"sqlite:///{db_path}"
    # Heroku-style postgres prefix fix
    if uri.startswith("postgres://"):
        uri = uri.replace("postgres://", "postgresql://", 1)

    # Default config (can be overridden by env)
    app.config.from_mapping(
        SECRET_KEY=os.environ.get("SECRET_KEY", "your-secret-key"),
        SQLALCHEMY_DATABASE_URI=uri,
        SQLALCHEMY_TRACK_MODIFICATIONS=False,
        SQLALCHEMY_ENGINE_OPTIONS={"pool_pre_ping": True, "pool_recycle": 1800},
        SESSION_COOKIE_SAMESITE="Lax",
        REDIS_URL=os.environ.get("REDIS_URL"),  # for Socket.IO in prod (optional)
    )

    # Init extensions (order matters)
    db.init_app(app)
    login_manager.init_app(app)
    login_manager.login_view = "auth.login"  # admin login; user routes use their own guards
    migrate.init_app(app, db)

    # Register custom filters
    app.jinja_env.filters["format_inr"] = format_inr
    app.jinja_env.filters["kg_to_mt"] = kg_to_mt
    app.jinja_env.filters["format_date"] = format_date
    app.jinja_env.filters["to_hindi"] = to_hindi_name

    # ----------------- Blueprints -----------------
    # Public/auth routes (admin)
    try:
        from .routes import auth
        app.register_blueprint(auth.bp)
    except Exception as e:
        log.debug("Auth blueprint not registered: %s", e)

    # Seller module
    try:
        from app.routes.seller import dashboard as seller_dashboard, seller, purchase, payment, due
        app.register_blueprint(seller_dashboard.bp)
        app.register_blueprint(seller.bp)
        app.register_blueprint(purchase.bp)
        app.register_blueprint(payment.bp)
        app.register_blueprint(due.bp)
    except Exception as e:
        log.debug("Seller blueprints not fully registered: %s", e)

    # Stockist module
    try:
        from app.routes.stockist import (
            dashboard as stockist_dashboard,
            stockist,
            stockdata,
            stockexit,
            loandata,
            margindata,
            rental_calculator,
        )
        app.register_blueprint(stockist_dashboard.bp)
        app.register_blueprint(stockist.bp)
        app.register_blueprint(stockdata.bp)
        app.register_blueprint(stockexit.bp)
        app.register_blueprint(loandata.bp)
        app.register_blueprint(margindata.bp)
        app.register_blueprint(rental_calculator.bp)
    except Exception as e:
        log.debug("Stockist blueprints not fully registered: %s", e)

    # Company module
    try:
        from app.routes.company import (
            dashboard as company_dashboard,
            companyloan,
            loanrepayment,
            interest_payble,
            interest_receivable,
            rental_due,
            expenditure,
            breakeven_calculator,
            profit_loss,
            final_report,
        )
        app.register_blueprint(company_dashboard.bp)
        app.register_blueprint(companyloan.bp)
        app.register_blueprint(loanrepayment.bp)
        app.register_blueprint(interest_payble.bp)
        app.register_blueprint(interest_receivable.bp)
        app.register_blueprint(rental_due.bp)
        app.register_blueprint(expenditure.bp)
        app.register_blueprint(breakeven_calculator.bp)
        app.register_blueprint(profit_loss.bp)
        app.register_blueprint(final_report.bp)
    except Exception as e:
        log.debug("Company blueprints not fully registered: %s", e)

    # Stock summary
    try:
        from app.routes.stock_summary import bp as stock_summary_bp
        app.register_blueprint(stock_summary_bp)
    except Exception as e:
        log.debug("Stock summary blueprint not registered: %s", e)

    # User (seller/stockist) login + views
    try:
        from app.routes.user import user_auth_bp, user_view_bp
        app.register_blueprint(user_auth_bp)
        app.register_blueprint(user_view_bp)
    except Exception as e:
        log.debug("User blueprints not fully registered: %s", e)

    # ----------------- Assistant (chat) -----------------
from importlib import import_module

assistant_module = None
last_err = None
for dotted in ("app.assistant", "app.app.assistant"):  # try both layouts
    try:
        assistant_module = import_module(dotted)
        app.logger.info("Assistant module loaded from %s", dotted)
        break
    except Exception as e:
        last_err = e

if assistant_module is None:
    app.logger.exception(
        "Failed to import assistant module from app.assistant OR app.app.assistant"
    )
    raise last_err  # fail fast so /socket.io doesn't silently 404

assistant_bp = getattr(assistant_module, "assistant_bp", None)
assistant_socketio = getattr(assistant_module, "socketio", None)

if assistant_bp is None or assistant_socketio is None:
    raise RuntimeError("assistant module missing 'assistant_bp' or 'socketio'.")

# Register blueprint
app.register_blueprint(assistant_bp)

# Initialize the SAME Socket.IO instance; only pass message_queue if configured
init_kwargs = {"cors_allowed_origins": "*"}
mq_url = app.config.get("REDIS_URL")
if mq_url:
    init_kwargs["message_queue"] = mq_url
assistant_socketio.init_app(app, **init_kwargs)

# (Optional) quick sanity endpoint — remove later
@app.get("/__sio")
def __sio():
    return {
        "socketio_attached": bool(app.extensions.get("socketio")),
        "assistant_path": assistant_module.__name__,
    }, 200


    # ----------------- DB bootstrap (optional; use migrations in prod) -----------------
    # If you still want auto-create for dev (SQLite), set CREATE_TABLES_ON_START=1
    if os.environ.get("CREATE_TABLES_ON_START") == "1":
        with app.app_context():
            from app import models  # ensure models are imported
            db.create_all()

    # ----------------- Login manager loader -----------------
    try:
        from app.models import User

        @login_manager.user_loader
        def load_user(user_id):
            try:
                return User.query.get(int(user_id))
            except Exception:
                return None
    except Exception as e:
        log.debug("Login user loader not set (User model missing?): %s", e)

    # ----------------- Health -----------------
    @app.get("/__health")
    def __health():
        return {"ok": True}, 200

    return app
