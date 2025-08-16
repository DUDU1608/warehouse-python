from flask import Blueprint, jsonify, render_template
from datetime import datetime
from app import db
from app.routes.company.interest_payble import calculate_interest_payable_upto_today
from app.routes.company.interest_receivable import calculate_interest_receivable_upto_today

bp = Blueprint('profit_loss', __name__, url_prefix='/company')

@bp.route('/profit-loss')
def profit_loss():
    return render_template('company/profit_loss.html')

@bp.route('/calculate-warehousing')
def calculate_warehousing():
    from flask import jsonify
    from sqlalchemy import text
    from datetime import datetime, timedelta
    from collections import defaultdict

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
            {"d": current_date, "name": EXCEPTION_STOCKIST}
        ).fetchall()

        # Aggregate OUT (excluding ANUNAY)
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

        # Month label (with "Upto" suffix for current month)
        month_label = current_date.strftime("%b %Y")
        if current_date.month == end_date.month and current_date.year == end_date.year:
            month_label = f"{end_date.strftime('%b %Y')} (Upto {end_date.strftime('%d/%m/%y')})"

        day_rent = 0.0
        for name in stockists:
            net_kg = max(0.0, in_by.get(name, 0.0) - out_by.get(name, 0.0))
            if net_kg <= 0.0:
                continue
            net_ton = net_kg / KG_PER_TON
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


@bp.route('/calculate-financing')
def calculate_financing_activity():
    receivable = calculate_interest_receivable_upto_today()
    payable = calculate_interest_payable_upto_today()
    net_financing_profit = receivable - payable

    return jsonify({
        "receivable": receivable,
        "payable": payable,
        "net": round(net_financing_profit, 2)
    })
