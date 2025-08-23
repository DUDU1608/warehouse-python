from flask import Blueprint, render_template, session, redirect, url_for
from flask_login import login_required
from app import db
from app.models import Seller, Stockist, Purchase, Payment, LoanData, MarginData, StockData, StockExit
from datetime import date

def login_required(func):
    from functools import wraps
    from flask import session, redirect, url_for
    @wraps(func)
    def wrapper(*args, **kwargs):
        if 'mobile' not in session:
            return redirect(url_for('user_auth.login'))
        return func(*args, **kwargs)
    return wrapper

user_view_bp = Blueprint('user_views', __name__, url_prefix='/user')

@user_view_bp.route('/')
def index():
    return render_template('user/index.html')

@user_view_bp.route('/home')
def home():
    if 'mobile' not in session:
        return redirect(url_for('user_auth.login'))

    mobile = session['mobile']
    seller = Seller.query.filter_by(mobile=mobile).first()
    stockist = Stockist.query.filter_by(mobile=mobile).first()

    is_seller = seller is not None
    is_stockist = stockist is not None

    # Prefer seller name, fallback to stockist
    if is_seller and seller.name:
        display_name = seller.name
    elif is_stockist and stockist.name:
        display_name = stockist.name
    else:
        display_name = "User"

    return render_template('user/home.html',
                           is_seller=is_seller,
                           is_stockist=is_stockist,
                           display_name=display_name)

@user_view_bp.route('/seller')
@login_required
def seller_module():
    mobile = session.get('mobile')
    seller = Seller.query.filter_by(mobile=mobile).first()
    if not seller:
        return redirect(url_for('user_auth.login'))

    # Get seller name to match purchase/payment tables
    name = seller.name

    # Purchases
    purchases = Purchase.query.filter_by(seller_name=name).all()
    purchase_summary = {
        'quantity': sum(p.quantity or 0 for p in purchases),
        'reduction': sum(p.reduction or 0 for p in purchases),
        'net_qty': sum(p.net_qty or 0 for p in purchases),
        'cost': sum(p.cost or 0 for p in purchases),
        'handling': sum(p.handling or 0 for p in purchases),
        'net_cost': sum(p.net_cost or 0 for p in purchases)
    }

    # Payments
    payments = Payment.query.filter_by(seller_name=name).all()
    payment_summary = {
        'amount': sum(p.amount_paid or 0 for p in payments)
    }

    # Payment Due
    net_cost = purchase_summary.get('net_cost') or 0
    amount_paid = payment_summary.get('amount') or 0
    payment_due = net_cost - amount_paid

    return render_template(
        'user/seller_module.html',
        purchases=purchases,
        payments=payments,
        purchase_summary=purchase_summary,
        payment_summary=payment_summary,
        net_cost=net_cost,
        amount_paid=amount_paid,
        payment_due=payment_due,
        today=date.today().strftime("%d/%m/%Y")
    )

@user_view_bp.route('/stockist')
@login_required
def stockist_module():
    mobile = session.get('mobile')
    stockist = Stockist.query.filter_by(mobile=mobile).first()
    if not stockist:
        return redirect(url_for('user_auth.login'))

    name = stockist.name

    # --------------------------------
    # 1. My Materials Stored
    # --------------------------------
    stock_data = StockData.query.filter_by(stockist_name=name).all()

    # Summary by warehouse and commodity (in MT)
    material_summary = {}
    for entry in stock_data:
        wh = entry.warehouse
        com = entry.commodity
        qty = (entry.quantity or 0) / 1000  # Convert kg to MT

        if wh not in material_summary:
            material_summary[wh] = {}
        material_summary[wh][com] = material_summary[wh].get(com, 0) + qty

    # --------------------------------
    # 2. Loans Received
    # --------------------------------
    loan_data = LoanData.query.filter_by(stockist_name=name).all()

    # Initialize summary structure
    loan_summary = {}
    for entry in loan_data:
        wh = entry.warehouse
        loan_type = entry.loan_type
        amt = entry.amount or 0

        if wh not in loan_summary:
            loan_summary[wh] = {'cash': 0, 'margin': 0}

        if loan_type and loan_type.lower() == 'cash':
            loan_summary[wh]['cash'] += amt
        elif loan_type and loan_type.lower() == 'margin':
            loan_summary[wh]['margin'] += amt

    # --------------------------------
    # 3. Margins Paid
    # --------------------------------
    margin_data = MarginData.query.filter_by(stockist_name=name).all()

    margin_summary = {}
    for entry in margin_data:
        wh = entry.warehouse
        amt = entry.amount or 0

        if wh not in margin_summary:
            margin_summary[wh] = 0
        margin_summary[wh] += amt

    from datetime import date, timedelta

