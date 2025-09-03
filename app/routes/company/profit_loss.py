# routes/company/profit_loss.py
from __future__ import annotations

from flask import Blueprint, jsonify, render_template
from datetime import datetime, timedelta, date
from collections import defaultdict

from sqlalchemy import text

from app import db
from app.routes.company.interest_payble import calculate_interest_payable_upto_today
from app.models import (
    StockData,
    StockExit,
    LoanData,
    MarginData,
    StockistLoanRepayment,
)

bp = Blueprint('profit_loss', __name__, url_prefix='/company')

# ---- Constants (shared) ----
ANNUAL_INTEREST_RATE = 0.1375  # 13.75% p.a.
DAILY_RATE = ANNUAL_INTEREST_RATE / 365.0
KG_PER_TON = 1000.0
RENTAL_PER_TON = 800.0  # flat ₹/ton (not pro-rated)
EXCEPTION_STOCKIST = "ANUNAY AGRO"


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
    KG_PER_TON_LOCAL = 1000.0

    # ----- Determine date range -----
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
    anunay_net_ton = max(0.0, anunay_net_kg) / KG_PER_TON_LOCAL
    anunay_agro_rental = anunay_net_ton * FLAT_YEARLY_PER_TON  # full flat, not pro-rated

    # ----- (B) OTHERS: month-wise @ ₹3.334/ton/day (exclude ANUNAY) -----
    others_monthly = defaultdict(float)

    current_date = start_date
    while current_date <= end_date:
        ins = db.session.execute(
            text("""
                SELECT stockist_name, COALESCE(SUM(quantity), 0) AS total_in
                FROM stock_data
                WHERE date <= :d AND UPPER(stockist_name) <> UPPER(:name)
                GROUP BY stockist_name
            """),
            {"d": current_date, "name": EXCEPTION_STOCKIST}
        ).fetchall()

        outs = db.session.execute(
            text("""
                SELECT stockist_name, COALESCE(SUM(quantity), 0) AS total_out
                FROM stock_exit
                WHERE date <= :d AND UPPER(stockist_name) <> UPPER(:name)
                GROUP BY stockist_name
            """),
            {"d": current_date, "name": EXCEPTION_STOCKIST}
        ).fetchall()

        in_by = { (r.stockist_name or "").strip(): float(r.total_in or 0.0) for r in ins }
        out_by = { (r.stockist_name or "").strip(): float(r.total_out or 0.0) for r in outs }
        stockists = set(in_by.keys()) | set(out_by.keys())

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
    keys = sorted(d for d in changes_by_date.keys() if d and d <= as_of)
    if not keys:
        return 0.0

    outstanding = 0.0
    total_interest = 0.0
    current = keys[0]

    for d in keys:
        if d > as_of:
            break
        if d > current and outstanding > 0:
            days = (d - current).days
            if days > 0:
                total_interest += outstanding * DAILY_RATE * days
        outstanding += float(changes_by_date.get(d, 0.0))
        if outstanding < 0:
            outstanding = 0.0
        current = d

    if current <= as_of and outstanding > 0:
        days = (as_of - current).days + 1
        if days > 0:
            total_interest += outstanding * DAILY_RATE * days

    return total_interest


def _calculate_interest_receivable_upto_today_including_repayments() -> float:
    as_of = datetime.today().date()

    loan_stockists = {s[0] for s in db.session.query(LoanData.stockist_name).distinct().all() if s[0]}
    margin_stockists = {s[0] for s in db.session.query(MarginData.stockist_name).distinct().all() if s[0]}
    repay_stockists = {s[0] for s in db.session.query(StockistLoanRepayment.stockist_name).distinct().all() if s[0]}
    all_stockists = loan_stockists | margin_stockists | repay_stockists

    grand_total = 0.0

    for name in all_stockists:
        if not name:
            continue
        changes = defaultdict(float)

        for dt, amt in db.session.query(LoanData.date, LoanData.amount)\
                                 .filter(LoanData.stockist_name == name,
                                         LoanData.date <= as_of).all():
            if dt and amt:
                changes[dt] += float(amt)

        for dt, amt in db.session.query(MarginData.date, MarginData.amount)\
                                 .filter(MarginData.stockist_name == name,
                                         MarginData.date <= as_of).all():
            if dt and amt:
                changes[dt] -= float(amt)

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
    receivable = _calculate_interest_receivable_upto_today_including_repayments()
    payable = calculate_interest_payable_upto_today()  # your existing logic
    net_financing_profit = receivable - payable

    return jsonify({
        "receivable": receivable,
        "payable": payable,
        "net": round(net_financing_profit, 2)
    })


