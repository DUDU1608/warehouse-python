# routes/company/final_report.py
from __future__ import annotations

from flask import Blueprint, render_template, request, flash
from datetime import datetime, date
from sqlalchemy import func
from app import db
from app.models import StockData, StockExit, LoanData, MarginData  # ensure these exist

bp = Blueprint("final_report", __name__, url_prefix="/company")

RATE_PER_TON_PER_DAY = 3.334
FLAT_YEARLY_PER_TON = 800.0
EXCEPTION_STOCKIST = "ANUNAY AGRO"
KG_PER_TON = 1000.0
ANNUAL_INTEREST_RATE = 0.1375  # 13.75% per annum
DAILY_RATE = ANNUAL_INTEREST_RATE / 365.0


def _parse_date(s: str) -> date | None:
    try:
        return datetime.strptime(s, "%Y-%m-%d").date()
    except Exception:
        return None


def _get_dropdowns():
    warehouses = [w[0] for w in db.session.query(StockData.warehouse).distinct().all() if w[0]]
    commodities = [c[0] for c in db.session.query(StockData.commodity).distinct().all() if c[0]]
    stockists = [s[0] for s in db.session.query(StockData.stockist_name).distinct().all() if s[0]]
    return warehouses, commodities, stockists


def _sum_scalar(query):
    val = query.scalar()
    return float(val or 0.0)


# --- replace the old _sum_interest(...) with this daily accrual version ---
def _compute_interest(stockist: str, upto_date: date, commodity: str | None, warehouse: str | None) -> float:
    """
    Daily simple interest @13.75% p.a. on:
        outstanding = (cash loan + margin loan - margin paid)
    Outstanding is accumulated from transactions up to 'upto_date'.
    Interest is summed daily between transaction dates (inclusive end).
    """
    # Loans (both cash + margin) add to outstanding
    loans_q = db.session.query(LoanData.date, LoanData.amount, LoanData.loan_type).filter(
        func.upper(LoanData.stockist_name) == func.upper(stockist),
        LoanData.date <= upto_date
    )
    if commodity:
        loans_q = loans_q.filter(LoanData.commodity == commodity)
    if warehouse:
        loans_q = loans_q.filter(LoanData.warehouse == warehouse)
    loans = loans_q.order_by(LoanData.date.asc()).all()

    # Margin paid reduces outstanding
    margins_q = db.session.query(MarginData.date, MarginData.amount).filter(
        func.upper(MarginData.stockist_name) == func.upper(stockist),
        MarginData.date <= upto_date
    )
    if commodity:
        margins_q = margins_q.filter(MarginData.commodity == commodity)
    if warehouse:
        margins_q = margins_q.filter(MarginData.warehouse == warehouse)
    margins = margins_q.order_by(MarginData.date.asc()).all()

    # Build date -> delta map (sum multiple events on same day)
    from collections import defaultdict
    delta_by_date = defaultdict(float)

    for dt, amt, loan_type in loans:
        if dt is None or amt is None:
            continue
        # cash or margin loans both INCREASE outstanding
        delta_by_date[dt] += float(amt or 0.0)

    for dt, amt in margins:
        if dt is None or amt is None:
            continue
        # margin paid DECREASES outstanding
        delta_by_date[dt] -= float(amt or 0.0)

    if not delta_by_date:
        return 0.0

    # Iterate through dates in order, accruing interest between events
    dates = sorted(delta_by_date.keys())
    current_date = dates[0]
    # If first event occurs after upto_date, no accrual
    if current_date > upto_date:
        return 0.0

    outstanding = 0.0
    interest_total = 0.0

    # Process each event day
    for d in dates:
        if d > upto_date:
            break
        # Accrue interest from current_date up to the day BEFORE 'd'
        if d > current_date:
            days = (d - current_date).days  # exclusive of 'd'
            if days > 0 and outstanding > 0:
                interest_total += outstanding * DAILY_RATE * days
        # Apply all deltas on day 'd'
        outstanding += delta_by_date[d]
        if outstanding < 0:
            outstanding = 0.0  # do not allow negative outstanding for interest
        current_date = d

    # Accrue from the last processed date THROUGH upto_date (inclusive)
    if current_date <= upto_date and outstanding > 0:
        days = (upto_date - current_date).days + 1  # inclusive end date
        if days > 0:
            interest_total += outstanding * DAILY_RATE * days

    return round(interest_total, 2)