# ---------- helpers (piecewise daily accrual) ----------
def _qty_kg(rec):
    """Prefer net_qty if present, else quantity; return KG as float."""
    v = getattr(rec, "net_qty", None)
    if v is None:
        v = getattr(rec, "quantity", 0.0) or 0.0
    return float(v)

def _accrue_piecewise(changes_by_date, as_of, per_unit_per_day):
    """
    changes_by_date: {date -> delta_amount}  (amount can be MT for rental, or ₹ for interest)
    per_unit_per_day: multiplier per 'amount' per day (e.g. rental_rate, or daily interest rate)
    Accrues from each change date up to the next change (exclusive), and up to as_of (inclusive via +1).
    """
    if not changes_by_date:
        return 0.0
    # consider only events up to and including as_of
    changes = {d: float(v) for d, v in changes_by_date.items() if d and d <= as_of}
    if not changes:
        return 0.0

    keys = sorted(changes.keys())
    end_boundary = as_of + timedelta(days=1)
    keys.append(end_boundary)

    running = 0.0
    total = 0.0
    for i in range(len(keys) - 1):
        d = keys[i]
        # apply change at start of day 'd'
        running = max(0.0, running + changes.get(d, 0.0))  # never accrue negative
        nxt = keys[i + 1]
        if nxt <= d:
            continue
        days = (nxt - d).days
        if running > 0 and days > 0:
            total += running * per_unit_per_day * days
    return total

# =======================================================
# 4) RENTAL DUE — daily, cumulative till today, per (warehouse, commodity)
# =======================================================
rental_rate = 3.334  # per MT per day
as_of = date.today()

# Build the set of (warehouse, commodity) pairs that actually had movement
pairs = set(
    db.session.query(StockData.warehouse, StockData.commodity)
      .filter_by(stockist_name=name).distinct().all()
)
pairs |= set(
    db.session.query(StockExit.warehouse, StockExit.commodity)
      .filter_by(stockist_name=name).distinct().all()
)

rental_due = {}
for wh, commodity in pairs:
    # Collect dated quantity deltas (in MT) for this (wh, commodity)
    changes = {}

    # Stock IN (positive)
    for e in StockData.query.filter_by(stockist_name=name, warehouse=wh, commodity=commodity).all():
        changes[e.date] = changes.get(e.date, 0.0) + (_qty_kg(e) / 1000.0)

    # Stock OUT (negative)
    for e in StockExit.query.filter_by(stockist_name=name, warehouse=wh, commodity=commodity).all():
        changes[e.date] = changes.get(e.date, 0.0) - (_qty_kg(e) / 1000.0)

    total_rental = _accrue_piecewise(changes, as_of, rental_rate)
    rental_due.setdefault(wh, {})[commodity] = round(total_rental, 2)

# =======================================================
# 5) INTEREST DUE — daily, cumulative till today, per warehouse
# =======================================================
interest_rate = 13.75  # % p.a.
daily_rate = interest_rate / 100.0 / 365.0
as_of = date.today()

# Warehouses where any loan/margin occurred
warehouses = set(
    db.session.query(LoanData.warehouse).filter_by(stockist_name=name).distinct().all()
)
warehouses |= set(
    db.session.query(MarginData.warehouse).filter_by(stockist_name=name).distinct().all()
)
# flatten tuples and drop Nones
warehouses = {w[0] for w in warehouses if w and w[0]}

interest_due = {}
for wh in warehouses:
    # Build dated principal changes: +loan, -margin
    changes = {}

    for e in LoanData.query.filter_by(stockist_name=name, warehouse=wh).all():
        amt = float(e.amount or 0.0)
        if amt:
            changes[e.date] = changes.get(e.date, 0.0) + amt

    for e in MarginData.query.filter_by(stockist_name=name, warehouse=wh).all():
        amt = float(e.amount or 0.0)
        if amt:
            changes[e.date] = changes.get(e.date, 0.0) - amt

    interest_amt = _accrue_piecewise(changes, as_of, daily_rate)
    interest_due[wh] = round(interest_amt, 2)


    return render_template(
        'user/stockist_module.html',
        stock_data=stock_data,
        material_summary=material_summary,
        loan_data=loan_data,
        loan_summary=loan_summary,
        margin_data=margin_data,
        margin_summary=margin_summary,
        rental_due=rental_due,
        rental_rate=rental_rate,
        interest_due=interest_due,
        interest_rate=interest_rate,
        today=today.strftime("%d/%m/%Y")
    )
