import io
from flask import Blueprint, render_template, request, redirect, url_for, flash, send_file, jsonify
from app import db
from app.models import StockExit, Stockist  # Adjust import if path is different
from datetime import datetime
import pandas as pd

bp = Blueprint('stockexit', __name__, url_prefix='/stockexit')

# Add Stock Exit
@bp.route('/add', methods=['GET', 'POST'])
def add_stock_exit():
    # Query all stockists and convert to dicts for JSON serialization
    stockists_query = Stockist.query.all()
    stockists = [{"name": s.name, "mobile": s.mobile} for s in stockists_query]

    if request.method == 'POST':
        form = request.form
        try:
            quantity = float(form['quantity'])
            reduction = float(form['reduction'])
            rate = float(form['rate'])
            handling = float(form['handling'])
        except Exception:
            flash("Enter valid numeric values.", "danger")
            return redirect(request.url)
        net_qty = quantity - reduction
        cost = net_qty * rate
        net_cost = cost - handling
        stock_exit = StockExit(
            date=datetime.strptime(form['date'], "%Y-%m-%d").date(),
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
        )
        db.session.add(stock_exit)
        db.session.commit()
        flash("Stock Exit data added!", "success")
        return redirect(url_for('stockexit.list_stock_exit'))
    return render_template('stockist/add_stock_exit.html', stockists=stockists)

# List + Filter + Export
@bp.route('/list', methods=['GET', 'POST'])
def list_stock_exit():
    query = StockExit.query

    start_date = request.args.get('start_date')
    end_date = request.args.get('end_date')
    stockist_name = request.args.get('stockist_name')
    warehouse = request.args.get('warehouse')
    commodity = request.args.get('commodity')
    quality = request.args.get('quality')

    if start_date and end_date:
        query = query.filter(StockExit.date.between(start_date, end_date))
    if stockist_name:
        query = query.filter(StockExit.stockist_name == stockist_name)
    if warehouse:
        query = query.filter(StockExit.warehouse == warehouse)
    if commodity:
        query = query.filter(StockExit.commodity == commodity)
    if quality:
        query = query.filter(StockExit.quality == quality)

    stockexits = query.order_by(StockExit.date.desc()).all()
    stockist_names = [s[0] for s in db.session.query(StockExit.stockist_name).distinct()]
    warehouses = [w[0] for w in db.session.query(StockExit.warehouse).distinct()]
    return render_template('stockist/list_stock_exit.html',
        stockexits=stockexits,
        stockist_names=stockist_names,
        warehouses=warehouses
    )

# Export Excel
@bp.route('/export_excel')
def export_stock_exit_excel():
    stockexits = StockExit.query.all()
    data = [{
        'Date': s.date.strftime('%Y-%m-%d') if s.date else '',
        'Warehouse': s.warehouse,
        'Stockist Name': s.stockist_name,
        'Mobile': s.mobile,
        'Commodity': s.commodity,
        'Quantity': s.quantity,
        'Reduction': s.reduction,
        'NetQty': s.net_qty,
        'Rate': s.rate,
        'Cost': s.cost,
        'Handling': s.handling,
        'Net Cost': s.net_cost,
        'Quality': s.quality
    } for s in stockexits]
    df = pd.DataFrame(data)
    output = io.BytesIO()
    df.to_excel(output, index=False)
    output.seek(0)
    return send_file(output, mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet', download_name='stock_exit.xlsx', as_attachment=True)

# Export PDF (renders the same HTML as list)
# Edit
@bp.route('/edit/<int:stockexit_id>', methods=['GET', 'POST'])
def edit_stock_exit(stockexit_id):
    stockexit = StockExit.query.get_or_404(stockexit_id)
    stockists = Stockist.query.all()
    if request.method == 'POST':
        form = request.form
        stockexit.date = datetime.strptime(form['date'], "%Y-%m-%d").date()
        stockexit.warehouse = form['warehouse']
        stockexit.stockist_name = form['stockist_name']
        stockexit.mobile = form['mobile']
        stockexit.commodity = form['commodity']
        stockexit.quantity = float(form['quantity'])
        stockexit.reduction = float(form['reduction'])
        stockexit.net_qty = float(form['net_qty'])
        stockexit.rate = float(form['rate'])
        stockexit.cost = float(form['cost'])
        stockexit.handling = float(form['handling'])
        stockexit.net_cost = float(form['net_cost'])
        stockexit.quality = form['quality']
        db.session.commit()
        flash('Stock Exit updated!', 'success')
        return redirect(url_for('stockexit.list_stock_exit'))
    return render_template('stockist/edit_stock_exit.html', stockexit=stockexit, stockists=stockists)

# Delete
@bp.route('/delete/<int:stockexit_id>', methods=['POST'])
def delete_stock_exit(stockexit_id):
    stockexit = StockExit.query.get_or_404(stockexit_id)
    db.session.delete(stockexit)
    db.session.commit()
    flash("Stock Exit deleted.", "success")
    return redirect(url_for('stockexit.list_stock_exit'))
