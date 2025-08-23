# routes/company/final_report.py
from __future__ import annotations

from flask import Blueprint, render_template, request, flash
from datetime import datetime, date, timedelta
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


def _parse_float(s: str, default: float = 0.0) -> float:
    try:
        return float((s or "").strip() or default)
    except Exception:
        return default


def _get_dropdowns():
    warehouses = [w[0] for w in db.session.query(StockData.warehouse).distinct().all() if w[0]]
    commodities = [c[0] for c in db.session.query(StockData.commodity).distinct().all() if c[0]]
    stockists = [s[0] for s in db.session.query(StockData.stockist_name).distinct().all() if s[0]]
    return warehouses, commodities, stockists


def _sum_scalar(query):
    val = query.scalar()
    return float(val or 0.0)


# --- daily accrual interest (unchanged; no quality filter applied here) ---
def _compute_interest(stockist: str, upto_date: date, commodity: str | None, warehouse: str | None) -> float:
    """
    Daily simple interest @13.75% p.a. on:
        outstanding = (cash loan + margin loan - margin paid)
    Outstanding is accumulated from transactions up to 'upto_date'.
    Interest is summed daily between transaction dates (inclusive end).
    """
    # Loans add to outstanding
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

    from collections import defaultdict
    delta_by_date = defaultdict(float)

    for dt, amt, _loan_type in loans:
        if dt and amt:
            delta_by_date[dt] += float(amt)

    for dt, amt in margins:
        if dt and amt:
            delta_by_date[dt] -= float(amt)

    if not delta_by_date:
        return 0.0

    dates = sorted(delta_by_date.keys())
    current_date = dates[0]
    if current_date > upto_date:
        return 0.0

    outstanding = 0.0
    interest_total = 0.0

    for d in dates:
        if d > upto_date:
            break
        # accrue from current_date up to the day BEFORE 'd'
        if d > current_date:
            days = (d - current_date).days
            if days > 0 and outstanding > 0:
                interest_total += outstanding * DAILY_RATE * days
        # apply all deltas on the event day
        outstanding += delta_by_date[d]
        if outstanding < 0:
            outstanding = 0.0
        current_date = d

    # accrue from last event day THROUGH upto_date (inclusive)
    if current_date <= upto_date and outstanding > 0:
        days = (upto_date - current_date).days + 1
        if days > 0:
            interest_total += outstanding * DAILY_RATE * days

    return round(interest_total, 2)


from datetime import timedelta
from sqlalchemy import func

def _accrue_piecewise(changes_by_date: dict, as_of: date, per_unit_per_day: float) -> float:
    """
    changes_by_date: {date -> delta_level}, where level is in MT.
    Accrues per day from each change date up to next change (exclusive), and up to as_of (inclusive).
    """
    if not changes_by_date:
        return 0.0
    # keep only dates <= as_of
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
        running = max(0.0, running + changes.get(d, 0.0))  # never accrue negative
        nxt = keys[i + 1]
        if nxt <= d:
            continue
        days = (nxt - d).days
        if running > 0 and days > 0:
            total += running * per_unit_per_day * days
    return total

