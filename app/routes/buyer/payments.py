from __future__ import annotations

from flask import Blueprint, render_template, request, redirect, url_for, flash
from app import db
from app.models import Buyer, BuyerPayment

bp = Blueprint("payments", __name__, url_prefix="/buyer")


def _f(v, default=0.0) -> float:
    try:
        return float(v)
    except Exception:
        return float(default)


@bp.route("/add-payment", methods=["GET", "POST"])
def add_payment():
    buyers = Buyer.query.order_by(Buyer.buyer_name.asc()).all()

    if request.method == "POST":
        buyer_id = request.form.get("buyer_id")
        buyer = Buyer.query.get(buyer_id) if buyer_id else None
        if not buyer:
            flash("Please select a valid Buyer.", "danger")
            return redirect(url_for("payments.add_payment"))

        commodity = request.form.get("commodity", "").strip()
        warehouse = request.form.get("warehouse", "").strip()
        amount = _f(request.form.get("amount"))
        reference = request.form.get("reference", "").strip()

        p = BuyerPayment(
            buyer_id=buyer.id,
            buyer_name=buyer.buyer_name,
            mobile_no=buyer.mobile_no,
            commodity=commodity,
            warehouse=warehouse,
            amount=amount,
            reference=reference,
        )
        db.session.add(p)
        db.session.commit()
        flash("Payment receipt added.", "success")
        return redirect(url_for("payments.list_payments"))

    return render_template("buyer/add_payment.html", buyers=buyers)


@bp.route("/payments", methods=["GET"])
def list_payments():
    buyer_mobile = request.args.get("mobile", "").strip()
    commodity = request.args.get("commodity", "").strip()
    warehouse = request.args.get("warehouse", "").strip()

    q = BuyerPayment.query
    if buyer_mobile:
        q = q.filter(BuyerPayment.mobile_no == buyer_mobile)
    if commodity:
        q = q.filter(BuyerPayment.commodity == commodity)
    if warehouse:
        q = q.filter(BuyerPayment.warehouse == warehouse)

    payments = q.order_by(BuyerPayment.id.desc()).all()
    buyers = Buyer.query.order_by(Buyer.buyer_name.asc()).all()
    return render_template("buyer/list_payments.html", payments=payments, buyers=buyers)


@bp.route("/payments/<int:payment_id>/update", methods=["POST"])
def update_payment(payment_id: int):
    p = BuyerPayment.query.get_or_404(payment_id)

    p.commodity = request.form.get("commodity", p.commodity)
    p.warehouse = request.form.get("warehouse", p.warehouse)
    p.amount = _f(request.form.get("amount"), p.amount)
    p.reference = request.form.get("reference", p.reference)

    db.session.commit()
    flash("Payment updated.", "success")
    return redirect(url_for("payments.list_payments"))


@bp.route("/payments/<int:payment_id>/delete", methods=["POST"])
def delete_payment(payment_id: int):
    p = BuyerPayment.query.get_or_404(payment_id)
    db.session.delete(p)
    db.session.commit()
    flash("Payment deleted.", "info")
    return redirect(url_for("payments.list_payments"))
