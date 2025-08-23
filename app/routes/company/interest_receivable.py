from __future__ import annotations

from flask import Blueprint, render_template, request
from datetime import datetime, date
from collections import defaultdict
from sqlalchemy import func

from app import db
from app.models import LoanData, MarginData, StockistLoanRepayment

bp = Blueprint("interest_receivable", __name__, url_prefix="/company")

ROI_ANNUAL = 13.75  # % p.a.
DAILY_RATE = ROI_ANNUAL / 100.0 / 365.0  # simple daily rate


def _stockists_upto(as_of: date) -> set[str]:
    """All stockists that have any loan/margin/repayment up to 'as_of'."""
    s1 = {
        r[0]
        for r in db.session.query(LoanData.stockist_name)
        .filter(LoanData.date <= as_of)
        .distinct()
        .all()
        if r[0]
    }
    s2 = {
        r[0]
        for r in db.session.query(MarginData.stockist_name)
        .filter(MarginData.date <= as_of)
        .distinct()
        .all()
        if r[0]
    }
    s3 = {
        r[0]
        for r in db.session.query(StockistLoanRepayment.stockist_name)
        .filter(StockistLoanRepayment.date <= as_of)
        .distinct()
        .all()
        if r[0]
    }
    return s1 | s2 | s3


def _accrue_interest_piecewise(changes_by_date: dict[date, float], as_of: date) -> float:
    """
    Accrue daily simple interest on the *actual net outstanding*:
      outstanding(t) = max(0, outstanding(t-1) + delta_on_t)
    Interest accrues only when outstanding > 0.
    Deltas are applied at the START of the event day.
    Accrual is inclusive of 'as_of'.
    """
    if not changes_by_date:
        return 0.0

    event_days = sorted(d for d in changes_by_date if d and d <= as_of)
    if not event_days:
        return 0.0

    outstanding = 0.0
    total_interest = 0.0
    current = event_days[0]

    for d in event_days:
        if d > as_of:
            break
        # accrue from 'current' up to the day BEFORE 'd'
        if d > current and outstanding > 0:
            days = (d - current).days
            if days > 0:
                total_interest += outstanding * DAILY_RATE * days
        # apply delta at the start of day 'd'
        outstanding += float(changes_by_date.get(d, 0.0))
        if outstanding < 0:
            outstanding = 0.0
        current = d

    # accrue THROUGH as_of (inclusive)
    if current <= as_of and outstanding > 0:
        days = (as_of - current).days + 1
        if days > 0:
            total_interest += outstanding * DAILY_RATE * days

    return round(total_interest, 2)


@bp.route("/interest-receivable", methods=["GET", "POST"])
def interest_receivable():
    """
    Compute interest receivable as daily interest on:
      Outstanding(t) = (Loans≤t) - (Margins≤t) - (Repayments≤t), floored at 0.
    Summed for all days up to the entered date (inclusive).
    """
    end_date: date | None = None
    interest_receivable: float | None = None
    error: str | None = None

    if request.method == "POST":
        date_str = (request.form.get("date") or "").strip()
        if not date_str:
            error = "Please select a date."
        else:
            try:
                end_date = datetime.strptime(date_str, "%Y-%m-%d").date()
            except Exception:
                error = "Invalid date format. Use YYYY-MM-DD."

    if end_date and not error:
        total = 0.0

        # Do this per stockist to avoid cross-netting across parties.
        for stockist in _stockists_upto(end_date):
            changes = defaultdict(float)

            # + Loans (cash + margin loans)
            for dt, amt in (
                db.session.query(LoanData.date, LoanData.amount)
                .filter(
                    LoanData.date <= end_date,
                    func.upper(LoanData.stockist_name) == func.upper(stockist),
                )
                .all()
            ):
                if dt and amt:
                    changes[dt] += float(amt)

            # - Margins
            for dt, amt in (
                db.session.query(MarginData.date, MarginData.amount)
                .filter(
                    MarginData.date <= end_date,
                    func.upper(MarginData.stockist_name) == func.upper(stockist),
                )
                .all()
            ):
                if dt and amt:
                    changes[dt] -= float(amt)

            # - Loan Repayments
            for dt, amt in (
                db.session.query(StockistLoanRepayment.date, StockistLoanRepayment.amount)
                .filter(
                    StockistLoanRepayment.date <= end_date,
                    func.upper(StockistLoanRepayment.stockist_name) == func.upper(stockist),
                )
                .all()
            ):
                if dt and amt:
                    changes[dt] -= float(amt)

            if changes:
                total += _accrue_interest_piecewise(changes, end_date)

        interest_receivable = round(total, 2)

    return render_template(
        "company/interest_receivable.html",
        end_date=end_date,
        roi=ROI_ANNUAL,
        interest_receivable=interest_receivable,
        error=error,
    )
