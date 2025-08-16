import io
from sqlite3 import IntegrityError

import pandas as pd
from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify, send_file
from app import db
from app.models import Purchase, Seller

bp = Blueprint('purchase', __name__, url_prefix='/purchase')

@bp.route('/add', methods=['GET', 'POST'])
def add_purchase():
    """Add a new purchase entry."""
    sellers = Seller.query.all()

    if request.method == 'POST':
        form = request.form
        quantity = float(form['quantity'])
        reduction = float(form['reduction'])
        rate = float(form['rate'])
        handling = float(form['handling'])

        net_qty = quantity - reduction
        cost = net_qty * rate
        net_cost = cost - handling

        purchase = Purchase(
            date=form['date'],
            rst_no=form['rst_no'],
            warehouse=form['warehouse'],
            seller_name=form['seller_name'],
            mobile=form['mobile'],
            commodity=form['commodity'],
            quantity=quantity,
            reduction=reduction,
            net_qty=net_qty,
            rate=rate,
            cost=cost,
            handling=handling,
            net_cost=net_cost,
            quality=form['quality']
        )

        try:
            db.session.commit()
            flash("Purchase added successfully.")
            return redirect(url_for('purchase.display_purchase'))
        except IntegrityError:
            db.session.rollback()
            flash("This RST No and Warehouse combination already exists!", "danger")
            return redirect(request.url)

    from datetime import datetime
    return render_template('seller/add_purchase.html', sellers=sellers, datetime=datetime)

@bp.route('/list')
def display_purchase():
    """Show all purchases without filters."""
    purchases = Purchase.query.order_by(Purchase.date.desc()).all()
    return render_template('seller/list_purchase.html', purchases=purchases)

from datetime import datetime

@bp.route('/purchases', methods=['GET'])
def list_purchases():
    """Show purchases with filters for dashboard view."""
    query = Purchase.query

    # Fetch filter values from query parameters
    start_date = request.args.get('start_date')
    end_date = request.args.get('end_date')
    seller = request.args.get('seller')
    warehouse = request.args.get('warehouse')
    commodity = request.args.get('commodity')
    quality = request.args.get('quality')

    if start_date and end_date:
        query = query.filter(Purchase.date.between(start_date, end_date))
    if seller:
        query = query.filter(Purchase.seller_name == seller)
    if warehouse:
        query = query.filter(Purchase.warehouse == warehouse)
    if commodity:
        query = query.filter(Purchase.commodity == commodity)
    if quality:
        query = query.filter(Purchase.quality == quality)

    purchases = query.order_by(Purchase.date.desc()).all()

    # --- THE CRITICAL DATE NORMALIZATION FIX! ---
    for p in purchases:
        if hasattr(p.date, "strftime"):
            p.date_str = p.date.strftime("%Y-%m-%d")
        elif isinstance(p.date, str):
            try:
                # Already YYYY-MM-DD
                datetime.strptime(p.date, "%Y-%m-%d")
                p.date_str = p.date
            except ValueError:
                try:
                    # Try DD/MM/YYYY
                    d = datetime.strptime(p.date, "%d/%m/%Y")
                    p.date_str = d.strftime("%Y-%m-%d")
                except Exception:
                    p.date_str = ""
        else:
            p.date_str = ""

    # Needed for filter dropdowns
    sellers = db.session.query(Purchase.seller_name).distinct().all()
    warehouses = db.session.query(Purchase.warehouse).distinct().all()

    return render_template(
        "seller/list_purchase.html",
        purchases=purchases,
        sellers=[s[0] for s in sellers],
        warehouses=[w[0] for w in warehouses]
    )

