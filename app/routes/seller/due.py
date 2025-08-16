from flask import Blueprint, render_template, request
from app.models import Purchase, Payment
from app import db

bp = Blueprint('payment_due', __name__, url_prefix='/payment_due')

@bp.route('/', methods=['GET', 'POST'])
def payment_due():
    result = None
    sellers = [s[0] for s in db.session.query(Purchase.seller_name).distinct()]
    warehouses = [w[0] for w in db.session.query(Purchase.warehouse).distinct()]
    commodities = [c[0] for c in db.session.query(Purchase.commodity).distinct()]

    rows = []
    if request.method == 'POST':
        seller = request.form.get('seller_name')
        warehouse = request.form.get('warehouse')
        commodity = request.form.get('commodity')

        # Get net amount and amount paid for this combination
        net_amount = db.session.query(db.func.sum(Purchase.net_cost)).filter_by(
            seller_name=seller, warehouse=warehouse, commodity=commodity).scalar() or 0

        amount_paid = db.session.query(db.func.sum(Payment.amount_paid)).filter_by(
            seller_name=seller, warehouse=warehouse, commodity=commodity).scalar() or 0

        payment_due = net_amount - amount_paid
        rows.append({
            'seller_name': seller,
            'warehouse': warehouse,
            'commodity': commodity,
            'net_amount': net_amount,
            'amount_paid': amount_paid,
            'payment_due': payment_due
        })

    return render_template('seller/payment_due.html',
                           sellers=sellers, warehouses=warehouses, commodities=commodities, rows=rows)
