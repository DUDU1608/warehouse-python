# app/routes/user/views.py
from __future__ import annotations

from datetime import date, timedelta
from functools import wraps

from flask import Blueprint, render_template, session, redirect, url_for
from app import db
from app.models import (
    Seller, Stockist, Purchase, Payment,
    LoanData, MarginData, StockData, StockExit
)

# ------------------------------------------------------------------------------
# Auth helper (do NOT shadow flask_login.login_required)
# ------------------------------------------------------------------------------
def user_login_required(func):
    @wraps(func)
    def wrapper(*args, **kwargs):
        if "mobile" not in session:
            return redirect(url_for("user_auth.login"))
        return func(*args, **kwargs)
    return wrapper


user_view_bp = Blueprint("user_views", __name__, url_prefix="/user")


@user_view_bp.route("/")
def index():
    return render_template("user/index.html")


@user_view_bp.route("/home")
def home():
    if "mobile" not in session:
        return redirect(url_for("user_auth.login"))

    mobile = session["mobile"]
    seller = Seller.query.filter_by(mobile=mobile).first()
    stockist = Stockist.query.filter_by(mobile=mobile).first()

    is_seller = seller is not None
    is_stockist = stockist is not None

    # Prefer seller name, fallback to stockist, else "User"
    if is_seller and seller.name:
        display_name = seller.name
    elif is_stockist and stockist.name:
        display_name = stockist.name
    else:
        display_name = "User"

    return render_template(
        "user/home.html",
        is_seller=is_seller,
        is_stockist=is_stockist,
        display_name=display_name,
    )


# ==============================================================================
# Seller module
# ==============================================================================
@user_view_bp.route("/seller")
@user_login_required
def seller_module():
    mobile = session.get("mobile")
    seller = Seller.query.filter_by(mobile=mobile).first()
    if not seller:
        return redirect(url_for("user_auth.login"))

    name = seller.name  # used to join with purchase/payment

    # Purchases
    purchases = Purchase.query.filter_by(seller_name=name).all()
    purchase_summary = {
        "quantity": sum(p.quantity or 0 for p in purchases),
        "reduction": sum(p.reduction or 0 for p in purchases),
        "net_qty": sum(p.net_qty or 0 for p in purchases),
        "cost": sum(p.cost or 0 for p in purchases),
        "handling": sum(p.handling or 0 for p in purchases),
        "net_cost": sum(p.net_cost or 0 for p in purchases),
    }

    # Payments
    payments = Payment.query.filter_by(seller_name=name).all()
    payment_summary = {"amount": sum(p.amount_paid or 0 for p in payments)}

    # Payment Due
    net_cost = purchase_summary.get("net_cost") or 0.0
    amount_paid = payment_summary.get("amount") or 0.0
    payment_due = net_cost - amount_paid

    today_dt = date.today()

    return render_template(
        "user/seller_module.html",
        purchases=purchases,
        payments=payments,
        purchase_summary=purchase_summary,
        payment_summary=payment_summary,
        net_cost=net_cost,
        amount_paid=amount_paid,
        payment_due=payment_due,
        today=today_dt.strftime("%d/%m/%Y"),
    )


