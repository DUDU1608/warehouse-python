from flask import Blueprint, render_template, request
from app import db
from app.models import LoanData, MarginData
from datetime import datetime

bp = Blueprint('interest_receivable', __name__, url_prefix='/company')

@bp.route('/interest-receivable', methods=['GET', 'POST'])
def interest_receivable():
    total_loan_interest = 0
    total_margin_interest = 0
    final_interest_receivable = 0
    end_date = None
    roi = 13.75

    if request.method == 'POST':
        end_date_str = request.form.get('date')
        if not end_date_str:
            return render_template('company/interest_receivable.html', error="Please select a date.")

        end_date = datetime.strptime(end_date_str, "%Y-%m-%d").date()

        # 1. Calculate interest for each loan from its date to end_date
        loans = LoanData.query.all()
        for loan in loans:
            days = (end_date - loan.date).days
            if days > 0:
                interest = (loan.amount * roi * days) / (100 * 365)
                total_loan_interest += interest

        # 2. Calculate interest for margin data
        margins = MarginData.query.all()
        for margin in margins:
            days = (end_date - margin.date).days
            if days > 0:
                interest = (margin.amount * roi * days) / (100 * 365)
                total_margin_interest += interest

        final_interest_receivable = total_loan_interest - total_margin_interest

    return render_template(
        'company/interest_receivable.html',
        total_loan_interest=total_loan_interest,
        total_margin_interest=total_margin_interest,
        final_interest_receivable=final_interest_receivable,
        roi=roi,
        end_date=end_date
    )

def calculate_interest_receivable_upto_today():
    from datetime import date

    total_loan_interest = 0
    total_margin_interest = 0
    roi = 13.75
    today = date.today()

    loans = LoanData.query.all()
    for loan in loans:
        days = (today - loan.date).days
        if days > 0:
            interest = (loan.amount * roi * days) / (100 * 365)
            total_loan_interest += interest

    margins = MarginData.query.all()
    for margin in margins:
        days = (today - margin.date).days
        if days > 0:
            interest = (margin.amount * roi * days) / (100 * 365)
            total_margin_interest += interest

    final_receivable = total_loan_interest - total_margin_interest
    return round(final_receivable, 2)