@bp.route('/edit/<int:purchase_id>', methods=['GET', 'POST'])
def edit_purchase(purchase_id):
    purchase = Purchase.query.get_or_404(purchase_id)

    def parse_float(value, default=0.0):
        try:
            return float(value)
        except (ValueError, TypeError):
            return default

    if request.method == 'POST':
        purchase.date = request.form['date']
        purchase.rst_no = request.form['rst_no']
        purchase.warehouse = request.form['warehouse']
        purchase.seller_name = request.form['seller_name']
        purchase.mobile = request.form['mobile']
        purchase.commodity = request.form['commodity']
        purchase.quantity = parse_float(request.form.get('quantity'))
        purchase.reduction = parse_float(request.form.get('reduction'))
        purchase.rate = parse_float(request.form.get('rate'))
        purchase.handling = parse_float(request.form.get('handling'))
        purchase.quality = request.form['quality']

        # Calculated fields
        purchase.net_qty = purchase.quantity - purchase.reduction
        purchase.cost = purchase.net_qty * purchase.rate
        purchase.net_cost = purchase.cost - purchase.handling

        try:
            db.session.commit()
            flash("Purchase added successfully.")
            return redirect(url_for('purchase.display_purchase'))
        except IntegrityError:
            db.session.rollback()
            flash("This RST No and Warehouse combination already exists!", "danger")
            return redirect(request.url)

    return render_template('seller/edit_purchase.html', purchase=purchase)


@bp.route('/delete-purchase/<int:purchase_id>', methods=['POST'])
def delete_purchase(purchase_id):
    """Delete a purchase record."""
    purchase = Purchase.query.get_or_404(purchase_id)
    db.session.delete(purchase)
    db.session.commit()
    return jsonify({'success': True})

@bp.route('/export-purchases-excel', methods=['GET'])
def export_purchases_excel():
    """Export all purchases to Excel."""
    purchases = Purchase.query.all()
    data = [{
        'Date': p.date,
        'RST No': p.rst_no,
        'Warehouse': p.warehouse,
        'Seller Name': p.seller_name,
        'Mobile': p.mobile,
        'Commodity': p.commodity,
        'Quantity': p.quantity,
        'Reduction': p.reduction,
        'Net Qty': p.net_qty,
        'Rate': p.rate,
        'Cost': p.cost,
        'Handling': p.handling,
        'Net Cost': p.net_cost,
        'Quality': p.quality
    } for p in purchases]

    df = pd.DataFrame(data)
    output = io.BytesIO()
    df.to_excel(output, index=False)
    output.seek(0)
    return send_file(output, mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
                     download_name='purchase_data.xlsx', as_attachment=True)

import math

@bp.route('/import-purchases-excel', methods=['POST'])
def import_purchases_excel():
    file = request.files['file']
    df = pd.read_excel(file)

    for _, row in df.iterrows():
        # Convert Timestamp to str (or .date())
        date_value = row['Date']
        if hasattr(date_value, 'strftime'):
            date_value = date_value.strftime('%Y-%m-%d')  # or .date() if you want

        # Handle missing mobile or other text fields
        mobile_value = row['Mobile']
        if (pd.isna(mobile_value)) or (type(mobile_value) is float and math.isnan(mobile_value)):
            mobile_value = ''

        quality_value = str(row['Quality']).title()  # "GOOD" → "Good"

        purchase = Purchase(
            date=date_value,
            rst_no=row['RST No'],
            warehouse=row['Warehouse'],
            seller_name=row['Seller Name'],
            mobile=mobile_value,
            commodity=row['Commodity'],
            quantity=row['Quantity'],
            reduction=row['Reduction'],
            net_qty=row['Net Qty'],
            rate=row['Rate'],
            cost=row['Cost'],
            handling=row['Handling'],
            net_cost=row['Net Cost'],
            quality=quality_value
        )
        db.session.add(purchase)

    db.session.commit()
    return redirect(url_for('purchase.list_purchases'))

@bp.route('/transfer-purchases', methods=['POST'])
def transfer_purchases():
    """Placeholder for future transfer logic."""
    return jsonify({'message': 'Transfer logic not yet implemented'})
