from __future__ import annotations

from flask import Blueprint, render_template
from sqlalchemy import func
from app import db
from app.models import CompanyLoan, LoanRepayment  # ensure these models exist

bp = Blueprint("company_loan_due", __name__, url_prefix="/company")


def _sum_scalar(q):
    val = q.scalar()
    return float(val or 0.0)


@bp.route("/loan-due", methods=["GET"])
def loan_due():
    """
    Company Loan Due = Sum(CompanyLoan.loan_amount) - Sum(LoanRepayment.amount)
    """
    total_loan_q = db.session.query(func.coalesce(func.sum(CompanyLoan.loan_amount), 0.0))
    total_repaid_q = db.session.query(func.coalesce(func.sum(LoanRepayment.amount), 0.0))

    total_loan = _sum_scalar(total_loan_q)
    total_repaid = _sum_scalar(total_repaid_q)
    loan_due = round(total_loan - total_repaid, 2)

    ctx = {
        "total_loan": round(total_loan, 2),
        "total_repaid": round(total_repaid, 2),
        "loan_due": loan_due,
    }
    return render_template("company/company_loan_due.html", **ctx)
