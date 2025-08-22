from __future__ import annotations

from flask import Blueprint, render_template, request, redirect, url_for, flash
from datetime import datetime
from app import db
from app.models import Buyer, BuyerSale

bp = Blueprint("sales", __name__, url_prefix="/buyer")


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


@bp.route("/add-sale", methods=["GET", "POST"])
def add_sale():
    buyers = Buyer.query.order_by(Buyer.buyer_name.asc()).all()

    if request.method == "POST":
        # Required buyer
        buyer_id = request.form.get("buyer_id")
        buyer = Buyer.query.get(buyer_id) if buyer_id else None
        if not buyer:
            flash("Please select a valid Buyer.", "danger")
            return redirect(url_for("sales.add_sale"))

        date = _parse_date(request.form.get("date", "")) or datetime.utcnow().date()
        rst_no = request.form.get("rst_no", "").strip()
        warehouse = request.form.get("warehouse", "").strip()
        commodity = request.form.get("commodity", "").strip()
        quality = request.form.get("quality", "").strip()

        quantity = _f(request.form.get("quantity"))
        rate = _f(request.form.get("rate"))
        handling = _f(request.form.get("handling_charge"))

        cost = quantity * rate
        net_cost = cost + handling

        rec = BuyerSale(
            date=date,
            rst_no=rst_no,
            warehouse=warehouse,
            buyer_id=buyer.id,
            buyer_name=buyer.buyer_name,
            mobile=buyer.mobile_no,
            commodity=commodity,
            quantity=quantity,
            rate=rate,
            cost=cost,
            handling_charge=handling,
            net_cost=net_cost,
            quality=quality,
        )
        db.session.add(rec)
        db.session.commit()
        flash("Sale recorded.", "success")
        return redirect(url_for("sales.list_sales"))

    return render_template("buyer/add_sale.html", buyers=buyers)


@bp.route("/sales", methods=["GET"])
def list_sales():
    # Filters
    buyer_mobile = request.args.get("mobile", "").strip()
    commodity = request.args.get("commodity", "").strip()
    quality = request.args.get("quality", "").strip()
    warehouse = request.args.get("warehouse", "").strip()
    date_from = _parse_date(request.args.get("from", ""))
    date_to = _parse_date(request.args.get("to", ""))

    q = BuyerSale.query
    if buyer_mobile:
        q = q.filter(BuyerSale.mobile == buyer_mobile)
    if commodity:
        q = q.filter(BuyerSale.commodity == commodity)
    if quality:
        q = q.filter(BuyerSale.quality == quality)
    if warehouse:
        q = q.filter(BuyerSale.warehouse == warehouse)
    if date_from:
        q = q.filter(BuyerSale.date >= date_from)
    if date_to:
        q = q.filter(BuyerSale.date <= date_to)

    sales = q.order_by(BuyerSale.date.desc(), BuyerSale.id.desc()).all()
    buyers = Buyer.query.order_by(Buyer.buyer_name.asc()).all()
    return render_template("buyer/list_sales.html", sales=sales, buyers=buyers)


@bp.route("/sales/<int:sale_id>/update", methods=["POST"])
def update_sale(sale_id: int):
    s = BuyerSale.query.get_or_404(sale_id)

    s.date = _parse_date(request.form.get("date")) or s.date
    s.rst_no = request.form.get("rst_no", s.rst_no)
    s.warehouse = request.form.get("warehouse", s.warehouse)
    s.commodity = request.form.get("commodity", s.commodity)
    s.quality = request.form.get("quality", s.quality)

    s.quantity = _f(request.form.get("quantity"), s.quantity)
    s.rate = _f(request.form.get("rate"), s.rate)
    s.handling_charge = _f(request.form.get("handling_charge"), s.handling_charge)

    # Recalculate
    s.cost = s.quantity * s.rate
    s.net_cost = s.cost + s.handling_charge

    db.session.commit()
    flash("Sale updated.", "success")
    return redirect(url_for("sales.list_sales"))


@bp.route("/sales/<int:sale_id>/delete", methods=["POST"])
def delete_sale(sale_id: int):
    s = BuyerSale.query.get_or_404(sale_id)
    db.session.delete(s)
    db.session.commit()
    flash("Sale deleted.", "info")
    return redirect(url_for("sales.list_sales"))
