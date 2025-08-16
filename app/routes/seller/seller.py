from flask import Blueprint, render_template, request, redirect, url_for, flash
from app import db
from app.models import Seller

bp = Blueprint('seller', __name__, url_prefix='/seller')

@bp.route('/add', methods=['GET', 'POST'])
def add_seller():
    if request.method == 'POST':
        name = request.form['name']
        mobile = request.form['mobile']
        address = request.form['address']
        banking_name = request.form['banking_name']
        account_number = request.form['account_number']
        ifsc_code = request.form['ifsc_code']
        bank_name = request.form['bank_name']

        new_seller = Seller(
            name=name,
            mobile=mobile,
            address=address,
            banking_name=banking_name,
            account_number=account_number,
            ifsc_code=ifsc_code,
            bank_name=bank_name
        )
        db.session.add(new_seller)
        db.session.commit()
        flash('Seller added successfully!')
        return redirect(url_for('seller.list_sellers'))

    return render_template('seller/add_seller.html')


@bp.route('/list')
def list_sellers():
    sellers = Seller.query.all()
    return render_template('seller/list_sellers.html', sellers=sellers)

@bp.route('/update-inline/<int:seller_id>', methods=['POST'])
def update_seller_inline(seller_id):
    seller = Seller.query.get_or_404(seller_id)
    seller.name = request.form['name']
    seller.mobile = request.form['mobile']
    seller.address = request.form['address']
    seller.banking_name = request.form['banking_name']
    seller.account_number = request.form['account_number']
    seller.ifsc_code = request.form['ifsc_code']
    seller.bank_name = request.form['bank_name']
    db.session.commit()
    return redirect(url_for('seller.list_sellers'))

@bp.route('/delete/<int:seller_id>', methods=['GET'])
def delete_seller(seller_id):
    seller = Seller.query.get_or_404(seller_id)
    db.session.delete(seller)
    db.session.commit()
    return redirect(url_for('seller.list_sellers'))  # ✅ Ensure function name matches your route