# ==============================================================================
# Stockist module (piecewise daily accrual for rental & interest)
# ==============================================================================
@user_view_bp.route("/stockist")
@user_login_required
def stockist_module():
    mobile = session.get("mobile")
    stockist = Stockist.query.filter_by(mobile=mobile).first()
    if not stockist:
        return redirect(url_for("user_auth.login"))

    name = stockist.name
    today_dt = date.today()

    # -----------------------------
    # Helpers (scoped to this view)
    # -----------------------------
    def _qty_kg(rec) -> float:
        """
        Prefer 'net_qty' if present, else 'quantity'; return KG as float.
        """
        v = getattr(rec, "net_qty", None)
        if v is None:
            v = getattr(rec, "quantity", 0.0) or 0.0
        return float(v)

    def _accrue_piecewise(changes_by_date: dict, as_of: date, per_unit_per_day: float) -> float:
        """
        Accrue per-day amount for a running level that changes on specific dates.

        changes_by_date: {date -> delta_level}
            - level = MT for rental
            - level = principal ₹ for interest
        per_unit_per_day: rate per level per day
            - rental: ₹ per MT per day
            - interest: daily_rate (e.g., 13.75%/365)
        Accrues from each change date up to the next change (exclusive), and up to (as_of + 1 day).
        """
        if not changes_by_date:
            return 0.0

        # Keep only changes up to as_of (inclusive)
        filtered = {d: float(v) for d, v in changes_by_date.items() if d and d <= as_of}
        if not filtered:
            return 0.0

        # Sort dates and add end boundary (as_of + 1)
        keys = sorted(filtered.keys())
        end_boundary = as_of + timedelta(days=1)
        keys.append(end_boundary)

        running = 0.0
        total = 0.0
        for i in range(len(keys) - 1):
            d = keys[i]
            # Apply change at the start of day 'd'
            running = max(0.0, running + filtered.get(d, 0.0))  # never accrue negative
            nxt = keys[i + 1]
            if nxt <= d:
                continue
            days = (nxt - d).days
            if running > 0 and days > 0:
                total += running * per_unit_per_day * days
        return total

    # --------------------------------
    # 1) My Materials Stored (summary)
    # --------------------------------
    stock_data = StockData.query.filter_by(stockist_name=name).all()

    material_summary = {}
    for entry in stock_data:
        wh = entry.warehouse
        com = entry.commodity
        qty_mt = _qty_kg(entry) / 1000.0
        material_summary.setdefault(wh, {})
        material_summary[wh][com] = material_summary[wh].get(com, 0.0) + qty_mt

    # --------------------------------
    # 2) Loans Received (summary)
    # --------------------------------
    loan_data = LoanData.query.filter_by(stockist_name=name).all()

    loan_summary = {}
    for entry in loan_data:
        wh = entry.warehouse
        loan_type = (entry.loan_type or "").lower()
        amt = float(entry.amount or 0.0)
        loan_summary.setdefault(wh, {"cash": 0.0, "margin": 0.0})
        if loan_type == "cash":
            loan_summary[wh]["cash"] += amt
        elif loan_type == "margin":
            loan_summary[wh]["margin"] += amt

    # --------------------------------
    # 3) Margins Paid (summary)
    # --------------------------------
    margin_data = MarginData.query.filter_by(stockist_name=name).all()

    margin_summary = {}
    for entry in margin_data:
        wh = entry.warehouse
        amt = float(entry.amount or 0.0)
        margin_summary[wh] = margin_summary.get(wh, 0.0) + amt

    # =======================================================
    # 4) RENTAL DUE — daily, cumulative till today
    # =======================================================
    rental_rate = 3.334  # ₹ per MT per day

    # Build movement pairs (warehouse, commodity) with activity
    rows_in = db.session.query(StockData.warehouse, StockData.commodity)\
                        .filter_by(stockist_name=name).distinct().all()
    rows_out = db.session.query(StockExit.warehouse, StockExit.commodity)\
                         .filter_by(stockist_name=name).distinct().all()

    pairs = {(r[0], r[1]) for r in rows_in if r and r[0] and r[1]}
    pairs |= {(r[0], r[1]) for r in rows_out if r and r[0] and r[1]}

    rental_due = {}
    for wh, commodity in pairs:
        # Dated quantity deltas (in MT)
        changes = {}

        # Stock IN (positive)
        for e in StockData.query.filter_by(stockist_name=name, warehouse=wh, commodity=commodity).all():
            changes[e.date] = changes.get(e.date, 0.0) + (_qty_kg(e) / 1000.0)

        # Stock OUT (negative)
        for e in StockExit.query.filter_by(stockist_name=name, warehouse=wh, commodity=commodity).all():
            changes[e.date] = changes.get(e.date, 0.0) - (_qty_kg(e) / 1000.0)

        total_rental = _accrue_piecewise(changes, today_dt, rental_rate)
        rental_due.setdefault(wh, {})[commodity] = round(total_rental, 2)

    # =======================================================
    # 5) INTEREST DUE — daily, cumulative till today
    # =======================================================
    interest_rate = 13.75  # % p.a.
    daily_rate = interest_rate / 100.0 / 365.0

    w_loan = db.session.query(LoanData.warehouse).filter_by(stockist_name=name).distinct().all()
    w_marg = db.session.query(MarginData.warehouse).filter_by(stockist_name=name).distinct().all()
    warehouses = {w[0] for w in (w_loan + w_marg) if w and w[0]}

    interest_due = {}
    for wh in warehouses:
        # Dated principal changes: +loan, -margin
        changes = {}

        for e in LoanData.query.filter_by(stockist_name=name, warehouse=wh).all():
            amt = float(e.amount or 0.0)
            if amt:
                changes[e.date] = changes.get(e.date, 0.0) + amt

        for e in MarginData.query.filter_by(stockist_name=name, warehouse=wh).all():
            amt = float(e.amount or 0.0)
            if amt:
                changes[e.date] = changes.get(e.date, 0.0) - amt

        interest_amt = _accrue_piecewise(changes, today_dt, daily_rate)
        interest_due[wh] = round(interest_amt, 2)

    # Render
    return render_template(
        "user/stockist_module.html",
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
        today=today_dt.strftime("%d/%m/%Y"),
    )
