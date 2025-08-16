# app/routes/stockist/stockist.py
from flask import Blueprint, render_template, request, redirect, url_for, flash
from app import db
from app.models import Stockist

bp = Blueprint('stockist', __name__, url_prefix='/stockist')

@bp.route('/add', methods=['GET', 'POST'])
def add_stockist():
    if request.method == 'POST':
        name = request.form['name']
        mobile = request.form['mobile']
        address = request.form['address']
        banking_name = request.form['banking_name']
        account_number = request.form['account_number']
        ifsc_code = request.form['ifsc_code']
        bank_name = request.form['bank_name']

        stockist = Stockist(
            name=name,
            mobile=mobile,
            address=address,
            banking_name=banking_name,
            account_number=account_number,
            ifsc_code=ifsc_code,
            bank_name=bank_name
        )
        db.session.add(stockist)
        try:
            db.session.commit()
            flash("Stockist added successfully!", "success")
        except Exception as e:
            db.session.rollback()
            flash(f"Error: {str(e)}", "danger")
        return redirect(url_for('stockist.list_stockists'))
    return render_template('stockist/add_stockist.html')

@bp.route('/edit/<int:stockist_id>', methods=['GET', 'POST'])
def edit_stockist(stockist_id):
    stockist = Stockist.query.get_or_404(stockist_id)
    if request.method == 'POST':
        stockist.name = request.form['name']
        stockist.mobile = request.form['mobile']
        stockist.address = request.form['address']
        stockist.banking_name = request.form['banking_name']
        stockist.account_number = request.form['account_number']
        stockist.ifsc_code = request.form['ifsc_code']
        stockist.bank_name = request.form['bank_name']
        try:
            db.session.commit()
            flash("Stockist updated successfully!", "success")
        except Exception as e:
            db.session.rollback()
            flash(f"Error: {str(e)}", "danger")
        return redirect(url_for('stockist.list_stockists'))
    return render_template('stockist/edit_stockist.html', stockist=stockist)

@bp.route('/delete/<int:stockist_id>', methods=['POST'])
def delete_stockist(stockist_id):
    stockist = Stockist.query.get_or_404(stockist_id)
    db.session.delete(stockist)
    db.session.commit()
    flash("Stockist deleted.", "success")
    return redirect(url_for('stockist.list_stockists'))

@bp.route('/list')
def list_stockists():
    stockists = Stockist.query.all()
    return render_template('stockist/list_stockist.html', stockists=stockists)