def _rental_for_combination(stockist: str, upto_date: date, commodity: str | None, warehouse: str | None) -> float:
    """
    Rental for entered combination up to entered date.
    - ANUNAY AGRO: flat ₹800/ton on net stock (ins - outs) as of 'upto_date'
    - Others: ₹3.334/ton/day using per-entry days, subtracting exits per RST
    """
    stockist_u = (stockist or "").strip().upper()

    # Base filters for IN and OUT
    in_q = StockData.query.filter(
        func.upper(StockData.stockist_name) == func.upper(stockist),
        StockData.date <= upto_date
    )
    out_q = StockExit.query.filter(
        func.upper(StockExit.stockist_name) == func.upper(stockist),
        StockExit.date <= upto_date
    )
    if commodity:
        in_q = in_q.filter(StockData.commodity == commodity)
        out_q = out_q.filter(StockExit.commodity == commodity)
    if warehouse:
        in_q = in_q.filter(StockData.warehouse == warehouse)
        out_q = out_q.filter(StockExit.warehouse == warehouse)

    if stockist_u == EXCEPTION_STOCKIST.upper():
        # Flat ₹800/ton on net stock as of date
        total_in = _sum_scalar(in_q.with_entities(func.coalesce(func.sum(StockData.quantity), 0.0)))
        total_out = _sum_scalar(out_q.with_entities(func.coalesce(func.sum(StockExit.quantity), 0.0)))
        net_kg = max(0.0, total_in - total_out)
        net_ton = net_kg / KG_PER_TON
        return net_ton * FLAT_YEARLY_PER_TON

    # Others: need exit per RST map
    exits = out_q.all()
    exit_by_rst = {}
    for ex in exits:
        rst = ex.rst_no or ""
        exit_by_rst[rst] = exit_by_rst.get(rst, 0.0) + float(ex.quantity or 0.0)

    rental_total = 0.0
    stocks = in_q.all()
    for s in stocks:
        days = (upto_date - s.date).days + 1
        if days <= 0:
            continue
        qty_in = float(s.quantity or 0.0)
        qty_out = float(exit_by_rst.get(s.rst_no or "", 0.0))
        net_qty = qty_in - qty_out  # KG
        if net_qty <= 0:
            continue
        rent = (net_qty / KG_PER_TON) * RATE_PER_TON_PER_DAY * days
        rental_total += rent

    return rental_total


