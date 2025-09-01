# app/models.py
from datetime import date, datetime
from sqlalchemy.orm import column_property
from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash

from app import db, login_manager


# ---------------------------
# Auth / Users
# ---------------------------
class User(db.Model, UserMixin):
    __tablename__ = "user"                          # keep existing table name
    __table_args__ = {"extend_existing": True}      # guard against duplicate imports

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    name = db.Column(db.String(100))
    mobile = db.Column(db.String(15), unique=True, index=True)
    password_hash = db.Column(db.String(128), nullable=True)

    def set_password(self, password: str):
        self.password_hash = generate_password_hash(password, method="pbkdf2:sha256")

    def check_password(self, password: str) -> bool:
        return check_password_hash(self.password_hash or "", password)


@login_manager.user_loader
def load_user(user_id):
    try:
        return User.query.get(int(user_id))
    except Exception:
        return None


# ---------------------------
# Seller / Purchases / Payments
# ---------------------------
class Seller(db.Model):
    __tablename__ = "seller"

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    name = db.Column(db.String(100))
    mobile = db.Column(db.String(15), unique=True)
    address = db.Column(db.String(200))
    banking_name = db.Column(db.String(100))
    account_number = db.Column(db.String(30))
    ifsc_code = db.Column(db.String(20))
    bank_name = db.Column(db.String(100))


class Payment(db.Model):
    __tablename__ = "payment"

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    date = db.Column(db.Date, nullable=False, default=date.today)
    seller_name = db.Column(db.String(100), nullable=False)
    warehouse = db.Column(db.String(100), nullable=False)
    commodity = db.Column(db.String(50), nullable=False)
    banking_name = db.Column(db.String(100), nullable=False)
    account_number = db.Column(db.String(30), nullable=False)
    ifsc = db.Column(db.String(20), nullable=False)
    amount_paid = db.Column(db.Float, nullable=False)
    bank_reference = db.Column(db.String(100), nullable=False)


class Purchase(db.Model):
    __tablename__ = "purchase"

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    date = db.Column(db.String(20))
    rst_no = db.Column(db.String(50))
    warehouse = db.Column(db.String(100))
    seller_name = db.Column(db.String(100))
    mobile = db.Column(db.String(20))
    commodity = db.Column(db.String(50))
    quantity = db.Column(db.Float)
    reduction = db.Column(db.Float)
    net_qty = db.Column(db.Float)
    rate = db.Column(db.Float)
    cost = db.Column(db.Float)
    handling = db.Column(db.Float)
    net_cost = db.Column(db.Float)
    quality = db.Column(db.String(20))

    __table_args__ = (
        db.UniqueConstraint("rst_no", "warehouse", name="uix_rstno_warehouse"),
    )


# ---------------------------
# Stockist / Stock
# ---------------------------
class Stockist(db.Model):
    __tablename__ = "stockist"

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    name = db.Column(db.String(100))
    mobile = db.Column(db.String(15), unique=True)
    address = db.Column(db.String(200))
    banking_name = db.Column(db.String(100))
    account_number = db.Column(db.String(30))
    ifsc_code = db.Column(db.String(20))
    bank_name = db.Column(db.String(100))


class StockData(db.Model):
    __tablename__ = "stock_data"

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    date = db.Column(db.Date, nullable=False)
    rst_no = db.Column(db.String(50), nullable=False)
    warehouse = db.Column(db.String(120), nullable=False)
    stockist_name = db.Column(db.String(120), nullable=False)
    mobile = db.Column(db.String(20))
    commodity = db.Column(db.String(50))
    quantity = db.Column(db.Float)
    reduction = db.Column(db.Float)
    net_qty = db.Column(db.Float)
    rate = db.Column(db.Float)
    cost = db.Column(db.Float)
    handling = db.Column(db.Float)
    net_cost = db.Column(db.Float)
    quality = db.Column(db.String(40))
    kind_of_stock = db.Column(db.String(20), default="self")   # set by backend


class StockExit(db.Model):
    __tablename__ = "stock_exit"

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    date = db.Column(db.Date, nullable=False)
    warehouse = db.Column(db.String(100), nullable=False)
    stockist_name = db.Column(db.String(100), nullable=False)
    mobile = db.Column(db.String(20))
    commodity = db.Column(db.String(30), nullable=False)
    quantity = db.Column(db.Float, nullable=False)
    reduction = db.Column(db.Float, nullable=False)
    net_qty = db.Column(db.Float, nullable=False)
    rate = db.Column(db.Float, nullable=False)
    cost = db.Column(db.Float, nullable=False)
    handling = db.Column(db.Float, nullable=False)
    net_cost = db.Column(db.Float, nullable=False)
    quality = db.Column(db.String(30))