def _rental_for_combination(
    stockist: str,
    upto_date: date,
    commodity: str | None,
    warehouse: str | None,
    quality: str | None,
) -> float:
    """
    Rental up to 'upto_date'.
    - EXCEPTION_STOCKIST: flat ₹800/ton on net stock (ins - outs) as of 'upto_date'
    - Others: ₹3.334/ton/day using a daily timeline (+IN on in-dates, -OUT on out-dates).
    Applies optional quality filter to both IN and OUT.
    """
    stockist_u = (stockist or "").strip().upper()
    quality_u = (quality or "").strip().upper()

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
    if quality_u and quality_u != "ALL":
        in_q = in_q.filter(func.upper(StockData.quality) == quality_u)
        out_q = out_q.filter(func.upper(StockExit.quality) == quality_u)

    # Flat rule for the exception stockist
    if stockist_u == EXCEPTION_STOCKIST.upper():
        total_in = (in_q.with_entities(func.coalesce(func.sum(StockData.quantity), 0.0)).scalar() or 0.0)
        # prefer net_qty for exits if present, else quantity
        total_out = (out_q.with_entities(func.coalesce(func.sum(StockExit.net_qty), 0.0)).scalar() or 0.0)
        if total_out <= 0:
            total_out = (out_q.with_entities(func.coalesce(func.sum(StockExit.quantity), 0.0)).scalar() or 0.0)
        net_kg = max(0.0, float(total_in) - float(total_out))
        return (net_kg / KG_PER_TON) * FLAT_YEARLY_PER_TON

    # Build daily changes in MT (no rst_no needed)
    changes = {}
    for s in in_q.all():
        qty_mt = float(s.quantity or 0.0) / KG_PER_TON
        if qty_mt:
            changes[s.date] = changes.get(s.date, 0.0) + qty_mt

    for ex in out_q.all():
        # prefer net_qty if available
        qkg = float(ex.net_qty if getattr(ex, "net_qty", None) is not None else (ex.quantity or 0.0))
        qty_mt = qkg / KG_PER_TON
        if qty_mt:
            changes[ex.date] = changes.get(ex.date, 0.0) - qty_mt

    return _accrue_piecewise(changes, upto_date, RATE_PER_TON_PER_DAY)


