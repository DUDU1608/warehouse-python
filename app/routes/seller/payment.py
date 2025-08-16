from flask import Blueprint, render_template, request, redirect, url_for, flash
from app import db
from app.models import Payment, Seller
from datetime import datetime
from flask import send_file
import pandas as pd
import io

bp = Blueprint('payment', __name__, url_prefix='/payment')

@bp.route('/add', methods=['GET', 'POST'])
def add_payment():
    # Always build a list of dicts, never pass SQLAlchemy objects directly to template!
    sellers = [
        {
            "name": getattr(s, 'name', '') or '',
            "banking_name": getattr(s, 'banking_name', '') or '',
            "account_number": getattr(s, 'account_number', '') or '',
            "ifsc_code": getattr(s, 'ifsc_code', '') or ''
        }
        for s in Seller.query.all()
    ]

    if request.method == 'POST':
        form = request.form
        date_obj = datetime.strptime(form['date'], "%Y-%m-%d").date()
        payment = Payment(
            date=date_obj,
            seller_name=form['seller_name'],
            warehouse=form['warehouse'],
            commodity=form['commodity'],
            banking_name=form['banking_name'],
            account_number=form['account_number'],
            ifsc=form['ifsc'],
            amount_paid=float(form['amount_paid']),
            bank_reference=form['bank_reference']
        )
        db.session.add(payment)
        db.session.commit()
        flash("Payment added successfully!")
        return redirect(url_for('payment.list_payments'))

    print("SELLERS FOR TEMPLATE", sellers)
    return render_template('seller/add_payment.html', sellers=sellers)

@bp.route('/list', methods=['GET'])
def list_payments():
    query = Payment.query

    # Filters
    start_date = request.args.get('start_date')
    end_date = request.args.get('end_date')
    seller = request.args.get('seller_name')
    warehouse = request.args.get('warehouse')
    commodity = request.args.get('commodity')

    if start_date and end_date:
        query = query.filter(Payment.date.between(start_date, end_date))
    if seller:
        query = query.filter(Payment.seller_name == seller)
    if warehouse:
        query = query.filter(Payment.warehouse == warehouse)
    if commodity:
        query = query.filter(Payment.commodity == commodity)

    payments = query.order_by(Payment.date.desc()).all()

    # For dropdowns
    sellers = db.session.query(Payment.seller_name).distinct().all()
    warehouses = db.session.query(Payment.warehouse).distinct().all()
    commodities = db.session.query(Payment.commodity).distinct().all()

    return render_template(
        'seller/list_payment.html',
        payments=payments,
        sellers=[s[0] for s in sellers],
        warehouses=[w[0] for w in warehouses],
        commodities=[c[0] for c in commodities]
    )

from datetime import datetime

@bp.route('/edit/<int:payment_id>', methods=['GET', 'POST'])
def edit_payment(payment_id):
    payment = Payment.query.get_or_404(payment_id)

    if request.method == 'POST':
        form = request.form
        payment.date = datetime.strptime(form['date'], "%Y-%m-%d").date()
        payment.seller_name = form['seller_name']
        payment.warehouse = form['warehouse']
        payment.commodity = form['commodity']
        payment.banking_name = form['banking_name']
        payment.account_number = form['account_number']
        payment.ifsc = form['ifsc']
        payment.amount_paid = float(form['amount_paid'])
        payment.bank_reference = form['bank_reference']
        db.session.commit()
        flash("Payment updated successfully!")
        return redirect(url_for('payment.list_payments'))

    return render_template('seller/edit_payment.html', payment=payment)

@bp.route('/delete-payment/<int:payment_id>', methods=['POST'])
def delete_payment(payment_id):
    payment = Payment.query.get_or_404(payment_id)
    db.session.delete(payment)
    db.session.commit()
    return redirect(url_for('payment.list_payments'))

@bp.route('/export-payments-excel', methods=['GET'])
def export_payments_excel():
    payments = Payment.query.order_by(Payment.date.desc()).all()
    data = [{
        'Date': p.date.strftime('%Y-%m-%d') if p.date else '',
        'Seller Name': p.seller_name,
        'Warehouse': p.warehouse,
        'Commodity': p.commodity,
        'Banking Name': p.banking_name,
        'Account Number': p.account_number,
        'IFSC': p.ifsc,
        'Amount Paid': p.amount_paid,
        'Bank Reference': p.bank_reference
    } for p in payments]
    df = pd.DataFrame(data)
    output = io.BytesIO()
    df.to_excel(output, index=False)
    output.seek(0)
    return send_file(output, mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
                     download_name='payment_data.xlsx', as_attachment=True)

