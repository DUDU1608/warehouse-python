import io
import pandas as pd
from flask import Blueprint, render_template, request, redirect, url_for, flash, send_file
from app import db
from app.models import StockData, Stockist
from datetime import datetime
from flask import render_template, make_response, request
from fpdf import FPDF
from flask import send_file
import io
from sqlalchemy import func


bp = Blueprint('stockdata', __name__, url_prefix='/stockdata')

def get_filter_choices():
    # For dropdowns: list of all stockist names, warehouses
    stockist_names = [s[0] for s in db.session.query(StockData.stockist_name).distinct().all()]
    warehouses = [w[0] for w in db.session.query(StockData.warehouse).distinct().all()]
    return stockist_names, warehouses

@bp.route('/list', methods=['GET'])
def display_stock_data():
    def _parse_date(val: str | None):
        if not val:
            return None
        try:
            return datetime.strptime(val, "%Y-%m-%d").date()
        except Exception:
            return None

    query = StockData.query

    # Filters from query string
    start_date_s = request.args.get('start_date')
    end_date_s = request.args.get('end_date')
    stockist_name = request.args.get('stockist_name')
    warehouse = request.args.get('warehouse')
    commodity = request.args.get('commodity')
    quality = request.args.get('quality')
    kind_of_stock = request.args.get('kind_of_stock')

    # Parse dates safely
    start_date = _parse_date(start_date_s)
    end_date = _parse_date(end_date_s)

    # Apply filters
    if start_date and end_date:
        query = query.filter(StockData.date.between(start_date, end_date))
    elif start_date:
        query = query.filter(StockData.date >= start_date)
    elif end_date:
        query = query.filter(StockData.date <= end_date)

    if stockist_name:
        query = query.filter(StockData.stockist_name == stockist_name)
    if warehouse:
        query = query.filter(StockData.warehouse == warehouse)
    if commodity:
        query = query.filter(StockData.commodity == commodity)
    if quality:
        query = query.filter(StockData.quality == quality)
    if kind_of_stock:
        query = query.filter(StockData.kind_of_stock == kind_of_stock)

    # --- NEW: aggregated totals on the filtered set ---
    totals = query.with_entities(
        func.coalesce(func.sum(StockData.quantity), 0.0),
        func.coalesce(func.sum(StockData.net_qty), 0.0),
        func.count(StockData.id)
    ).first()
    total_quantity, total_net_qty, row_count = (totals or (0.0, 0.0, 0))

    stocks = query.order_by(StockData.date.desc()).all()
    stockist_names, warehouses = get_filter_choices()

    return render_template(
        "stockist/list_stock_data.html",
        stocks=stocks,
        stockist_names=stockist_names,
        warehouses=warehouses,
        total_quantity=total_quantity,
        total_net_qty=total_net_qty,
        row_count=row_count
    )
@bp.route('/add', methods=['GET', 'POST'])
def add_stock_data():
    stockists = Stockist.query.all()
    if request.method == 'POST':
        form = request.form
        try:
            quantity = float(form['quantity'])
            reduction = float(form['reduction'])
            rate = float(form['rate'])
            handling = float(form['handling'])
        except Exception:
            flash("Please enter valid numeric values.", "danger")
            return redirect(request.url)

        net_qty = quantity - reduction
        cost = net_qty * rate
        net_cost = cost - handling

        stock = StockData(
            date=datetime.strptime(form['date'], "%Y-%m-%d").date(),
            rst_no=form['rst_no'],
            warehouse=form['warehouse'],
            stockist_name=form['stockist_name'],
            mobile=form['mobile'],
            commodity=form['commodity'],
            quantity=quantity,
            reduction=reduction,
            net_qty=net_qty,
            rate=rate,
            cost=cost,
            handling=handling,
            net_cost=net_cost,
            quality=form['quality'],
            kind_of_stock="self"  # Always self for manual entry or Excel upload
        )
        db.session.add(stock)
        db.session.commit()
        flash("Stock data added successfully!", "success")
        return redirect(url_for('stockdata.display_stock_data'))
    return render_template('stockist/add_stock_data.html', stockists=stockists)

@bp.route('/edit/<int:stockdata_id>', methods=['GET', 'POST'])
def edit_stock_data(stockdata_id):
    stock = StockData.query.get_or_404(stockdata_id)
    if request.method == 'POST':
        form = request.form
        try:
            stock.date = datetime.strptime(form['date'], "%Y-%m-%d").date()
            stock.rst_no = form['rst_no']
            stock.warehouse = form['warehouse']
            stock.stockist_name = form['stockist_name']
            stock.mobile = form['mobile']
            stock.commodity = form['commodity']
            stock.quantity = float(form['quantity'])
            stock.reduction = float(form['reduction'])
            stock.net_qty = stock.quantity - stock.reduction
            stock.rate = float(form['rate'])
            stock.cost = stock.net_qty * stock.rate
            stock.handling = float(form['handling'])
            stock.net_cost = stock.cost - stock.handling
            stock.quality = form['quality']
            # Do NOT allow admin to edit kind_of_stock from the form!
            db.session.commit()
            flash("Stock data updated!", "success")
        except Exception:
            db.session.rollback()
            flash("Please enter valid numeric values.", "danger")
        return redirect(url_for('stockdata.display_stock_data'))
    stockists = Stockist.query.all()
    return render_template('stockist/edit_stock_data.html', stock=stock, stockists=stockists)

