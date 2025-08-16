from flask import Blueprint, render_template, request
from app.models import StockData, StockExit
from sqlalchemy import func, and_
from datetime import datetime, timedelta
import pandas as pd
import io
from flask import send_file, make_response

bp = Blueprint('rental_calculator', __name__, url_prefix='/rental')


@bp.route('/calculator', methods=['GET', 'POST'])
def calculator():
    # Get all distinct stockists, warehouses, commodities for dropdowns
    stockists = [r[0] for r in StockData.query.with_entities(StockData.stockist_name).distinct()]
    warehouses = [r[0] for r in StockData.query.with_entities(StockData.warehouse).distinct()]
    commodities = [r[0] for r in StockData.query.with_entities(StockData.commodity).distinct()]

    data = []
    summary = {}
    filters = {}

    if request.method == 'POST':
        # Get form data
        date_str = request.form['date']
        upto_date = datetime.strptime(date_str, "%Y-%m-%d").date()
        stockist = request.form.get('stockist_name') or None
        warehouse = request.form.get('warehouse') or None
        commodity = request.form.get('commodity') or None

        filters['stockist_name'] = stockist or 'All'
        filters['warehouse'] = warehouse or 'All'
        filters['commodity'] = commodity or 'All'
        filters['date'] = date_str

        # Date range: earliest stockdata date to upto_date
        min_date = StockData.query.order_by(StockData.date).first().date
        all_dates = [min_date + timedelta(days=i) for i in range((upto_date - min_date).days + 1)]

        total_rental = 0
        last_net_qty = 0

        for d in all_dates:
            # Filter queries
            stockdata_q = StockData.query.filter(StockData.date <= d)
            stockexit_q = StockExit.query.filter(StockExit.date <= d)
            if stockist:
                stockdata_q = stockdata_q.filter(StockData.stockist_name == stockist)
                stockexit_q = stockexit_q.filter(StockExit.stockist_name == stockist)
            if warehouse:
                stockdata_q = stockdata_q.filter(StockData.warehouse == warehouse)
                stockexit_q = stockexit_q.filter(StockExit.warehouse == warehouse)
            if commodity:
                stockdata_q = stockdata_q.filter(StockData.commodity == commodity)
                stockexit_q = stockexit_q.filter(StockExit.commodity == commodity)

            qty_in = stockdata_q.with_entities(func.sum(StockData.quantity)).scalar() or 0
            qty_out = stockexit_q.with_entities(func.sum(StockExit.quantity)).scalar() or 0
            net_qty = qty_in - qty_out
            rental = round((net_qty / 1000) * 3.33, 2) if net_qty > 0 else 0
            total_rental += rental
            last_net_qty = net_qty

            data.append({
                'date': d.strftime("%Y-%m-%d"),
                'warehouse': warehouse or 'All',
                'commodity': commodity or 'All',
                'quantity': int(qty_in),
                'exit_quantity': int(qty_out),
                'net_quantity': int(net_qty),
                'rental': rental
            })

        summary = {
            'total_rental': round(total_rental, 2),
            'last_net_qty': int(last_net_qty),
            'filters': filters
        }

    return render_template('stockist/rental_calculator.html',
                           stockists=stockists, warehouses=warehouses, commodities=commodities,
                           data=data, summary=summary)


@bp.route('/export-excel', methods=['POST'])
def export_excel():
    # Get filtered data from the form submission (reuse calculation logic)
    data = request.form.get('data')
    if not data:
        return "No data to export", 400
    import json
    data = json.loads(data)
    df = pd.DataFrame(data)
    output = io.BytesIO()
    df.to_excel(output, index=False)
    output.seek(0)
    return send_file(output, as_attachment=True, download_name="rental_statement.xlsx", mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')


def HTML(string):
    pass


@bp.route('/export-pdf', methods=['POST'])
def export_pdf():
    # Render the table as HTML and convert to PDF
    data = request.form.get('data')
    summary = request.form.get('summary')
    import json
    data = json.loads(data)
    summary = json.loads(summary)
    html = render_template('stockist/rental_pdf.html', data=data, summary=summary)
    pdf_file = HTML(string=html).write_pdf()
    response = make_response(pdf_file)
    response.headers['Content-Type'] = 'application/pdf'
    response.headers['Content-Disposition'] = 'attachment; filename=rental_statement.pdf'
    return response

