from flask import Blueprint, render_template, request, redirect, url_for, flash
from datetime import datetime
from app import db
from app.models import MarginData, Stockist

bp = Blueprint('margindata', __name__, url_prefix='/margindata')

@bp.route('/add', methods=['GET', 'POST'])
def add_margin_data():
    stockists = Stockist.query.all()
    if request.method == 'POST':
        form = request.form
        try:
            amount = float(form['amount'])
            date = datetime.strptime(form['date'], "%Y-%m-%d").date()
        except Exception:
            flash("Please enter valid values.", "danger")
            return redirect(request.url)
        margin = MarginData(
            date=date,
            stockist_name=form['stockist_name'],
            warehouse=form['warehouse'],
            commodity=form['commodity'],
            amount=amount
        )
        db.session.add(margin)
        db.session.commit()
        flash("Margin data added!", "success")
        return redirect(url_for('margindata.list_margin_data'))
    return render_template('stockist/add_margin_data.html', stockists=stockists)

@bp.route('/list')
def list_margin_data():
    margins = MarginData.query.order_by(MarginData.date.desc()).all()
    stockist_names = sorted(set(m.stockist_name for m in margins))
    warehouses = sorted(set(m.warehouse for m in margins))
    commodities = sorted(set(m.commodity for m in margins))
    return render_template(
        'stockist/list_margin_data.html',
        margins=margins,
        stockist_names=stockist_names,
        warehouses=warehouses,
        commodities=commodities
    )

@bp.route('/edit/<int:margin_id>', methods=['GET', 'POST'])
def edit_margin_data(margin_id):
    margin = MarginData.query.get_or_404(margin_id)
    if request.method == 'POST':
        try:
            margin.date = datetime.strptime(request.form['date'], "%Y-%m-%d").date()
        except Exception:
            flash("Please enter a valid date.", "danger")
            return redirect(request.url)
        margin.stockist_name = request.form['stockist_name']
        margin.warehouse = request.form['warehouse']
        margin.commodity = request.form['commodity']
        try:
            margin.amount = float(request.form['amount'])
        except Exception:
            flash("Please enter a valid amount.", "danger")
            return redirect(request.url)
        db.session.commit()
        flash("Margin data updated!", "success")
        return redirect(url_for('margindata.list_margin_data'))
    return render_template('stockist/edit_margin_data.html', margin=margin)

@bp.route('/delete/<int:margin_id>', methods=['POST'])
def delete_margin_data(margin_id):
    margin = MarginData.query.get_or_404(margin_id)
    db.session.delete(margin)
    db.session.commit()
    flash("Margin data deleted!", "success")
    return redirect(url_for('margindata.list_margin_data'))
