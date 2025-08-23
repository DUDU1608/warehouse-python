from __future__ import annotations

from datetime import datetime, date
from flask import Blueprint, render_template, request, redirect, url_for, flash
from sqlalchemy import func

from app import db
from app.models import Stockist, StockistLoanRepayment

bp = Blueprint("stockist_loan_repayment", __name__, url_prefix="/stockist")


# ---------- helpers ----------
def _parse_date(s: str) -> date | None:
    try:
        return datetime.strptime((s or "").strip(), "%Y-%m-%d").date()
    except Exception:
        return None


# ---------- Add Loan Repayment ----------
@bp.route("/add-loan-repayment", methods=["GET", "POST"])
def add_loan_repayment():
    stockists = Stockist.query.order_by(Stockist.name.asc()).all()

    if request.method == "POST":
        stockist_id = request.form.get("stockist_id")
        date_str = request.form.get("date")
        commodity = (request.form.get("commodity") or "").strip()
        warehouse = (request.form.get("warehouse") or "").strip()
        amount_str = request.form.get("amount")
        bank_reference = (request.form.get("bank_reference") or "").strip()

        st = Stockist.query.get(int(stockist_id)) if stockist_id else None
        if not st:
            flash("Select a valid stockist.", "danger")
            return render_template("stockist/add_loan_repayment.html", stockists=stockists)

        dt = _parse_date(date_str) or date.today()
        try:
            amount = float(amount_str or 0.0)
        except ValueError:
            amount = 0.0

        if amount <= 0:
            flash("Amount must be greater than 0.", "danger")
            return render_template("stockist/add_loan_repayment.html", stockists=stockists)

        row = StockistLoanRepayment(
            date=dt,
            stockist_name=st.name,
            mobile=st.mobile,
            warehouse=warehouse or None,
            commodity=commodity or None,
            amount=amount,
            bank_reference=bank_reference or None,
        )
        db.session.add(row)
        db.session.commit()
        flash("Loan repayment saved.", "success")
        return redirect(url_for("stockist_loan_repayment.list_loan_repayments"))

    return render_template("stockist/add_loan_repayment.html", stockists=stockists)


# ---------- List / filter ----------
@bp.route("/list-loan-repayments", methods=["GET"])
def list_loan_repayments():
    q = StockistLoanRepayment.query

    mobile = (request.args.get("mobile") or "").strip()
    commodity = (request.args.get("commodity") or "").strip()
    warehouse = (request.args.get("warehouse") or "").strip()

    if mobile:
        q = q.filter(StockistLoanRepayment.mobile == mobile)
    if commodity:
        q = q.filter(StockistLoanRepayment.commodity == commodity)
    if warehouse:
        q = q.filter(StockistLoanRepayment.warehouse == warehouse)

    rows = q.order_by(StockistLoanRepayment.date.desc(), StockistLoanRepayment.id.desc()).all()
    stockists = Stockist.query.order_by(Stockist.name.asc()).all()
    return render_template(
        "stockist/list_loan_repayment.html",
        repayments=rows,
        stockists=stockists,
    )


# ---------- Update (inline) ----------
@bp.route("/loan-repayment/<int:rep_id>/update", methods=["POST"])
def update_loan_repayment(rep_id: int):
    row = StockistLoanRepayment.query.get_or_404(rep_id)

    date_str = request.form.get("date")
    warehouse = request.form.get("warehouse")
    commodity = request.form.get("commodity")
    amount_str = request.form.get("amount")
    bank_reference = request.form.get("bank_reference")

    dt = _parse_date(date_str) or row.date
    try:
        amount = float(amount_str or row.amount)
    except ValueError:
        amount = row.amount

    row.date = dt
    row.warehouse = (warehouse or "").strip() or None
    row.commodity = (commodity or "").strip() or None
    row.amount = amount
    row.bank_reference = (bank_reference or "").strip() or None

    db.session.commit()
    flash("Repayment updated.", "success")
    return redirect(url_for("stockist_loan_repayment.list_loan_repayments"))


# ---------- Delete ----------
@bp.route("/loan-repayment/<int:rep_id>/delete", methods=["POST"])
def delete_loan_repayment(rep_id: int):
    row = StockistLoanRepayment.query.get_or_404(rep_id)
    db.session.delete(row)
    db.session.commit()
    flash("Repayment deleted.", "warning")
    return redirect(url_for("stockist_loan_repayment.list_loan_repayments"))
