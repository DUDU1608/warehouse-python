from flask import Blueprint, render_template, request, redirect, url_for, flash
from datetime import datetime
from app import db
from app.models import CompanyLoan

bp = Blueprint('companyloan', __name__, url_prefix='/company')

@bp.route('/add-company-loan', methods=['GET', 'POST'])
def add_company_loan():
    if request.method == 'POST':
        try:
            date = datetime.strptime(request.form['date'], '%Y-%m-%d').date()
            loan_amount = float(request.form['loan_amount'])
            processing_fee = float(request.form['processing_fee'])
            gst = float(request.form['gst'])
            interest_rate = float(request.form['interest_rate'])

            total_processing_fee = processing_fee + gst
            total_disbursement = loan_amount - total_processing_fee

            company_loan = CompanyLoan(
                date=date,
                loan_amount=loan_amount,
                processing_fee=processing_fee,
                gst=gst,
                total_processing_fee=total_processing_fee,
                total_disbursement=total_disbursement,
                interest_rate=interest_rate
            )
            db.session.add(company_loan)
            db.session.commit()
            flash('Company Loan added successfully!', 'success')
            return redirect(url_for('companyloan.list_company_loans'))
        except Exception as e:
            flash(f"Error: {e}", "danger")
    return render_template('company/add_company_loan.html')

@bp.route('/display-company-loan')
def list_company_loans():
    loans = CompanyLoan.query.order_by(CompanyLoan.date.desc()).all()
    return render_template('company/list_company_loans.html', loans=loans)

@bp.route('/delete/<int:loan_id>', methods=['POST'])
def delete_company_loan(loan_id):
    loan = CompanyLoan.query.get_or_404(loan_id)
    db.session.delete(loan)
    db.session.commit()
    flash("Loan deleted!", "success")
    return redirect(url_for('companyloan.list_company_loans'))

@bp.route('/edit/<int:loan_id>', methods=['GET', 'POST'])
def edit_company_loan(loan_id):
    loan = CompanyLoan.query.get_or_404(loan_id)
    if request.method == 'POST':
        try:
            loan.date = request.form['date']
            loan.stockist_name = request.form['stockist_name']
            loan.warehouse = request.form['warehouse']
            loan.commodity = request.form['commodity']
            loan.loan_type = request.form['loan_type']
            loan.amount = float(request.form['amount'])
            db.session.commit()
            flash('Loan entry updated successfully!', 'success')
            return redirect(url_for('companyloan.list_company_loans'))
        except Exception as e:
            db.session.rollback()
            flash('Error updating loan data: {}'.format(e), 'danger')
            return redirect(request.url)
    # Render the edit form
    return render_template('company/edit_company_loan.html', loan=loan)

