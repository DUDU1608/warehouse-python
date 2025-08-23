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
    Given date->delta outstanding (₹) up to 'as_of',
    accrue simple interest daily at DAILY_RATE (inclusive of 'as_of').
    - Apply each delta at the START of its date.
    - Prevent negative outstanding (no negative accrual).
    """
    if not changes_by_date:
        return 0.0

    # Keep only events up to 'as_of'
    keys = sorted(d for d in changes_by_date.keys() if d and d <= as_of)
    if not keys:
        return 0.0

    outstanding = 0.0
    total = 0.0
    current = keys[0]

    for d in keys:
        if d > as_of:
            break
        # Accrue from 'current' up to the day BEFORE 'd'
        if d > current and outstanding > 0:
            days = (d - current).days
            if days > 0:
                total += outstanding * DAILY_RATE * days

        # Apply all deltas on day 'd'
        outstanding += float(changes_by_date.get(d, 0.0))
        if outstanding < 0:
            outstanding = 0.0
        current = d

    # Accrue THROUGH as_of (inclusive)
    if current <= as_of and outstanding > 0:
        days = (as_of - current).days + 1
        if days > 0:
            total += outstanding * DAILY_RATE * days

    return round(total, 2)


def _all_stockists_upto(as_of: date) -> set[str]:
    """Union of stockists present in loans, margins, or repayments up to 'as_of'."""
    s1 = {r[0] for r in db.session.query(LoanData.stockist_name).filter(LoanData.date <= as_of).distinct().all() if r[0]}
    s2 = {r[0] for r in db.session.query(MarginData.stockist_name).filter(MarginData.date <= as_of).distinct().all() if r[0]}
    s3 = {r[0] for r in db.session.query(StockistLoanRepayment.stockist_name).filter(StockistLoanRepayment.date <= as_of).distinct().all() if r[0]}
    return s1 | s2 | s3


@bp.route('/interest-receivable', methods=['GET', 'POST'])
def interest_receivable():
    """
    Renders a simple page where the main number shown is:
      final_interest_receivable  -> repayment-aware, piecewise daily accrual across all stockists.

    For continuity with the old template:
      total_loan_interest   -> simple sum of per-loan interest (no offsets)
      total_margin_interest -> simple sum of per-margin + per-repayment interest (treated as offsets)
    These two parts are for display only and may not match the piecewise final exactly.
    """
    total_loan_interest = 0.0                 # simple display helper (loans only)
    total_margin_interest = 0.0               # simple display helper (margins + repayments)
    final_interest_receivable = 0.0           # ✅ authoritative, piecewise
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

        # ---------- (A) Piecewise, repayment-aware (authoritative) ----------
        piecewise_total = 0.0
        for stockist in _all_stockists_upto(end_date):
            changes = defaultdict(float)

            # + loans (cash & margin) up to end_date
            for dt, amt in db.session.query(LoanData.date, LoanData.amount)\
                                     .filter(LoanData.date <= end_date,
                                             func.upper(LoanData.stockist_name) == func.upper(stockist)).all():
                if dt and amt:
                    changes[dt] += float(amt)

            # - margins up to end_date
            for dt, amt in db.session.query(MarginData.date, MarginData.amount)\
                                     .filter(MarginData.date <= end_date,
                                             func.upper(MarginData.stockist_name) == func.upper(stockist)).all():
                if dt and amt:
                    changes[dt] -= float(amt)

            # - loan repayments up to end_date  ✅
            for dt, amt in db.session.query(StockistLoanRepayment.date, StockistLoanRepayment.amount)\
                                     .filter(StockistLoanRepayment.date <= end_date,
                                             func.upper(StockistLoanRepayment.stockist_name) == func.upper(stockist)).all():
                if dt and amt:
                    changes[dt] -= float(amt)

            if changes:
                piecewise_total += _accrue_interest_piecewise(changes, end_date)

        final_interest_receivable = round(piecewise_total, 2)

        # ---------- (B) Simple parts for display (not used in final math) ----------
        # Simple loan side (sum each loan's interest days inclusively)
        for loan in LoanData.query.filter(LoanData.date <= end_date).all():
            if not loan.date:
                continue
            days = (end_date - loan.date).days + 1
            if days > 0 and loan.amount:
                total_loan_interest += float(loan.amount) * DAILY_RATE * days

        # Simple offsets: margins + repayments (both reduce receivable)
        for margin in MarginData.query.filter(MarginData.date <= end_date).all():
            if not margin.date:
                continue
            days = (end_date - margin.date).days + 1
            if days > 0 and margin.amount:
                total_margin_interest += float(margin.amount) * DAILY_RATE * days

        for repay in StockistLoanRepayment.query.filter(StockistLoanRepayment.date <= end_date).all():
            if not repay.date:
                continue
            days = (end_date - repay.date).days + 1
            if days > 0 and repay.amount:
                total_margin_interest += float(repay.amount) * DAILY_RATE * days  # include with "margin" bucket

        total_loan_interest = round(total_loan_interest, 2)
        total_margin_interest = round(total_margin_interest, 2)

    return render_template(
        'company/interest_receivable.html',
        total_loan_interest=total_loan_interest,
        total_margin_interest=total_margin_interest,  # includes repayments for display
        final_interest_receivable=final_interest_receivable,  # ✅ repayment-aware
        roi=roi,
        end_date=end_date
    )


def calculate_interest_receivable_upto_today() -> float:
    """
    Helper used by other modules. Returns the repayment-aware, piecewise interest receivable
    across all stockists up to TODAY (inclusive).
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