# ---------------------------
# Financing (stockist-level)
# ---------------------------
class LoanData(db.Model):
    __tablename__ = "loan_data"

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    date = db.Column(db.Date, nullable=False)
    stockist_name = db.Column(db.String(100), nullable=False)
    warehouse = db.Column(db.String(100))
    commodity = db.Column(db.String(30))
    loan_type = db.Column(db.String(30))  # "Cash", "Margin"
    amount = db.Column(db.Float, nullable=False)


class MarginData(db.Model):
    __tablename__ = "margin_data"

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    date = db.Column(db.Date, nullable=False)
    stockist_name = db.Column(db.String(100), nullable=False)
    warehouse = db.Column(db.String(100), nullable=False)
    commodity = db.Column(db.String(20), nullable=False)
    amount = db.Column(db.Float, nullable=False)


class StockistPayment(db.Model):
    __tablename__ = "stockist_payment"

    id = db.Column(db.Integer, primary_key=True)
    date = db.Column(db.Date, nullable=False, index=True, default=date.today)
    stockist_id = db.Column(db.Integer, db.ForeignKey("stockist.id"), index=True)
    stockist_name = db.Column(db.String(100), nullable=False)
    mobile = db.Column(db.String(20))
    warehouse = db.Column(db.String(150))
    commodity = db.Column(db.String(50))
    amount = db.Column(db.Float, nullable=False)
    bank_reference = db.Column(db.String(100))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


class StockistLoanRepayment(db.Model):
    __tablename__ = "stockist_loan_repayment"

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    date = db.Column(db.Date, nullable=False, default=date.today)
    stockist_name = db.Column(db.String(100), nullable=False, index=True)
    mobile = db.Column(db.String(20), index=True)
    warehouse = db.Column(db.String(100))
    commodity = db.Column(db.String(30))
    amount = db.Column(db.Float, nullable=False)
    bank_reference = db.Column(db.String(120))
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)


# ---------------------------
# Buyer / Sales
# ---------------------------
class Buyer(db.Model):
    __tablename__ = "buyer"

    id = db.Column(db.Integer, primary_key=True)
    buyer_name = db.Column(db.String(150), nullable=False, index=True)
    mobile_no = db.Column(db.String(20), nullable=False, unique=True, index=True)
    address = db.Column(db.String(255))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    sales = db.relationship("BuyerSale", backref="buyer", lazy=True, cascade="all, delete-orphan")
    payments = db.relationship("BuyerPayment", backref="buyer", lazy=True, cascade="all, delete-orphan")


class BuyerSale(db.Model):
    __tablename__ = "buyer_sale"

    id = db.Column(db.Integer, primary_key=True)
    date = db.Column(db.Date, nullable=False, index=True)
    rst_no = db.Column(db.String(50), nullable=False)
    warehouse = db.Column(db.String(150))
    buyer_id = db.Column(db.Integer, db.ForeignKey("buyer.id"), nullable=False)
    buyer_name = db.Column(db.String(150))
    mobile = db.Column(db.String(20))
    commodity = db.Column(db.String(50), nullable=False)
    quantity = db.Column(db.Float, nullable=False)
    rate = db.Column(db.Float, nullable=False)
    cost = db.Column(db.Float, nullable=False)
    handling_charge = db.Column(db.Float, default=0.0)
    net_cost = db.Column(db.Float, nullable=False)  # cost + handling
    quality = db.Column(db.String(20))              # Good / BD
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


class BuyerPayment(db.Model):
    __tablename__ = "buyer_payment"

    id = db.Column(db.Integer, primary_key=True)
    date = db.Column(db.Date, nullable=False, index=True, default=date.today)
    buyer_id = db.Column(db.Integer, db.ForeignKey("buyer.id"), nullable=False)
    buyer_name = db.Column(db.String(150))
    mobile_no = db.Column(db.String(20))
    commodity = db.Column(db.String(50))
    warehouse = db.Column(db.String(150))
    amount = db.Column(db.Float, nullable=False)
    reference = db.Column(db.String(100))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


