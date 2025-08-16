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

    # --------------------------------
    # 4. Rental Due (by warehouse and commodity)
    # --------------------------------
    rental_rate = 3.334
    today = date.today()

    # Collect all (warehouse, commodity) pairs
    pairs = set((entry.warehouse, entry.commodity) for entry in stock_data)
    rental_due = {}
    for wh, commodity in pairs:
        # Net stock: total in - total out
        total_in = sum((e.quantity or 0) for e in StockData.query.filter_by(stockist_name=name, warehouse=wh, commodity=commodity).all())
        total_out = sum((e.quantity or 0) for e in StockExit.query.filter_by(stockist_name=name, warehouse=wh, commodity=commodity).all())
        net_qty_kg = total_in - total_out
        net_qty_mt = net_qty_kg / 1000

        # Rental = net_qty_mt * rental_rate * number of days since earliest entry for this stockist/warehouse/commodity
        first_entry = StockData.query.filter_by(stockist_name=name, warehouse=wh, commodity=commodity).order_by(StockData.date).first()
        if first_entry:
            num_days = (today - first_entry.date).days + 1
        else:
            num_days = 0

        total_rental = net_qty_mt * rental_rate * num_days if net_qty_mt > 0 else 0
        if wh not in rental_due:
            rental_due[wh] = {}
        rental_due[wh][commodity] = round(total_rental, 2)

    # --------------------------------
    # 5. Interest Due (by warehouse)
    # --------------------------------
    interest_rate = 13.75
    warehouses = set(entry.warehouse for entry in loan_data)
    interest_due = {}
    for wh in warehouses:
        total_loan = sum((e.amount or 0) for e in LoanData.query.filter_by(stockist_name=name, warehouse=wh).all())
        total_margin = sum((e.amount or 0) for e in MarginData.query.filter_by(stockist_name=name, warehouse=wh).all())
        first_loan = LoanData.query.filter_by(stockist_name=name, warehouse=wh).order_by(LoanData.date).first()
        if first_loan:
            num_days = (today - first_loan.date).days + 1
        else:
            num_days = 0

        principal = total_loan - total_margin
        interest_amt = principal * (interest_rate / 100) * (num_days / 365) if principal > 0 and num_days > 0 else 0
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
