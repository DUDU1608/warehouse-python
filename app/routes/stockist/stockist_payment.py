from __future__ import annotations
from datetime import datetime
from flask import Blueprint, render_template, request, redirect, url_for, flash
from app import db
from app.models import Stockist, StockistPayment

bp = Blueprint("stockist_payment", __name__, url_prefix="/stockist")

def _parse_date(s: str):
    try:
        return datetime.strptime(s, "%Y-%m-%d").date()
    except Exception:
        return None

def _f(v, default=0.0) -> float:
    try:
        return float(v)
    except Exception:
        return float(default)

@bp.route("/add-payment", methods=["GET", "POST"])
def add_payment():
    stockists = Stockist.query.order_by(Stockist.name.asc()).all()

    if request.method == "POST":
        stockist_id = request.form.get("stockist_id")
        st = Stockist.query.get(stockist_id) if stockist_id else None
        if not st:
            flash("Please select a valid Stockist.", "danger")
            return redirect(url_for("stockist_payment.add_payment"))

        pay_date = _parse_date(request.form.get("date")) or datetime.utcnow().date()
        commodity = (request.form.get("commodity") or "").strip()
        warehouse = (request.form.get("warehouse") or "").strip()
        amount = _f(request.form.get("amount"))
        bank_reference = (request.form.get("bank_reference") or "").strip()

        p = StockistPayment(
            date=pay_date,
            stockist_id=st.id,
            stockist_name=st.name,
            mobile=st.mobile,
            warehouse=warehouse,
            commodity=commodity,
            amount=amount,
            bank_reference=bank_reference,
        )
        db.session.add(p)
        db.session.commit()
        flash("Stockist payment added.", "success")
        return redirect(url_for("stockist_payment.list_payments"))

    return render_template("stockist/add_payment.html", stockists=stockists)

@bp.route("/payments", methods=["GET"])
def list_payments():
    mobile = (request.args.get("mobile") or "").strip()
    commodity = (request.args.get("commodity") or "").strip()
    warehouse = (request.args.get("warehouse") or "").strip()
    d_from = _parse_date(request.args.get("from", ""))
    d_to   = _parse_date(request.args.get("to", ""))

    q = StockistPayment.query
    if mobile:    q = q.filter(StockistPayment.mobile == mobile)
    if commodity: q = q.filter(StockistPayment.commodity == commodity)
    if warehouse: q = q.filter(StockistPayment.warehouse == warehouse)
    if d_from:    q = q.filter(StockistPayment.date >= d_from)
    if d_to:      q = q.filter(StockistPayment.date <= d_to)

    payments = q.order_by(StockistPayment.date.desc(), StockistPayment.id.desc()).all()
    stockists = Stockist.query.order_by(Stockist.name.asc()).all()
    return render_template("stockist/list_payments.html", payments=payments, stockists=stockists)

@bp.route("/payments/<int:payment_id>/update", methods=["POST"])
def update_payment(payment_id: int):
    p = StockistPayment.query.get_or_404(payment_id)

    p.date = _parse_date(request.form.get("date")) or p.date
    p.commodity = request.form.get("commodity", p.commodity)
    p.warehouse = request.form.get("warehouse", p.warehouse)
    p.amount = _f(request.form.get("amount"), p.amount)
    p.bank_reference = request.form.get("bank_reference", p.bank_reference)

    db.session.commit()
    flash("Stockist payment updated.", "success")
    return redirect(url_for("stockist_payment.list_payments"))

@bp.route("/payments/<int:payment_id>/delete", methods=["POST"])
def delete_payment(payment_id: int):
    p = StockistPayment.query.get_or_404(payment_id)
    db.session.delete(p)
    db.session.commit()
    flash("Stockist payment deleted.", "info")
    return redirect(url_for("stockist_payment.list_payments"))
