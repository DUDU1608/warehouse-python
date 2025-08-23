from flask import Blueprint, jsonify, render_template
from datetime import datetime, timedelta, date
from collections import defaultdict

from sqlalchemy import text, func

from app import db
from app.routes.company.interest_payble import calculate_interest_payable_upto_today
# (We no longer import company.interest_receivable; we implement a repayment-aware version here)
from app.models import (
    StockData,
    StockExit,
    LoanData,
    MarginData,
    StockistLoanRepayment,   # ✅ used to subtract repayments in receivable calc
)

bp = Blueprint('profit_loss', __name__, url_prefix='/company')

ANNUAL_INTEREST_RATE = 0.1375  # 13.75% p.a.
DAILY_RATE = ANNUAL_INTEREST_RATE / 365.0


@bp.route('/profit-loss')
def profit_loss():
    return render_template('company/profit_loss.html')


# ----------------------------
# Warehousing (unchanged)
# ----------------------------
@bp.route('/calculate-warehousing')
def calculate_warehousing():
    # --- Rates / constants ---
    RATE_PER_TON_PER_DAY = 3.334
    FLAT_YEARLY_PER_TON = 800.0             # applies to ANUNAY AGRO (flat, not pro-rated)
    EXCEPTION_STOCKIST = "ANUNAY AGRO"
    KG_PER_TON = 1000.0

    # ----- Determine date range -----
    # earliest date across both tables
    min_row = db.session.execute(text("""
        SELECT MIN(min_d) AS min_date FROM (
            SELECT MIN(date) AS min_d FROM stock_data
            UNION ALL
            SELECT MIN(date) AS min_d FROM stock_exit
        ) t
    """)).fetchone()

    if not min_row or not min_row.min_date:
        return jsonify({
            "anunay_agro_rental": 0.0,
            "others_rental_by_month": [],
            "total_rental": 0.0
        })

    # Robust parse (driver may return str/date/datetime)
    min_raw = min_row.min_date
    if isinstance(min_raw, str):
        start_date = datetime.strptime(min_raw, "%Y-%m-%d").date()
    else:
        start_date = getattr(min_raw, "date", lambda: min_raw)()

    end_date = datetime.today().date()

    # ----- (A) ANUNAY AGRO: flat ₹800/ton on current net stock as of today -----
    anunay_net_row = db.session.execute(
        text("""
            SELECT
                COALESCE((
                    SELECT SUM(quantity)
                    FROM stock_data
                    WHERE UPPER(stockist_name) = UPPER(:name) AND date <= :d
                ), 0) -
                COALESCE((
                    SELECT SUM(quantity)
                    FROM stock_exit
                    WHERE UPPER(stockist_name) = UPPER(:name) AND date <= :d
                ), 0) AS net_kg
        """),
        {"name": EXCEPTION_STOCKIST, "d": end_date}
    ).fetchone()

    anunay_net_kg = float(anunay_net_row.net_kg or 0.0)
    anunay_net_ton = max(0.0, anunay_net_kg) / KG_PER_TON
    anunay_agro_rental = anunay_net_ton * FLAT_YEARLY_PER_TON  # full flat, not pro-rated

    # ----- (B) OTHERS: month-wise @ ₹3.334/ton/day (exclude ANUNAY) -----
    others_monthly = defaultdict(float)

    current_date = start_date
    while current_date <= end_date:
        # Aggregate IN (excluding ANUNAY)
        ins = db.session.execute(
            text("""
                SELECT stockist_name, COALESCE(SUM(quantity), 0) AS total_in
                FROM stock_data
                WHERE date <= :d AND UPPER(stockist_name) <> UPPER(:name)
                GROUP BY stockist_name
            """),
            {"d": current_date, "name": "ANUNAY AGRO"}
        ).fetchall()

        # Aggregate OUT (excluding ANUNAY)
        outs = db.session.execute(
            text("""
                SELECT stockist_name, COALESCE(SUM(quantity), 0) AS total_out
                FROM stock_exit
                WHERE date <= :d AND UPPER(stockist_name) <> UPPER(:name)
                GROUP BY stockist_name
            """),
            {"d": current_date, "name": "ANUNAY AGRO"}
        ).fetchall()

        in_by = { (r.stockist_name or "").strip(): float(r.total_in or 0.0) for r in ins }
        out_by = { (r.stockist_name or "").strip(): float(r.total_out or 0.0) for r in outs }
        stockists = set(in_by.keys()) | set(out_by.keys())

        # Month label (with "Upto" suffix for current month)
        month_label = current_date.strftime("%b %Y")
        if current_date.month == end_date.month and current_date.year == end_date.year:
            month_label = f"{end_date.strftime('%b %Y')} (Upto {end_date.strftime('%d/%m/%y')})"

        day_rent = 0.0
        for name in stockists:
            net_kg = max(0.0, in_by.get(name, 0.0) - out_by.get(name, 0.0))
            if net_kg <= 0.0:
                continue
            net_ton = net_kg / 1000.0
            day_rent += net_ton * RATE_PER_TON_PER_DAY

        if day_rent:
            others_monthly[month_label] += day_rent

        current_date += timedelta(days=1)

    # ----- Prepare response -----
    others_list = [{"month": m, "rental": round(v, 2)} for m, v in others_monthly.items()]
    total_rental = anunay_agro_rental + sum(v for v in others_monthly.values())

    return jsonify({
        "anunay_agro_rental": round(anunay_agro_rental, 2),
        "others_rental_by_month": others_list,
        "total_rental": round(total_rental, 2)
    })