# ---------------------------
# Invoicing (aligned with invoice.py)
# ---------------------------
class Invoice(db.Model):
    __tablename__ = "invoice"

    id = db.Column(db.Integer, primary_key=True)
    invoice_no = db.Column(db.Integer, nullable=False, unique=True, index=True)
    date = db.Column(db.Date, nullable=False)

    # IMPORTANT: matches invoice.py (uses buyer_id, not customer_id)
    buyer_id = db.Column(db.Integer, db.ForeignKey("buyer.id"), nullable=False)

    customer_name = db.Column(db.String(150), nullable=False)
    address = db.Column(db.String(255))
    vehicle_no = db.Column(db.String(50))
    driver_no = db.Column(db.String(50))

    sub_total = db.Column(db.Float, default=0.0)    # matches invoice.py key "sub_total"
    cgst = db.Column(db.Float, default=0.0)         # always 0 per spec
    sgst = db.Column(db.Float, default=0.0)         # always 0 per spec
    grand_total = db.Column(db.Float, default=0.0)

    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    items = db.relationship("InvoiceItem", backref="invoice", cascade="all, delete-orphan")


class InvoiceItem(db.Model):
    __tablename__ = "invoice_item"

    id = db.Column(db.Integer, primary_key=True)
    invoice_id = db.Column(db.Integer, db.ForeignKey("invoice.id"), index=True, nullable=False)
    description = db.Column(db.String(255), nullable=False)
    price = db.Column(db.Float, nullable=False, default=0.0)
    qty = db.Column(db.Float, nullable=False, default=0.0)
    amount = db.Column(db.Float, nullable=False, default=0.0)


# ---------------------------
# Residual / Company financing
# ---------------------------
class ResidualEarning(db.Model):
    __tablename__ = "residual_earning"

    id = db.Column(db.Integer, primary_key=True)
    date = db.Column(db.Date, nullable=False, index=True)
    warehouse = db.Column(db.String(150), nullable=False)
    commodity = db.Column(db.String(50), nullable=False)
    quantity = db.Column(db.Float, nullable=False)
    rate = db.Column(db.Float, nullable=False)
    total_earning = db.Column(db.Float, nullable=False)  # usually = quantity * rate
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


class CompanyLoan(db.Model):
    __tablename__ = "company_loan"

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    date = db.Column(db.Date, nullable=False)
    loan_amount = db.Column(db.Float, nullable=False)
    processing_fee = db.Column(db.Float, nullable=False)
    gst = db.Column(db.Float, nullable=False)
    total_processing_fee = db.Column(db.Float, nullable=False)
    total_disbursement = db.Column(db.Float, nullable=False)
    interest_rate = db.Column(db.Float, nullable=False)


class LoanRepayment(db.Model):
    __tablename__ = "loan_repayment"

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    date = db.Column(db.Date, nullable=False)
    amount = db.Column(db.Float, nullable=False)
    interest_rate = db.Column(db.Float, nullable=False)


class Expenditure(db.Model):
    __tablename__ = "expenditure"

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    date = db.Column(db.Date, nullable=False)
    expenditure_type = db.Column(db.String(50), nullable=False)  # Maintenance, Salary, Others
    amount = db.Column(db.Float, nullable=False)
    comments = db.Column(db.String(255))  # required if type is 'Others'


# ---------------------------
# Assistant chat models
# ---------------------------
class ChatSession(db.Model):
    __tablename__ = "chat_session"

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    user_mobile = db.Column(db.String(20), index=True, nullable=True)  # allow NULL for guests
    visitor_id = db.Column(db.String(64), index=True, nullable=True)
    scope = db.Column(db.String(20), default="public", nullable=True)  # "public" or "account"

    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    last_activity = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    status = db.Column(db.String(20), default="open")   # open, closed
    escalated = db.Column(db.Boolean, default=False)
    assigned_agent = db.Column(db.String(50), nullable=True)


class ChatMessage(db.Model):
    __tablename__ = "chat_message"

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    session_id = db.Column(db.Integer, db.ForeignKey("chat_session.id"), index=True, nullable=False)
    sender_type = db.Column(db.String(10), nullable=False)  # user, bot, agent, system
    sender_id = db.Column(db.String(50), nullable=True)
    message = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    is_private = db.Column(db.Boolean, default=False)

    session = db.relationship("ChatSession", backref=db.backref("messages", lazy="dynamic"))

class CompanyStock(db.Model):
    __tablename__ = "company_stock"

    id = db.Column(db.Integer, primary_key=True)
    warehouse = db.Column(db.String(120), nullable=False)
    commodity = db.Column(db.String(50), nullable=False)     # e.g., Wheat / Maize / Paddy
    quantity = db.Column(db.Numeric(14, 3), nullable=False)  # store in kg or unit you prefer
    quality = db.Column(db.String(20), nullable=False)       # e.g., Good / BD
    average_price = db.Column(db.Numeric(14, 2), nullable=False)  # per unit price

    # Computed at DB level: total_price = quantity * average_price
    total_price = column_property(quantity * average_price)

    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    def __repr__(self):
        return f"<CompanyStock {self.id} {self.warehouse} {self.commodity}>"

