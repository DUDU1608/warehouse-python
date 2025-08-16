from flask import Blueprint, render_template, request
from app import db
from app.models import CompanyLoan, LoanRepayment
from datetime import datetime


bp = Blueprint('interest_payable', __name__, url_prefix='/company')

@bp.route('/interest-payable', methods=['GET', 'POST'])
def interest_payable():
    total_loan_interest = 0
    total_repay_interest = 0
    final_interest = 0
    processing_fees = 0
    final_interest_payable = 0
    end_date = None

    if request.method == 'POST':
        end_date_str = request.form.get('end_date')
        if not end_date_str:
            return render_template('company/interest_payable.html', error="Please select a date.")

        end_date = datetime.strptime(end_date_str, "%Y-%m-%d").date()

        # 1. Calculate interest for each loan from disbursement date to end_date
        loans = CompanyLoan.query.all()
        for loan in loans:
            days = (end_date - loan.date).days
            if days > 0:
                interest = (loan.loan_amount * (loan.interest_rate/100) * days) / 365
                total_loan_interest += interest

        # 2. Subtract interest for repayments
        repayments = LoanRepayment.query.all()
        for rep in repayments:
            days = (end_date - rep.date).days
            if days > 0:
                interest = (rep.amount * (rep.interest_rate/100) * days) / 365
                total_repay_interest += interest

        final_interest = total_loan_interest - total_repay_interest

        # 3. Add all processing fees
        processing_fees = db.session.query(db.func.sum(CompanyLoan.total_processing_fee)).scalar() or 0

        # 4. Final payable
        final_interest_payable = final_interest + processing_fees

    return render_template(
        'company/interest_payable.html',
        total_loan_interest=total_loan_interest,
        total_repay_interest=total_repay_interest,
        final_interest=final_interest,
        processing_fees=processing_fees,
        final_interest_payable=final_interest_payable,
        end_date=end_date
    )

from datetime import date

def calculate_interest_payable_upto_today():
    total_loan_interest = 0
    total_repay_interest = 0
    processing_fees = 0

    today = date.today()

    loans = CompanyLoan.query.all()
    for loan in loans:
        days = (today - loan.date).days
        if days > 0:
            interest = (loan.loan_amount * (loan.interest_rate / 100) * days) / 365
            total_loan_interest += interest

    repayments = LoanRepayment.query.all()
    for rep in repayments:
        days = (today - rep.date).days
        if days > 0:
            interest = (rep.amount * (rep.interest_rate / 100) * days) / 365
            total_repay_interest += interest

    processing_fees = db.session.query(db.func.sum(CompanyLoan.total_processing_fee)).scalar() or 0

    final_payable = total_loan_interest - total_repay_interest + processing_fees
    return round(final_payable, 2)

