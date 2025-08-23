# app/__init__.py
import os
import logging
from pathlib import Path
from datetime import timedelta

from flask import Flask, session
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager
from flask_migrate import Migrate
from sqlalchemy import MetaData

from utils.hindi import to_hindi_name

# ----------------- Logging -----------------
log = logging.getLogger(__name__)

# ----------------- SQLAlchemy naming (portable across engines) -----------------
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

# ----------------- Jinja Filters -----------------
def format_inr(value):
    try:
        value = float(value or 0)
        s = f"{value:.2f}"
        int_part, dec_part = s.split(".")
        if len(int_part) <= 3:
            return f"₹{int_part}.{dec_part}"
        last_three = int_part[-3:]
        rest = int_part[:-3]
        parts = []
        while len(rest) > 2:
            parts.append(rest[-2:])
            rest = rest[:-2]
        if rest:
            parts.append(rest)
        formatted = (",".join(reversed(parts)) + "," if parts else "") + last_three
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
                    return _dt.strptime(value, fmt).strftime("%d-%m-%Y")
                except ValueError:
                    continue
        return value
    except Exception:
        return value


# ----------------- App Factory -----------------
def create_app() -> Flask:
    app = Flask(__name__, instance_relative_config=True)

    # Instance path (allow override via env)
    custom_instance = os.environ.get("FLASK_INSTANCE_PATH")
    if custom_instance:
        app.instance_path = custom_instance
    os.makedirs(app.instance_path, exist_ok=True)

    # Resolve DB URI: prefer SQLALCHEMY_DATABASE_URI, then DATABASE_URL, else SQLite
    uri = os.environ.get("SQLALCHEMY_DATABASE_URI") or os.environ.get("DATABASE_URL")
    if not uri:
        db_path = Path(app.instance_path) / "warehouse.db"
        uri = f"sqlite:///{db_path}"
    if uri.startswith("postgres://"):
        uri = uri.replace("postgres://", "postgresql://", 1)

    # Base config
    app.config.from_mapping(
        SECRET_KEY=os.environ.get("SECRET_KEY", "your-secret-key"),
        SQLALCHEMY_DATABASE_URI=uri,
        SQLALCHEMY_TRACK_MODIFICATIONS=False,
        SQLALCHEMY_ENGINE_OPTIONS={"pool_pre_ping": True, "pool_recycle": 1800},
        SESSION_COOKIE_SAMESITE="Lax",
        REDIS_URL=os.environ.get("REDIS_URL"),  # optional for Socket.IO message queue
    )

    # Auto-logout / session settings (10 minutes inactivity)
    app.config.update(
        SESSION_REFRESH_EACH_REQUEST=True,
        PERMANENT_SESSION_LIFETIME=timedelta(minutes=10),
    )

    # Ensure session lifetime applies
    @app.before_request
    def _session_permanent():
        session.permanent = True

    # Init extensions
    db.init_app(app)
    login_manager.init_app(app)
    login_manager.login_view = "auth.login"
    migrate.init_app(app, db)

    # Jinja filters
    app.jinja_env.filters["format_inr"] = format_inr
    app.jinja_env.filters["kg_to_mt"] = kg_to_mt
    app.jinja_env.filters["format_date"] = format_date
    app.jinja_env.filters["to_hindi"] = to_hindi_name

    # ----------------- Blueprints (register each independently) -----------------

    # Auth / public
    try:
        from .routes import auth
        app.register_blueprint(auth.bp)
    except Exception as e:
        app.logger.exception("Auth blueprint not registered: %s", e)

    # Seller module
    try:
        from app.routes.seller import dashboard as seller_dashboard
        app.register_blueprint(seller_dashboard.bp)
    except Exception as e:
        app.logger.exception("Seller dashboard blueprint failed: %s", e)
    try:
        from app.routes.seller import seller
        app.register_blueprint(seller.bp)
    except Exception as e:
        app.logger.exception("Seller blueprint failed: %s", e)
    try:
        from app.routes.seller import purchase
        app.register_blueprint(purchase.bp)
    except Exception as e:
        app.logger.exception("Purchase blueprint failed: %s", e)
    try:
        from app.routes.seller import payment
        app.register_blueprint(payment.bp)
    except Exception as e:
        app.logger.exception("Seller payment blueprint failed: %s", e)
    try:
        from app.routes.seller import due
        app.register_blueprint(due.bp)
    except Exception as e:
        app.logger.exception("Seller due blueprint failed: %s", e)

    # Stockist module
    try:
        from app.routes.stockist import dashboard as stockist_dashboard
        app.register_blueprint(stockist_dashboard.bp)
    except Exception as e:
        app.logger.exception("Stockist dashboard blueprint failed: %s", e)
    try:
        from app.routes.stockist import stockist
        app.register_blueprint(stockist.bp)
    except Exception as e:
        app.logger.exception("Stockist blueprint failed: %s", e)
    try:
        from app.routes.stockist import stockdata
        app.register_blueprint(stockdata.bp)
    except Exception as e:
        app.logger.exception("Stockdata blueprint failed: %s", e)
    try:
        from app.routes.stockist import stockexit
        app.register_blueprint(stockexit.bp)
    except Exception as e:
        app.logger.exception("Stockexit blueprint failed: %s", e)
    try:
        from app.routes.stockist import loandata
        app.register_blueprint(loandata.bp)
    except Exception as e:
        app.logger.exception("Loandata blueprint failed: %s", e)
    try:
        from app.routes.stockist import margindata
        app.register_blueprint(margindata.bp)
    except Exception as e:
        app.logger.exception("Margindata blueprint failed: %s", e)
    try:
        from app.routes.stockist import rental_calculator
        app.register_blueprint(rental_calculator.bp)
    except Exception as e:
        app.logger.exception("Rental calculator blueprint failed: %s", e)
    # Optional: stockist payments
    try:
        from app.routes.stockist import stockist_payment
        app.register_blueprint(stockist_payment.bp)
    except Exception as e:
        app.logger.debug("Stockist payment blueprint not registered: %s", e)
    # Optional: stockist loan repayment
    try:
        from app.routes.stockist import loan_repayment as stockist_loan_repayment
        app.register_blueprint(stockist_loan_repayment.bp)
    except Exception as e:
        app.logger.debug("Stockist loan repayment blueprint not registered: %s", e)

    # Buyer module
    try:
        from app.routes.buyer import dashboard as buyer_dashboard
        app.register_blueprint(buyer_dashboard.bp)
    except Exception as e:
        app.logger.exception("Buyer dashboard blueprint failed: %s", e)
    try:
        from app.routes.buyer import buyer
        app.register_blueprint(buyer.bp)
    except Exception as e:
        app.logger.exception("Buyer blueprint failed: %s", e)
    try:
        from app.routes.buyer import sales
        app.register_blueprint(sales.bp)
    except Exception as e:
        app.logger.exception("Buyer sales blueprint failed: %s", e)
    try:
        from app.routes.buyer import payments
        app.register_blueprint(payments.bp)
    except Exception as e:
        app.logger.exception("Buyer payments blueprint failed: %s", e)

    # Company module
    try:
        from app.routes.company import dashboard as company_dashboard
        app.register_blueprint(company_dashboard.bp)
    except Exception as e:
        app.logger.exception("company.dashboard failed: %s", e)
    try:
        from app.routes.company import companyloan
        app.register_blueprint(companyloan.bp)
    except Exception as e:
        app.logger.exception("company.companyloan failed: %s", e)
    try:
        from app.routes.company import loanrepayment
        app.register_blueprint(loanrepayment.bp)
    except Exception as e:
        app.logger.exception("company.loanrepayment failed: %s", e)
    try:
        from app.routes.company import interest_payble
        app.register_blueprint(interest_payble.bp)
    except Exception as e:
        app.logger.exception("company.interest_payble failed: %s", e)
    try:
        from app.routes.company import interest_receivable
        app.register_blueprint(interest_receivable.bp)
    except Exception as e:
        app.logger.exception("company.interest_receivable failed: %s", e)
    try:
        from app.routes.company import rental_due
        app.register_blueprint(rental_due.bp)
    except Exception as e:
        app.logger.exception("company.rental_due failed: %s", e)
    try:
        from app.routes.company import expenditure
        app.register_blueprint(expenditure.bp)
    except Exception as e:
        app.logger.exception("company.expenditure failed: %s", e)
    try:
        from app.routes.company import breakeven_calculator
        app.register_blueprint(breakeven_calculator.bp)
    except Exception as e:
        app.logger.exception("company.breakeven_calculator failed: %s", e)
    try:
        from app.routes.company import profit_loss
        app.register_blueprint(profit_loss.bp)
    except Exception as e:
        app.logger.exception("company.profit_loss failed: %s", e)
    try:
        from app.routes.company import final_report
        app.register_blueprint(final_report.bp)
    except Exception as e:
        app.logger.exception("company.final_report failed: %s", e)
    try:
        from app.routes.company import company_loan_due
        app.register_blueprint(company_loan_due.bp)
    except Exception as e:
        app.logger.exception("company.company_loan_due failed: %s", e)
    try:
        from app.routes.company import residual_earning
        app.register_blueprint(residual_earning.bp)
    except Exception as e:
        app.logger.exception("company.residual_earning failed: %s", e)
    # Keep invoice last; if it fails you still have /company/finance working
    try:
        from app.routes.company import invoice
        app.register_blueprint(invoice.bp)
    except Exception as e:
        app.logger.exception("company.invoice failed: %s", e)

    # Stock summary
    try:
        from app.routes.stock_summary import bp as stock_summary_bp
        app.register_blueprint(stock_summary_bp)
    except Exception as e:
        app.logger.exception("Stock summary blueprint not registered: %s", e)

    # User (seller/stockist) login + views
    try:
        from app.routes.user import user_auth_bp, user_view_bp
        app.register_blueprint(user_auth_bp)
        app.register_blueprint(user_view_bp)
    except Exception as e:
        app.logger.exception("User blueprints not fully registered: %s", e)

    # ----------------- Assistant (chat / Socket.IO) -----------------
    try:
        # Import only from the canonical path to avoid double-importing the package
        from app import assistant as assistant_module
        app.logger.info("Assistant module loaded from app.assistant")
    except Exception:
        app.logger.exception("Failed to import assistant module from app.assistant")
        raise

    assistant_bp = getattr(assistant_module, "assistant_bp", None)
    assistant_socketio = getattr(assistant_module, "socketio", None)
    if assistant_bp is None or assistant_socketio is None:
        raise RuntimeError("assistant module missing 'assistant_bp' or 'socketio'.")

    # Register assistant blueprint
    app.register_blueprint(assistant_bp)

    # Initialize Socket.IO (optionally with Redis message queue)
    init_kwargs = {"cors_allowed_origins": "*"}
    mq_url = app.config.get("REDIS_URL")
    if mq_url:
        init_kwargs["message_queue"] = mq_url
    assistant_socketio.init_app(app, **init_kwargs)

    # Optional quick sanity endpoint for Socket.IO wiring
    if os.environ.get("DEBUG_SIO") == "1":
        @app.get("/__sio")
        def __sio():
            return {
                "socketio_attached": bool(app.extensions.get("socketio")),
                "assistant_path": assistant_module.__name__,
            }, 200

    # ----------------- DB bootstrap (DEV only) -----------------
    # In production, prefer migrations. For local dev convenience:
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
        app.logger.debug("Login user loader not set (User model missing?): %s", e)

    # ----------------- Health -----------------
    @app.get("/__health")
    def __health():
        return {"ok": True}, 200

    return app
