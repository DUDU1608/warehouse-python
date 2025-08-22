from __future__ import annotations

from flask import Blueprint, render_template, request, redirect, url_for, flash
from sqlalchemy import or_
from app import db
from app.models import Buyer

bp = Blueprint("buyer", __name__, url_prefix="/buyer")


@bp.route("/add-buyer", methods=["GET", "POST"])
def add_buyer():
    if request.method == "POST":
        buyer_name = request.form.get("buyer_name", "").strip()
        mobile_no = request.form.get("mobile_no", "").strip()
        address = request.form.get("address", "").strip()

        if not buyer_name or not mobile_no:
            flash("Buyer Name and Mobile No are required.", "warning")
            return redirect(url_for("buyer.add_buyer"))

        # Enforce unique mobile
        if Buyer.query.filter_by(mobile_no=mobile_no).first():
            flash("A buyer with this Mobile No already exists.", "danger")
            return redirect(url_for("buyer.add_buyer"))

        b = Buyer(buyer_name=buyer_name, mobile_no=mobile_no, address=address)
        db.session.add(b)
        db.session.commit()
        flash("Buyer added successfully.", "success")
        return redirect(url_for("buyer.list_buyer"))

    return render_template("buyer/add_buyer.html")


@bp.route("/buyers", methods=["GET"])
def list_buyer():
    q = request.args.get("q", "").strip()
    qry = Buyer.query
    if q:
        like = f"%{q}%"
        qry = qry.filter(
            or_(
                Buyer.buyer_name.ilike(like),
                Buyer.mobile_no.ilike(like),
                Buyer.address.ilike(like),
            )
        )
    buyers = qry.order_by(Buyer.buyer_name.asc()).all()
    return render_template("buyer/list_buyer.html", buyers=buyers, q=q)


@bp.route("/buyers/<int:buyer_id>/update", methods=["POST"])
def update_buyer(buyer_id: int):
    b = Buyer.query.get_or_404(buyer_id)

    new_name = request.form.get("buyer_name", b.buyer_name).strip()
    new_mobile = request.form.get("mobile_no", b.mobile_no).strip()
    new_address = request.form.get("address", b.address)

    # If mobile changed, ensure uniqueness
    if new_mobile != b.mobile_no and Buyer.query.filter_by(mobile_no=new_mobile).first():
        flash("Another buyer already uses this Mobile No.", "danger")
        return redirect(url_for("buyer.list_buyer"))

    b.buyer_name = new_name
    b.mobile_no = new_mobile
    b.address = new_address

    db.session.commit()
    flash("Buyer updated.", "success")
    return redirect(url_for("buyer.list_buyer"))


@bp.route("/buyers/<int:buyer_id>/delete", methods=["POST"])
def delete_buyer(buyer_id: int):
    b = Buyer.query.get_or_404(buyer_id)
    db.session.delete(b)
    db.session.commit()
    flash("Buyer deleted (including related sales and payments).", "info")
    return redirect(url_for("buyer.list_buyer"))