# -------------------------------------------------------
# Trading Activity (NEW) — uses breakeven up to each exit
# -------------------------------------------------------
def _breakeven_per_ton(commodity: str, quality: str, as_of: date) -> float:
    """
    Breakeven per ton up to 'as_of' for ANUNAY AGRO & given commodity/quality.

    breakeven/ton = avg_purchase_price_per_ton
                  + RENTAL_PER_TON
                  + (avg_purchase_price_per_ton * DAILY_RATE * qty_weighted_avg_days)
    """
    if not commodity or not as_of:
        return 0.0

    lots = (
        StockData.query.filter(
            StockData.stockist_name == EXCEPTION_STOCKIST,
            StockData.commodity == commodity,
            StockData.quality == quality,
            StockData.date <= as_of,
        )
        .order_by(StockData.date.asc())
        .all()
    )

    total_qty_kg = 0.0
    total_cost_rs = 0.0
    weighted_days_sum = 0.0

    for s in lots:
        qty = float(s.quantity or 0.0)
        if qty <= 0:
            continue
        cost = float(s.cost or 0.0)
        age_days = max((as_of - s.date).days, 0)

        total_qty_kg += qty
        total_cost_rs += cost
        weighted_days_sum += qty * age_days

    if total_qty_kg <= 0:
        return 0.0

    avg_days_held = weighted_days_sum / total_qty_kg
    avg_price_per_ton = (total_cost_rs / total_qty_kg) * KG_PER_TON
    interest_per_ton = avg_price_per_ton * DAILY_RATE * avg_days_held
    breakeven_per_ton = avg_price_per_ton + RENTAL_PER_TON + interest_per_ton
    return float(round(breakeven_per_ton, 2))


@bp.route('/calculate-trading')
def calculate_trading_activity():
    """
    For each StockExit row where stockist_name = 'ANUNAY AGRO':
      profit_i = qty_kg * (rate_per_kg - breakeven_per_ton(as_of, commodity, quality)/1000)
    Returns total profit and a compact breakdown.
    """
    exits = (
        StockExit.query
        .filter(StockExit.stockist_name == EXCEPTION_STOCKIST)
        .order_by(StockExit.date.asc(), StockExit.commodity.asc(), StockExit.quality.asc())
        .all()
    )

    total_profit = 0.0
    breakdown = []

    # Cache breakevens per (date, commodity, quality) to avoid recomputation
    bk_cache: dict[tuple[date, str, str], float] = {}

    for row in exits:
        as_of = row.date
        commodity = (row.commodity or "").strip()
        quality = (row.quality or "").strip() or "Good"  # default if blank
        qty_kg = float(row.quantity or 0.0)
        rate_per_kg = float(row.rate or 0.0)

        if qty_kg <= 0 or not commodity:
            continue

        key = (as_of, commodity, quality)
        if key not in bk_cache:
            bk_cache[key] = _breakeven_per_ton(commodity, quality, as_of)

        bk_per_ton = bk_cache[key]
        bk_per_kg = bk_per_ton / KG_PER_TON if bk_per_ton > 0 else 0.0

        profit_i = qty_kg * (rate_per_kg - bk_per_kg)
        total_profit += profit_i

        breakdown.append({
            "date": as_of.strftime("%Y-%m-%d") if isinstance(as_of, date) else str(as_of),
            "commodity": commodity,
            "quality": quality,
            "quantity_kg": round(qty_kg, 3),
            "rate_per_kg": round(rate_per_kg, 2),
            "breakeven_per_kg": round(bk_per_kg, 2),
            "profit": round(profit_i, 2),
        })

    # Optional: bucket summary by commodity/quality
    by_combo = defaultdict(float)
    for b in breakdown:
        by_combo[(b["commodity"], b["quality"])] += b["profit"]
    summary = [
        {"commodity": c, "quality": q, "profit": round(p, 2)}
        for (c, q), p in sorted(by_combo.items())
    ]

    return jsonify({
        "total_trading_profit": round(total_profit, 2),
        "summary_by_combo": summary,
        "rows": breakdown[:200]  # keep payload reasonable; adjust as needed
    })
