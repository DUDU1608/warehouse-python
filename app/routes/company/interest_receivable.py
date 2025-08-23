from __future__ import annotations

from flask import Blueprint, render_template, request
from datetime import datetime, date
from collections import defaultdict
from sqlalchemy import func

from app import db
from app.models import LoanData, MarginData, StockistLoanRepayment  # ✅ include repayments

bp = Blueprint('interest_receivable', __name__, url_prefix='/company')

ANNUAL_ROI = 13.75  # % per annum
DAILY_RATE = ANNUAL_ROI / 100.0 / 365.0


def _accrue_interest_piecewise(changes_by_date: dict[date, float], as_of: date) -> float:
    """
    Repayment-aware daily simple interest accrual:
      - Apply each delta (₹) at the START of its date.
      - Accrue from each change date up to the next change (exclusive),
        and from the last change THROUGH 'as_of' (inclusive).
      - Prevent negative outstanding.
    """
    if not changes_by_date:
        return 0.0

    keys = sorted(d for d in changes_by_date if d and d <= as_of)
    if not keys:
        return 0.0

    outstanding = 0.0
    total = 0.0
    current = keys[0]

    for d in keys:
        if d > as_of:
            break
        # accrue from 'current' to the day BEFORE 'd'
        if d > current and outstanding > 0:
            days = (d - current).days
            if days > 0:
                total += outstanding * DAILY_RATE * days

        # apply delta on day 'd'
        outstanding += float(changes_by_date.get(d, 0.0))
        if outstanding < 0:
            outstanding = 0.0
        current = d

    # accrue THROUGH as_of (inclusive)
    if current <= as_of and outstanding > 0:
        days = (as_of - current).days + 1
        if days > 0:
            total += outstanding * DAILY_RATE * days

    return round(total, 2)


def _all_stockists_upto(as_of: date) -> set[str]:
    """Union of stockists present in loans, margins, or repayments up to 'as_of'."""
    s1 = {r[0] for r in db.session.query(LoanData.stockist_name)
          .filter(LoanData.date <= as_of).distinct().all() if r[0]}
    s2 = {r[0] for r in db.session.query(MarginData.stockist_name)
          .filter(MarginData.date <= as_of).distinct().all() if r[0]}
    s3 = {r[0] for r in db.session.query(StockistLoanRepayment.stockist_name)
          .filter(StockistLoanRepayment.date <= as_of).distinct().all() if r[0]}
    return s1 | s2 | s3


@bp.route('/interest-receivable', methods=['GET', 'POST'])
def interest_receivable():
    """
    Shows:
      - total_loan_interest (simple sum of each loan's interest)
      - total_margin_interest (simple sum of each margin's 'negative' interest)
      - total_repayment_interest (simple sum of each repayment's 'negative' interest)
      - simple_interest_receivable = loan - margin - repayment
      - final_interest_receivable  = repayment-aware, piecewise accrual (authoritative)
    """
    total_loan_interest = 0.0
    total_margin_interest = 0.0
    total_repayment_interest = 0.0
    simple_interest_receivable = 0.0
    final_interest_receivable = 0.0
    end_date: date | None = None
    roi = ANNUAL_ROI

    if request.method == 'POST':
        end_date_str = request.form.get('date')
        if not end_date_str:
            return render_template('company/interest_receivable.html', error="Please select a date.")
        try:
            end_date = datetime.strptime(end_date_str, "%Y-%m-%d").date()
        except Exception:
            return render_template('company/interest_receivable.html', error="Invalid date format (YYYY-MM-DD).")

        # ---------- (A) Authoritative piecewise (repayment-aware) ----------
        piecewise_total = 0.0
        for stockist in _all_stockists_upto(end_date):
            changes = defaultdict(float)

            # + loans (cash & margin)
            for dt, amt in db.session.query(LoanData.date, LoanData.amount)\
                                     .filter(LoanData.date <= end_date,
                                             func.upper(LoanData.stockist_name) == func.upper(stockist)).all():
                if dt and amt:
                    changes[dt] += float(amt)

            # - margins
            for dt, amt in db.session.query(MarginData.date, MarginData.amount)\
                                     .filter(MarginData.date <= end_date,
                                             func.upper(MarginData.stockist_name) == func.upper(stockist)).all():
                if dt and amt:
                    changes[dt] -= float(amt)

            # - loan repayments  ✅
            for dt, amt in db.session.query(StockistLoanRepayment.date, StockistLoanRepayment.amount)\
                                     .filter(StockistLoanRepayment.date <= end_date,
                                             func.upper(StockistLoanRepayment.stockist_name) == func.upper(stockist)).all():
                if dt and amt:
                    changes[dt] -= float(amt)

            if changes:
                piecewise_total += _accrue_interest_piecewise(changes, end_date)

        final_interest_receivable = round(piecewise_total, 2)

        # ---------- (B) Simple display buckets (inclusive days) ----------
        for loan in LoanData.query.filter(LoanData.date <= end_date).all():
            if loan.date and loan.amount:
                days = (end_date - loan.date).days + 1
                if days > 0:
                    total_loan_interest += float(loan.amount) * DAILY_RATE * days

        for margin in MarginData.query.filter(MarginData.date <= end_date).all():
            if margin.date and margin.amount:
                days = (end_date - margin.date).days + 1
                if days > 0:
                    total_margin_interest += float(margin.amount) * DAILY_RATE * days

        for repay in StockistLoanRepayment.query.filter(StockistLoanRepayment.date <= end_date).all():
            if repay.date and repay.amount:
                days = (end_date - repay.date).days + 1
                if days > 0:
                    total_repayment_interest += float(repay.amount) * DAILY_RATE * days

        total_loan_interest = round(total_loan_interest, 2)
        total_margin_interest = round(total_margin_interest, 2)
        total_repayment_interest = round(total_repayment_interest, 2)
        simple_interest_receivable = round(
            total_loan_interest - total_margin_interest - total_repayment_interest, 2
        )

    return render_template(
        'company/interest_receivable.html',
        roi=roi,
        end_date=end_date,
        total_loan_interest=total_loan_interest,
        total_margin_interest=total_margin_interest,
        total_repayment_interest=total_repayment_interest,     # ✅ new
        simple_interest_receivable=simple_interest_receivable, # ✅ new
        final_interest_receivable=final_interest_receivable,   # ✅ repayment-aware piecewise
    )


def calculate_interest_receivable_upto_today() -> float:
    """
    Returns repayment-aware, piecewise interest receivable up to TODAY (inclusive).
    Used by other modules (e.g., Profit/Loss).
    """
    as_of = date.today()
    total = 0.0

    for stockist in _all_stockists_upto(as_of):
        changes = defaultdict(float)

        for dt, amt in db.session.query(LoanData.date, LoanData.amount)\
                                 .filter(LoanData.date <= as_of,
                                         func.upper(LoanData.stockist_name) == func.upper(stockist)).all():
            if dt and amt:
                changes[dt] += float(amt)

        for dt, amt in db.session.query(MarginData.date, MarginData.amount)\
                                 .filter(MarginData.date <= as_of,
                                         func.upper(MarginData.stockist_name) == func.upper(stockist)).all():
            if dt and amt:
                changes[dt] -= float(amt)

        for dt, amt in db.session.query(StockistLoanRepayment.date, StockistLoanRepayment.amount)\
                                 .filter(StockistLoanRepayment.date <= as_of,
                                         func.upper(StockistLoanRepayment.stockist_name) == func.upper(stockist)).all():
            if dt and amt:
                changes[dt] -= float(amt)

        if changes:
            total += _accrue_interest_piecewise(changes, as_of)

    return round(total, 2)
