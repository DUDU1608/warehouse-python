from flask import Blueprint, render_template, request
from datetime import datetime
from app.models import StockData, StockExit

bp = Blueprint('breakeven_calculator', __name__, url_prefix='/company')

@bp.route('/breakeven-price', methods=['GET', 'POST'])
def breakeven_calculator():
    qualities = ['Good', 'BD']
    results = {}
    input_date = request.form.get('date') if request.method == 'POST' else ''
    commodity = request.form.get('commodity') if request.method == 'POST' else ''

    if request.method == 'POST' and input_date and commodity:
        end_date = datetime.strptime(input_date, "%Y-%m-%d").date()
        for quality in qualities:
            stock_q = StockData.query.filter(
                StockData.stockist_name == "ANUNAY AGRO",
                StockData.commodity == commodity,
                StockData.quality == quality,
                StockData.date <= end_date
            )
            stockexit_q = StockExit.query.filter(
                StockExit.stockist_name == "ANUNAY AGRO",
                StockExit.commodity == commodity,
                StockExit.quality == quality,
                StockExit.date <= end_date
            )

            total_qty = sum(s.quantity or 0 for s in stock_q)
            total_exit_qty = sum(s.quantity or 0 for s in stockexit_q)
            net_stock = total_qty - total_exit_qty

            total_cost = sum(s.cost or 0 for s in stock_q)
            avg_price = (total_cost / total_qty) if total_qty > 0 else 0
            avg_price_per_ton = avg_price * 1000

            rental = 800  # Rs per ton

            all_dates = [s.date for s in stock_q]
            if all_dates:
                start_date = min(all_dates)
                days_held = (end_date - start_date).days if end_date >= start_date else 0
            else:
                days_held = 0

            interest_rate = 0.1375
            interest_per_day = (interest_rate / 365)
            interest = avg_price_per_ton * interest_per_day * days_held

            breakeven = avg_price_per_ton + rental + interest

            results[quality] = {
                "net_stock": net_stock,
                "avg_price_per_ton": round(avg_price_per_ton, 2),
                "rental": rental,
                "interest": round(interest, 2),
                "breakeven": round(breakeven, 2),
                "days_held": days_held,
            }

    # For dropdowns
    commodities = [c[0] for c in StockData.query.with_entities(StockData.commodity).distinct()]
    return render_template("company/breakeven_price.html",
                          results=results,
                          input_date=input_date, input_commodity=commodity,
                          commodities=commodities)
