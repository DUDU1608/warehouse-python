from flask import Blueprint, render_template, request, redirect, url_for, flash
from datetime import datetime
from app.models import Expenditure
from app import db

bp = Blueprint('expenditure', __name__, url_prefix='/company')

@bp.route('/add-expenditure', methods=['GET', 'POST'])
def add_expenditure():
    if request.method == 'POST':
        date = datetime.strptime(request.form['date'], '%Y-%m-%d').date()
        expenditure_type = request.form['expenditure_type']
        amount = float(request.form['amount'])
        comments = request.form.get('comments', '') if expenditure_type == 'Others' else ''
        exp = Expenditure(date=date, expenditure_type=expenditure_type, amount=amount, comments=comments)
        db.session.add(exp)
        db.session.commit()
        flash("Expenditure added successfully!", "success")
        return redirect(url_for('expenditure.list_expenditure'))
    return render_template('company/add_expenditure.html')

@bp.route('/list-expenditure')
def list_expenditure():
    expenditures = Expenditure.query.order_by(Expenditure.date.desc()).all()
    total_expenditure = sum(exp.amount for exp in expenditures)
    return render_template(
        'company/list_expenditure.html',
        expenditures=expenditures,
        total_expenditure=round(total_expenditure, 2))

@bp.route('/delete-expenditure/<int:expenditure_id>', methods=['POST'])
def delete_expenditure(expenditure_id):
    exp = Expenditure.query.get_or_404(expenditure_id)
    db.session.delete(exp)
    db.session.commit()
    flash("Expenditure deleted.", "success")
    return redirect(url_for('expenditure.list_expenditure'))

@bp.route('/edit-expenditure/<int:expenditure_id>', methods=['GET', 'POST'])
def edit_expenditure(expenditure_id):
    exp = Expenditure.query.get_or_404(expenditure_id)
    if request.method == 'POST':
        form = request.form
        exp.date = datetime.strptime(form['date'], "%Y-%m-%d").date()
        exp.expenditure_type = form['expenditure_type']
        exp.comments = form.get('comments', '')
        exp.amount = float(form['amount'])
        db.session.commit()
        flash("Expenditure updated.", "success")
        return redirect(url_for('expenditure.list_expenditure'))
    return render_template('company/edit_expenditure.html', exp=exp)

