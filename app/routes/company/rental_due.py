from flask import Blueprint, render_template, request
from datetime import datetime
from app.models import StockData, StockExit

bp = Blueprint('rental_due', __name__, url_prefix='/company')

# --- constants ---
RATE_PER_TON_PER_DAY = 3.34          # existing daily rate
FLAT_YEARLY_RATE = 800.0             # flat per ton per year for ANUNAY AGRO
EXCEPTION_STOCKIST = "ANUNAY AGRO"   # case-insensitive match
KG_PER_TON = 1000.0


@bp.route('/rental_due', methods=['GET', 'POST'])
def rental_due():
    rental_results = []
    total_rental = 0
    total_quantity = 0

    date_str = request.form.get('date') if request.method == 'POST' else ''
    warehouse = request.form.get('warehouse') if request.method == 'POST' else ''
    commodity = request.form.get('commodity') if request.method == 'POST' else ''

    input_date = date_str
    input_warehouse = warehouse
    input_commodity = commodity

    if date_str:
        upto_date = datetime.strptime(date_str, "%Y-%m-%d").date()

        # Filter incoming stock
        stocks_query = StockData.query.filter(StockData.date <= upto_date)
        if warehouse:
            stocks_query = stocks_query.filter(StockData.warehouse == warehouse)
        if commodity:
            stocks_query = stocks_query.filter(StockData.commodity == commodity)
        stocks = stocks_query.all()

        # Filter outgoing stock
        exits_query = StockExit.query.filter(StockExit.date <= upto_date)
        if warehouse:
            exits_query = exits_query.filter(StockExit.warehouse == warehouse)
        if commodity:
            exits_query = exits_query.filter(StockExit.commodity == commodity)
        exits = exits_query.all()

        # Group exits by RST No for subtraction
        from collections import defaultdict
        exit_qty_by_rst = defaultdict(float)
        for ex in exits:
            exit_qty_by_rst[ex.rst_no] += (ex.quantity or 0.0)

        for s in stocks:
            days = (upto_date - s.date).days + 1
            qty_in = s.quantity or 0.0
            qty_out = exit_qty_by_rst.get(s.rst_no, 0.0)
            net_qty = qty_in - qty_out  # in KG
            if net_qty <= 0:
                continue

            total_quantity += net_qty
            stockist = (s.stockist_name or "").strip()

            # Decide pricing
            if stockist.upper() == EXCEPTION_STOCKIST.upper():
                # Flat ₹800 per ton per YEAR irrespective of duration
                rent = (net_qty / KG_PER_TON) * FLAT_YEARLY_RATE
                rate_type = "FLAT_YEARLY"
                rate_display = f"₹{FLAT_YEARLY_RATE:.2f}/ton (yearly flat)"
                days_considered = 0  # days not used in flat pricing
                calc_note = f"Flat yearly charge for {EXCEPTION_STOCKIST} applied"
            else:
                # Regular per-day rate
                rent = (net_qty / KG_PER_TON) * RATE_PER_TON_PER_DAY * days
                rate_type = "DAILY"
                rate_display = f"₹{RATE_PER_TON_PER_DAY:.2f}/ton/day"
                days_considered = days
                calc_note = f"{RATE_PER_TON_PER_DAY:.2f} × tons × {days} day(s)"

            rental_results.append({
                "date": s.date,
                "rst_no": s.rst_no,
                "warehouse": s.warehouse,
                "stockist_name": s.stockist_name,
                "commodity": s.commodity,
                "quantity": round(net_qty, 2),     # in KG
                "days": days,                      # raw days difference (unchanged)
                "days_considered": days_considered, # used in billing (0 for flat)
                "rate_type": rate_type,
                "rate_display": rate_display,
                "rental": round(rent, 2),
                "calc_note": calc_note
            })
            total_rental += rent

    else:
        stocks = []

    # For dropdowns
    warehouses = [w[0] for w in StockData.query.with_entities(StockData.warehouse).distinct()]
    commodities = [c[0] for c in StockData.query.with_entities(StockData.commodity).distinct()]

    return render_template(
        "company/rental_due.html",
        rental_results=rental_results,
        total_rental=round(total_rental, 2),
        total_quantity=round(total_quantity, 2),
        warehouses=warehouses,
        commodities=commodities,
        input_date=input_date,
        input_warehouse=input_warehouse,
        input_commodity=input_commodity
    )