# ---------------------------------------------
# Financing (Receivable includes repayments)
# ---------------------------------------------
def _accrue_interest_piecewise(changes_by_date: dict[date, float], as_of: date) -> float:
    """
    Given a mapping of date -> delta outstanding (₹), accrue daily simple interest
    at DAILY_RATE. Applies each delta at start of its day. Prevents negative outstanding.
    """
    # Only keep events up to as_of
    keys = sorted(d for d in changes_by_date.keys() if d and d <= as_of)
    if not keys:
        return 0.0

    outstanding = 0.0
    total_interest = 0.0
    current = keys[0]

    for d in keys:
        if d > as_of:
            break
        # accrue from 'current' up to the day BEFORE 'd'
        if d > current and outstanding > 0:
            days = (d - current).days
            if days > 0:
                total_interest += outstanding * DAILY_RATE * days
        # apply all deltas on day d
        outstanding += float(changes_by_date.get(d, 0.0))
        if outstanding < 0:
            outstanding = 0.0
        current = d

    # accrue through as_of (inclusive)
    if current <= as_of and outstanding > 0:
        days = (as_of - current).days + 1
        if days > 0:
            total_interest += outstanding * DAILY_RATE * days

    return total_interest


def _calculate_interest_receivable_upto_today_including_repayments() -> float:
    """
    Company’s interest receivable across ALL stockists up to today.
    Outstanding per stockist = +loans (cash+margin) - margins paid - loan repayments.
    Accrual is computed PER STOCKIST to avoid cross-offsetting.
    """
    as_of = datetime.today().date()

    # Distinct stockists (from any of the three tables)
    loan_stockists = {s[0] for s in db.session.query(LoanData.stockist_name).distinct().all() if s[0]}
    margin_stockists = {s[0] for s in db.session.query(MarginData.stockist_name).distinct().all() if s[0]}
    repay_stockists = {s[0] for s in db.session.query(StockistLoanRepayment.stockist_name).distinct().all() if s[0]}
    all_stockists = loan_stockists | margin_stockists | repay_stockists

    grand_total = 0.0

    for name in all_stockists:
        if not name:
            continue

        # Build date -> delta outstanding for this stockist
        changes = defaultdict(float)

        # + Loans (both types) up to today
        for dt, amt in db.session.query(LoanData.date, LoanData.amount)\
                                 .filter(LoanData.stockist_name == name,
                                         LoanData.date <= as_of).all():
            if dt and amt:
                changes[dt] += float(amt)

        # - Margins paid up to today
        for dt, amt in db.session.query(MarginData.date, MarginData.amount)\
                                 .filter(MarginData.stockist_name == name,
                                         MarginData.date <= as_of).all():
            if dt and amt:
                changes[dt] -= float(amt)

        # - Loan repayments up to today  ✅ include in receivable
        for dt, amt in db.session.query(StockistLoanRepayment.date, StockistLoanRepayment.amount)\
                                 .filter(StockistLoanRepayment.stockist_name == name,
                                         StockistLoanRepayment.date <= as_of).all():
            if dt and amt:
                changes[dt] -= float(amt)

        if not changes:
            continue

        grand_total += _accrue_interest_piecewise(changes, as_of)

    return round(grand_total, 2)


@bp.route('/calculate-financing')
def calculate_financing_activity():
    receivable = _calculate_interest_receivable_upto_today_including_repayments()  # ✅ uses repayments
    payable = calculate_interest_payable_upto_today()  # keep your existing payable logic
    net_financing_profit = receivable - payable

    return jsonify({
        "receivable": receivable,
        "payable": payable,
        "net": round(net_financing_profit, 2)
    })
