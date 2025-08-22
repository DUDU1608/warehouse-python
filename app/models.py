from app import db, login_manager
from flask_login import UserMixin

from werkzeug.security import generate_password_hash, check_password_hash

class User(db.Model, UserMixin):
    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    name = db.Column(db.String(100))
    mobile = db.Column(db.String(15), unique=True)
    password_hash = db.Column(db.String(128))  # ✅ add this

    def set_password(self, password):
        self.password_hash = generate_password_hash(password, method='pbkdf2:sha256')

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))
class Seller(db.Model):
    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    name = db.Column(db.String(100))
    mobile = db.Column(db.String(15), unique=True)
    address = db.Column(db.String(200))
    banking_name = db.Column(db.String(100))
    account_number = db.Column(db.String(30))
    ifsc_code = db.Column(db.String(20))
    bank_name = db.Column(db.String(100))

from app import db


from datetime import date, datetime


class Payment(db.Model):
    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    date = db.Column(db.Date, nullable=False, default=date.today)   # <-- Add this line!
    seller_name = db.Column(db.String(100), nullable=False)
    warehouse = db.Column(db.String(100), nullable=False)
    commodity = db.Column(db.String(50), nullable=False)
    banking_name = db.Column(db.String(100), nullable=False)
    account_number = db.Column(db.String(30), nullable=False)
    ifsc = db.Column(db.String(20), nullable=False)
    amount_paid = db.Column(db.Float, nullable=False)
    bank_reference = db.Column(db.String(100), nullable=False)

class Purchase(db.Model):
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
        db.UniqueConstraint('rst_no', 'warehouse', name='uix_rstno_warehouse'),
    )

class Stockist(db.Model):
    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    name = db.Column(db.String(100))
    mobile = db.Column(db.String(15), unique=True)
    address = db.Column(db.String(200))
    banking_name = db.Column(db.String(100))
    account_number = db.Column(db.String(30))
    ifsc_code = db.Column(db.String(20))
    bank_name = db.Column(db.String(100))

class StockData(db.Model):
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
    kind_of_stock = db.Column(db.String(20), default='self')   # Always set by backend

from app import db

class StockExit(db.Model):
    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    date = db.Column(db.Date, nullable=False)
    warehouse = db.Column(db.String(100), nullable=False)
    stockist_name = db.Column(db.String(100), nullable=False)
    mobile = db.Column(db.String(20), nullable=True)
    commodity = db.Column(db.String(30), nullable=False)
    quantity = db.Column(db.Float, nullable=False)
    reduction = db.Column(db.Float, nullable=False)
    net_qty = db.Column(db.Float, nullable=False)
    rate = db.Column(db.Float, nullable=False)
    cost = db.Column(db.Float, nullable=False)
    handling = db.Column(db.Float, nullable=False)
    net_cost = db.Column(db.Float, nullable=False)
    quality = db.Column(db.String(30), nullable=True)

# models.py
class LoanData(db.Model):
    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    date = db.Column(db.Date, nullable=False)
    stockist_name = db.Column(db.String(100), nullable=False)
    warehouse = db.Column(db.String(100))
    commodity = db.Column(db.String(30))
    loan_type = db.Column(db.String(30))  # e.g. "Cash", "Margin"
    amount = db.Column(db.Float, nullable=False)

class MarginData(db.Model):
    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    date = db.Column(db.Date, nullable=False)
    stockist_name = db.Column(db.String(100), nullable=False)
    warehouse = db.Column(db.String(100), nullable=False)
    commodity = db.Column(db.String(20), nullable=False)
    amount = db.Column(db.Float, nullable=False)

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
    quality = db.Column(db.String(20))  # Good / BD
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


class BuyerPayment(db.Model):
    __tablename__ = "buyer_payment"
    id = db.Column(db.Integer, primary_key=True)
    buyer_id = db.Column(db.Integer, db.ForeignKey("buyer.id"), nullable=False)
    buyer_name = db.Column(db.String(150))
    mobile_no = db.Column(db.String(20))
    commodity = db.Column(db.String(50))
    warehouse = db.Column(db.String(150))
    amount = db.Column(db.Float, nullable=False)
    reference = db.Column(db.String(100))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

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
    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    date = db.Column(db.Date, nullable=False)
    loan_amount = db.Column(db.Float, nullable=False)
    processing_fee = db.Column(db.Float, nullable=False)
    gst = db.Column(db.Float, nullable=False)
    total_processing_fee = db.Column(db.Float, nullable=False)
    total_disbursement = db.Column(db.Float, nullable=False)
    interest_rate = db.Column(db.Float, nullable=False)

class LoanRepayment(db.Model):
    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    date = db.Column(db.Date, nullable=False)
    amount = db.Column(db.Float, nullable=False)
    interest_rate = db.Column(db.Float, nullable=False)
    
class Expenditure(db.Model):
    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    date = db.Column(db.Date, nullable=False)
    expenditure_type = db.Column(db.String(50), nullable=False)  # e.g., Maintenance Charges, Salary Payment, Others
    amount = db.Column(db.Float, nullable=False)
    comments = db.Column(db.String(255))  # Only required if type is 'Others'

class ChatSession(db.Model):
    __tablename__ = "chat_session"
    id = db.Column(db.Integer, primary_key=True, autoincrement=True)

    # NOTE: allow NULL for public (guest) chats
    user_mobile = db.Column(db.String(20), index=True, nullable=True)

    # NEW: for homepage guests
    visitor_id = db.Column(db.String(64), index=True, nullable=True)

    # NEW: distinguish scopes
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