@bp.route("/final-report", methods=["GET", "POST"])
def final_report():
    """
    Adds split pricing:
      - Accepts 'bd_qty' (quantity in KG to be valued at rate_bd),
        'rate_good' (₹/kg), 'rate_bd' (₹/kg).
      - Remaining (net_qty - bd_qty) is valued at rate_good.
    """
    warehouses, commodities, stockists = _get_dropdowns()

    # Defaults for template
    ctx = {
        "warehouses": warehouses,
        "commodities": commodities,
        "stockists": stockists,
        "result": None,  # computed dict
        "input_stockist": "",
        "input_date": "",
        "input_rate_good": "",
        "input_rate_bd": "",
        "input_bd_qty": "",
        "input_commodity": "",
        "input_warehouse": "",
        "input_quality": "",
    }

    if request.method == "POST":
        stockist = (request.form.get("stockist") or "").strip()
        date_str = (request.form.get("date") or "").strip()

        # NEW inputs
        rate_good_str = (request.form.get("rate_good") or "").strip()
        rate_bd_str   = (request.form.get("rate_bd") or "").strip()
        bd_qty_str    = (request.form.get("bd_qty") or "").strip()   # Quantity at BD rate (in KG)

        commodity = (request.form.get("commodity") or "").strip()
        warehouse = (request.form.get("warehouse") or "").strip()
        quality   = (request.form.get("quality") or "").strip()

        ctx.update({
            "input_stockist": stockist,
            "input_date": date_str,
            "input_rate_good": rate_good_str,
            "input_rate_bd": rate_bd_str,
            "input_bd_qty": bd_qty_str,
            "input_commodity": commodity,
            "input_warehouse": warehouse,
            "input_quality": quality,
        })

        if not stockist:
            flash("Stockist is required.", "danger")
            return render_template("company/final_report.html", **ctx)
        upto_date = _parse_date(date_str)
        if not upto_date:
            flash("Valid date is required (YYYY-MM-DD).", "danger")
            return render_template("company/final_report.html", **ctx)

        # --- 1) Total Quantity (sum of StockData.quantity up to date) with optional filters ---
        in_q = db.session.query(func.coalesce(func.sum(StockData.quantity), 0.0)) \
            .filter(StockData.date <= upto_date,
                    func.upper(StockData.stockist_name) == func.upper(stockist))
        if commodity:
            in_q = in_q.filter(StockData.commodity == commodity)
        if warehouse:
            in_q = in_q.filter(StockData.warehouse == warehouse)
        if quality and quality.strip().upper() != "ALL":
            in_q = in_q.filter(func.upper(StockData.quality) == func.upper(quality))
        total_qty = _sum_scalar(in_q)  # KG

        # --- 2) Reduction = 1.5% of total quantity (only for Maize) ---
        reduction = 0.0
        if (commodity or "").strip().lower() == "maize":
            reduction = round(total_qty * 0.015, 3)

        # --- 3) Net Quantity (KG) ---
        net_qty = max(0.0, total_qty - reduction)

        # --- 4) Parse rates & BD quantity (KG) ---
        rate_good = _parse_float(rate_good_str, 0.0)
        rate_bd   = _parse_float(rate_bd_str, 0.0)
        bd_qty    = _parse_float(bd_qty_str, 0.0)

        # Clamp bd_qty to [0, net_qty]
        if bd_qty < 0:
            bd_qty = 0.0
        if bd_qty > net_qty:
            bd_qty = net_qty

        good_qty = max(0.0, net_qty - bd_qty)

        # --- 5) Cost split ---
        cost_bd   = bd_qty   * rate_bd
        cost_good = good_qty * rate_good
        total_cost = cost_bd + cost_good

        # --- 6) Rental (with quality filter for IN/OUT) ---
        rental = _rental_for_combination(
            stockist=stockist,
            upto_date=upto_date,
            commodity=commodity or None,
            warehouse=warehouse or None,
            quality=quality or None,
        )

        # --- 7) Interest (no quality filter applied) ---
        interest = _compute_interest(
            stockist=stockist,
            upto_date=upto_date,
            commodity=commodity or None,
            warehouse=warehouse or None,
        )

        # --- 8) Cash Loan (no quality) ---
        cash_q = db.session.query(func.coalesce(func.sum(LoanData.amount), 0.0)) \
            .filter(func.upper(LoanData.stockist_name) == func.upper(stockist),
                    LoanData.date <= upto_date,
                    func.upper(LoanData.loan_type) == func.upper("Cash"))
        if commodity:
            cash_q = cash_q.filter(LoanData.commodity == commodity)
        if warehouse:
            cash_q = cash_q.filter(LoanData.warehouse == warehouse)
        cash_loan = _sum_scalar(cash_q)

        # --- 9) Margin Loan (no quality) ---
        margin_loan_q = db.session.query(func.coalesce(func.sum(LoanData.amount), 0.0)) \
            .filter(func.upper(LoanData.stockist_name) == func.upper(stockist),
                    LoanData.date <= upto_date,
                    func.upper(LoanData.loan_type) == func.upper("Margin"))
        if commodity:
            margin_loan_q = margin_loan_q.filter(LoanData.commodity == commodity)
        if warehouse:
            margin_loan_q = margin_loan_q.filter(LoanData.warehouse == warehouse)
        margin_loan = _sum_scalar(margin_loan_q)

        # --- 10) Margin Paid (no quality) ---
        margin_paid_q = db.session.query(func.coalesce(func.sum(MarginData.amount), 0.0)) \
            .filter(func.upper(MarginData.stockist_name) == func.upper(stockist),
                    MarginData.date <= upto_date)
        if commodity:
            margin_paid_q = margin_paid_q.filter(MarginData.commodity == commodity)
        if warehouse:
            margin_paid_q = margin_paid_q.filter(MarginData.warehouse == warehouse)
        margin_paid = _sum_scalar(margin_paid_q)

        # --- 11) Net Payable ---
        net_payable = total_cost - rental - interest - cash_loan - margin_loan + margin_paid

        ctx["result"] = {
            # quantities
            "total_qty": round(total_qty, 2),
            "reduction": round(reduction, 2),
            "net_qty": round(net_qty, 2),
            "bd_qty": round(bd_qty, 2),
            "good_qty": round(good_qty, 2),
            # rates
            "rate_good": round(rate_good, 2),
            "rate_bd": round(rate_bd, 2),
            # costs
            "cost_good": round(cost_good, 2),
            "cost_bd": round(cost_bd, 2),
            "total_cost": round(total_cost, 2),
            # charges/loans
            "rental": round(rental, 2),
            "interest": round(interest, 2),
            "cash_loan": round(cash_loan, 2),
            "margin_loan": round(margin_loan, 2),
            "margin_paid": round(margin_paid, 2),
            # final
            "net_payable": round(net_payable, 2),
        }

    return render_template("company/final_report.html", **ctx)
