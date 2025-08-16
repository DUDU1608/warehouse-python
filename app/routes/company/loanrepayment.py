from flask import Blueprint, render_template, request, redirect, url_for, flash
from datetime import datetime
from app import db
from app.models import LoanRepayment

bp = Blueprint('loanrepayment', __name__, url_prefix='/company')

@bp.route('/add-loan-repayment', methods=['GET', 'POST'])
def add_loan_repayment():
    if request.method == 'POST':
        try:
            date = datetime.strptime(request.form['date'], '%Y-%m-%d').date()
            amount = float(request.form['amount'])
            interest_rate = float(request.form['interest_rate'])
            repayment = LoanRepayment(
                date=date,
                amount=amount,
                interest_rate=interest_rate
            )
            db.session.add(repayment)
            db.session.commit()
            flash('Loan repayment added!', 'success')
            return redirect(url_for('loanrepayment.list_loan_repayment'))
        except Exception as e:
            flash(f"Error: {e}", "danger")
    return render_template('company/add_loan_repayment.html')

@bp.route('/list-loan-repayment')
def list_loan_repayment():
    repayments = LoanRepayment.query.order_by(LoanRepayment.date.desc()).all()
    return render_template('company/list_loan_repayment.html', repayments=repayments)

@bp.route('/edit-loan-repayment/<int:repayment_id>', methods=['GET', 'POST'])
def edit_loan_repayment(repayment_id):
    repayment = LoanRepayment.query.get_or_404(repayment_id)
    if request.method == 'POST':
        form = request.form
        repayment.date = datetime.strptime(form['date'], "%Y-%m-%d").date()
        repayment.amount = float(form['amount'])
        repayment.interest_rate = float(form['interest_rate'])
        db.session.commit()
        flash("Loan repayment updated!", "success")
        return redirect(url_for('loanrepayment.list_loan_repayment'))
    return render_template('company/edit_loan_repayment.html', repayment=repayment)

@bp.route('/delete-loan-repayment/<int:repayment_id>', methods=['POST'])
def delete_loan_repayment(repayment_id):
    repayment = LoanRepayment.query.get_or_404(repayment_id)
    db.session.delete(repayment)
    db.session.commit()
    flash("Loan repayment deleted!", "success")
    return redirect(url_for('loanrepayment.list_loan_repayment'))