@bp.route('/delete/<int:stockdata_id>', methods=['POST'])
def delete_stock_data(stockdata_id):
    stock = StockData.query.get_or_404(stockdata_id)
    db.session.delete(stock)
    db.session.commit()
    flash("Stock data deleted.", "success")
    return redirect(url_for('stockdata.display_stock_data'))

# -------- Export to Excel ---------
@bp.route('/export_excel')
def export_stockdata_excel():
    stocks = StockData.query.all()
    data = [{
        'Date': s.date.strftime('%Y-%m-%d') if s.date else '',
        'RST No': s.rst_no,
        'Warehouse': s.warehouse,
        'Stockist Name': s.stockist_name,
        'Mobile': s.mobile,
        'Commodity': s.commodity,
        'Quantity': s.quantity,
        'Reduction': s.reduction,
        'Net Qty': s.net_qty,
        'Rate': s.rate,
        'Cost': s.cost,
        'Handling': s.handling,
        'Net Cost': s.net_cost,
        'Quality': s.quality,
        'Kind of Stock': s.kind_of_stock
    } for s in stocks]
    df = pd.DataFrame(data)
    output = io.BytesIO()
    df.to_excel(output, index=False)
    output.seek(0)
    return send_file(
        output,
        mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        download_name='stock_data.xlsx',
        as_attachment=True
    )

# -------- Import from Excel ---------
@bp.route('/import_excel', methods=['POST'])
def import_stockdata_excel():
    file = request.files['file']
    df = pd.read_excel(file)
    for _, row in df.iterrows():
        stock = StockData(
            date=pd.to_datetime(row['Date']).date(),
            rst_no=row['RST No'],
            warehouse=row['Warehouse'],
            stockist_name=row['Stockist Name'],
            mobile=row['Mobile'],
            commodity=row['Commodity'],
            quantity=float(row['Quantity']),
            reduction=float(row['Reduction']),
            net_qty=float(row['Net Qty']),
            rate=float(row['Rate']),
            cost=float(row['Cost']),
            handling=float(row['Handling']),
            net_cost=float(row['Net Cost']),
            quality=row['Quality'],
            kind_of_stock=row.get('Kind of Stock', 'self') if str(row.get('Kind of Stock', '')).lower() in ['self', 'transferred'] else 'self'
        )
        db.session.add(stock)
    db.session.commit()
    flash("Stock data imported from Excel!", "success")
    return redirect(url_for('stockdata.display_stock_data'))

@bp.route('/export_stockdata_pdf', methods=['GET'])
def export_stockdata_pdf():
    stocks = StockData.query.order_by(StockData.date.desc()).all()

    pdf = FPDF(orientation='L', unit='mm', format='A4')
    pdf.add_page()
    pdf.set_font('Arial', 'B', 9)

    # Adjust these widths to fit all 15 columns in A4 landscape (approx 277mm width)
    col_widths = [
        18,   # Date
        13,   # RST No
        28,   # Warehouse
        32,   # Stockist Name
        20,   # Mobile
        17,   # Commodity
        16,   # Quantity
        16,   # Reduction
        16,   # Net Qty
        14,   # Rate
        18,   # Cost
        16,   # Handling
        20,   # Net Cost
        14,   # Quality
        21    # Kind of Stock
    ]
    headers = [
        'Date', 'RST No', 'Warehouse', 'Stockist Name', 'Mobile', 'Commodity',
        'Quantity', 'Reduction', 'Net Qty', 'Rate', 'Cost', 'Handling', 'Net Cost', 'Quality', 'Kind of Stock'
    ]

    # Header row
    for i, header in enumerate(headers):
        pdf.cell(col_widths[i], 7, header, border=1, align='C')
    pdf.ln()

    pdf.set_font('Arial', '', 8)
    for s in stocks:
        values = [
            str(s.date or ""),
            str(s.rst_no or ""),
            str(s.warehouse or "")[:20],  # truncate to 20 chars
            str(s.stockist_name or "")[:16],  # truncate to 22 chars
            str(s.mobile or ""),
            str(s.commodity or ""),
            str(s.quantity if s.quantity is not None else ""),
            str(s.reduction if s.reduction is not None else ""),
            str(s.net_qty if s.net_qty is not None else ""),
            str(s.rate if s.rate is not None else ""),
            str(s.cost if s.cost is not None else ""),
            str(s.handling if s.handling is not None else ""),
            str(s.net_cost if s.net_cost is not None else ""),
            str(s.quality or ""),
            str(s.kind_of_stock or "")
        ]
        for i, v in enumerate(values):
            pdf.cell(col_widths[i], 7, v, border=1)
        pdf.ln()

    # Output
    output = io.BytesIO()
    pdf.output(output)
    output.seek(0)
    return send_file(output, as_attachment=True, download_name='stockdata.pdf', mimetype='application/pdf')