@bp.route("/final-report", methods=["GET", "POST"])
def final_report():
    warehouses, commodities, stockists = _get_dropdowns()

    # Defaults
    ctx = {
        "warehouses": warehouses,
        "commodities": commodities,
        "stockists": stockists,
        "result": None,  # will hold computed dict for rendering
        "input_stockist": "",
        "input_date": "",
        "input_rate": "",
        "input_commodity": "",
        "input_warehouse": "",
    }

    if request.method == "POST":
        stockist = (request.form.get("stockist") or "").strip()
        date_str = (request.form.get("date") or "").strip()
        rate_str = (request.form.get("rate") or "").strip()
        commodity = (request.form.get("commodity") or "").strip()
        warehouse = (request.form.get("warehouse") or "").strip()

        ctx.update({
            "input_stockist": stockist,
            "input_date": date_str,
            "input_rate": rate_str,
            "input_commodity": commodity,
            "input_warehouse": warehouse,
        })

        # validations
        if not stockist:
            flash("Stockist is required.", "danger")
            return render_template("company/final_report.html", **ctx)
        upto_date = _parse_date(date_str)
        if not upto_date:
            flash("Valid date is required (YYYY-MM-DD).", "danger")
            return render_template("company/final_report.html", **ctx)

        # 1) Total Quantity (sum of quantity from stock_data)
        in_q = db.session.query(func.coalesce(func.sum(StockData.quantity), 0.0))\
            .filter(StockData.date <= upto_date,
                    func.upper(StockData.stockist_name) == func.upper(stockist))
        if commodity:
            in_q = in_q.filter(StockData.commodity == commodity)
        if warehouse:
            in_q = in_q.filter(StockData.warehouse == warehouse)
        total_qty = _sum_scalar(in_q)  # KG

        # 2) Reduction = 1.5% of total quantity
        reduction = round(total_qty * 0.015, 3)

        # 3) Net Quantity = (1) - (2)
        net_qty = max(0.0, total_qty - reduction)  # KG

        # 4) Rate (₹ per KG)
        try:
            rate = float(rate_str) if rate_str else 0.0
        except ValueError:
            rate = 0.0

        # 5) Total Cost = Net Quantity * Rate
        total_cost = net_qty * rate

        # 6) Rental (for entered combination up to date)
        rental = _rental_for_combination(stockist, upto_date, commodity or None, warehouse or None)

        # 7) Interest (sum for entered combination up to date)
        interest = _compute_interest(stockist, upto_date, commodity or None, warehouse or None)

        # 8) Cash Loan (sum loanType='Cash')
        cash_q = db.session.query(func.coalesce(func.sum(LoanData.amount), 0.0))\
            .filter(func.upper(LoanData.stockist_name) == func.upper(stockist),
                    LoanData.date <= upto_date,
                    func.upper(LoanData.loan_type) == func.upper("Cash"))
        if commodity:
            cash_q = cash_q.filter(LoanData.commodity == commodity)
        if warehouse:
            cash_q = cash_q.filter(LoanData.warehouse == warehouse)
        cash_loan = _sum_scalar(cash_q)

        # 9) Margin Loan (sum loanType='Margin')
        margin_loan_q = db.session.query(func.coalesce(func.sum(LoanData.amount), 0.0))\
            .filter(func.upper(LoanData.stockist_name) == func.upper(stockist),
                    LoanData.date <= upto_date,
                    func.upper(LoanData.loan_type) == func.upper("Margin"))
        if commodity:
            margin_loan_q = margin_loan_q.filter(LoanData.commodity == commodity)
        if warehouse:
            margin_loan_q = margin_loan_q.filter(LoanData.warehouse == warehouse)
        margin_loan = _sum_scalar(margin_loan_q)

        # 10) Margin Paid (sum from MarginData)
        margin_paid_q = db.session.query(func.coalesce(func.sum(MarginData.amount), 0.0))\
            .filter(func.upper(MarginData.stockist_name) == func.upper(stockist),
                    MarginData.date <= upto_date)
        if commodity:
            margin_paid_q = margin_paid_q.filter(MarginData.commodity == commodity)
        if warehouse:
            margin_paid_q = margin_paid_q.filter(MarginData.warehouse == warehouse)
        margin_paid = _sum_scalar(margin_paid_q)

        # 11) Net Payable = Total Cost - Rental - Interest - Cash Loan - Margin Loan + Margin Paid
        net_payable = total_cost - rental - interest - cash_loan - margin_loan + margin_paid

        ctx["result"] = {
            "total_qty": round(total_qty, 2),
            "reduction": round(reduction, 2),
            "net_qty": round(net_qty, 2),
            "rate": round(rate, 2),
            "total_cost": round(total_cost, 2),
            "rental": round(rental, 2),
            "interest": round(interest, 2),
            "cash_loan": round(cash_loan, 2),
            "margin_loan": round(margin_loan, 2),
            "margin_paid": round(margin_paid, 2),
            "net_payable": round(net_payable, 2),
        }

    return render_template("company/final_report.html", **ctx)
