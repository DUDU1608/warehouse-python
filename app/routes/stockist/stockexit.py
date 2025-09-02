# app/routes/stockist/stockexit.py

import io
from flask import Blueprint, render_template, request, redirect, url_for, flash, send_file, jsonify
from app import db
from app.models import StockExit, Stockist
from datetime import datetime
import pandas as pd

bp = Blueprint('stockexit', __name__, url_prefix='/stockexit')

# ---------- Utility ----------
def compute_reduction(commodity: str, quantity: float) -> float:
    if not commodity:
        return 0.0
    c = commodity.strip().lower()
    if c == "maize":
        return round((quantity or 0.0) * 0.015, 2)  # 1.5%
    if c == "wheat":
        return 0.0
    return 0.0

# ---------- Add ----------
@bp.route('/add', methods=['GET', 'POST'])
def add_stock_exit():
    stockists_query = Stockist.query.all()
    stockists = [{"name": s.name, "mobile": s.mobile} for s in stockists_query]

    if request.method == 'POST':
        form = request.form
        try:
            date = datetime.strptime(form['date'], "%Y-%m-%d").date()
            rst_no = form.get('rst_no', '').strip()
            warehouse = form['warehouse'].strip()
            stockist_name = form['stockist_name'].strip()
            mobile = form.get('mobile', '').strip()
            commodity = form['commodity'].strip()

            quantity = float(form.get('quantity') or 0)
            # server-side default reduction if blank
            reduction_raw = form.get('reduction', '').strip()
            if reduction_raw == "":
                reduction = compute_reduction(commodity, quantity)
            else:
                reduction = float(reduction_raw)

            rate = float(form.get('rate') or 0)
            handling = float(form.get('handling') or 0)
            actual_qty = float(form.get('actual_qty') or 0)
            rate_diff = float(form.get('rate_of_difference') or 0)
        except Exception:
            flash("Enter valid values for date/text fields and numeric inputs.", "danger")
            return redirect(request.url)

        # Recompute all derived fields server-side
        net_qty = round(quantity - reduction, 2)
        cost = round(net_qty * rate, 2)
        net_cost = round(cost - handling, 2)
        difference = round(net_qty - actual_qty, 2)  # can be +/- 
        diff_amount = round(difference * rate_diff, 2)  # can be +/- 

        stock_exit = StockExit(
            date=date,
            rst_no=rst_no,
            warehouse=warehouse,
            stockist_name=stockist_name,
            mobile=mobile,
            commodity=commodity,
            quantity=quantity,
            reduction=reduction,
            net_qty=net_qty,
            actual_qty=actual_qty,
            difference=difference,
            rate_of_difference=rate_diff,
            differential_amount=diff_amount,
            rate=rate,
            cost=cost,
            handling=handling,
            net_cost=net_cost,
            quality=form.get('quality', None),
        )
        db.session.add(stock_exit)
        db.session.commit()
        flash("Stock Exit data added!", "success")
        return redirect(url_for('stockexit.list_stock_exit'))

    return render_template('stockist/add_stock_exit.html', stockists=stockists)

# ---------- Ajax: total reduction ----------
@bp.route('/total_reduction')
def total_reduction():
    stockist = request.args.get('stockist')
    warehouse = request.args.get('warehouse')
    commodity = request.args.get('commodity')

    q = StockExit.query
    if stockist:
        q = q.filter(StockExit.stockist_name == stockist)
    if warehouse:
        q = q.filter(StockExit.warehouse == warehouse)
    if commodity:
        q = q.filter(StockExit.commodity == commodity)

    total = q.with_entities(db.func.sum(StockExit.reduction)).scalar()
    return jsonify({"total_reduction": "NIL" if total is None else round(float(total), 2)})

# ---------- List ----------
@bp.route('/list')
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
    return render_template(
        'stockist/list_stock_exit.html',
        stockexits=stockexits,
        stockist_names=stockist_names,
        warehouses=warehouses
    )

# ---------- Export Excel ----------
@bp.route('/export_excel')
def export_stock_exit_excel():
    stockexits = StockExit.query.all()
    data = [{
        'Date': s.date.strftime('%Y-%m-%d') if s.date else '',
        'RST No': s.rst_no,
        'Warehouse': s.warehouse,
        'Stockist Name': s.stockist_name,
        'Mobile': s.mobile,
        'Commodity': s.commodity,
        'Quantity': s.quantity,
        'Reduction': s.reduction,
        'NetQty': s.net_qty,
        'Actual Qty': s.actual_qty,
        'Difference': s.difference,
        'Rate of Difference': s.rate_of_difference,
        'Differential Amount': s.differential_amount,
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
    return send_file(
        output,
        mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        download_name='stock_exit.xlsx',
        as_attachment=True
    )

# ---------- Edit ----------
@bp.route('/edit/<int:stockexit_id>', methods=['GET', 'POST'])
def edit_stock_exit(stockexit_id):
    stockexit = StockExit.query.get_or_404(stockexit_id)
    stockists = Stockist.query.all()

    if request.method == 'POST':
        form = request.form
        try:
            stockexit.date = datetime.strptime(form['date'], "%Y-%m-%d").date()
            stockexit.rst_no = form.get('rst_no', '').strip()
            stockexit.warehouse = form['warehouse'].strip()
            stockexit.stockist_name = form['stockist_name'].strip()
            stockexit.mobile = form.get('mobile', '').strip()
            stockexit.commodity = form['commodity'].strip()

            quantity = float(form.get('quantity') or 0)
            # server-side default reduction if blank
            reduction_raw = form.get('reduction', '').strip()
            if reduction_raw == "":
                reduction = compute_reduction(stockexit.commodity, quantity)
            else:
                reduction = float(reduction_raw)

            rate = float(form.get('rate') or 0)
            handling = float(form.get('handling') or 0)
            actual_qty = float(form.get('actual_qty') or 0)
            rate_diff = float(form.get('rate_of_difference') or 0)
        except Exception:
            flash("Enter valid values for date/text fields and numeric inputs.", "danger")
            return redirect(request.url)

        # Recompute all derived fields server-side (do NOT trust client)
        net_qty = round(quantity - reduction, 2)
        cost = round(net_qty * rate, 2)
        net_cost = round(cost - handling, 2)
        difference = round(net_qty - actual_qty, 2)
        diff_amount = round(difference * rate_diff, 2)

        stockexit.quantity = quantity
        stockexit.reduction = reduction
        stockexit.net_qty = net_qty
        stockexit.actual_qty = actual_qty
        stockexit.difference = difference
        stockexit.rate_of_difference = rate_diff
        stockexit.differential_amount = diff_amount
        stockexit.rate = rate
        stockexit.cost = cost
        stockexit.handling = handling
        stockexit.net_cost = net_cost
        stockexit.quality = form.get('quality', None)

        db.session.commit()
        flash("Stock Exit updated!", "success")
        return redirect(url_for('stockexit.list_stock_exit'))

    return render_template('stockist/edit_stock_exit.html', stockexit=stockexit, stockists=stockists)

# ---------- Delete ----------
@bp.route('/delete/<int:stockexit_id>', methods=['POST'])
def delete_stock_exit(stockexit_id):
    stockexit = StockExit.query.get_or_404(stockexit_id)
    db.session.delete(stockexit)
    db.session.commit()
    flash("Stock Exit deleted.", "success")
    return redirect(url_for('stockexit.list_stock_exit'))
