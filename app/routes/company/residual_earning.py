from __future__ import annotations
from datetime import datetime
from flask import Blueprint, render_template, request, redirect, url_for, flash
from app import db
from app.models import ResidualEarning

bp = Blueprint("residual_earning", __name__, url_prefix="/company")

def _parse_date(s: str):
    try:
        return datetime.strptime(s, "%Y-%m-%d").date()
    except Exception:
        return None

def _f(v, default=0.0) -> float:
    try: return float(v)
    except Exception: return float(default)

@bp.route("/residual-earning/add", methods=["GET", "POST"])
def add_earning():
    if request.method == "POST":
        date = _parse_date(request.form.get("date")) or datetime.utcnow().date()
        warehouse = (request.form.get("warehouse") or "").strip()
        commodity = (request.form.get("commodity") or "").strip()
        quantity = _f(request.form.get("quantity"))
        rate = _f(request.form.get("rate"))
        total = _f(request.form.get("total_earning")) or (quantity * rate)

        if not warehouse or not commodity:
            flash("Warehouse and Commodity are required.", "warning")
            return redirect(url_for("residual_earning.add_earning"))

        rec = ResidualEarning(
            date=date, warehouse=warehouse, commodity=commodity,
            quantity=quantity, rate=rate, total_earning=total
        )
        db.session.add(rec)
        db.session.commit()
        flash("Residual earning added.", "success")
        return redirect(url_for("residual_earning.list_earnings"))

    return render_template("company/add_residual_earning.html")

@bp.route("/residual-earnings", methods=["GET"])
def list_earnings():
    commodity = (request.args.get("commodity") or "").strip()
    warehouse = (request.args.get("warehouse") or "").strip()
    d_from = _parse_date(request.args.get("from", ""))
    d_to = _parse_date(request.args.get("to", ""))

    q = ResidualEarning.query
    if commodity: q = q.filter(ResidualEarning.commodity == commodity)
    if warehouse: q = q.filter(ResidualEarning.warehouse == warehouse)
    if d_from:    q = q.filter(ResidualEarning.date >= d_from)
    if d_to:      q = q.filter(ResidualEarning.date <= d_to)

    rows = q.order_by(ResidualEarning.date.desc(), ResidualEarning.id.desc()).all()
    # for simple dropdowns
    warehouses = [w[0] for w in db.session.query(ResidualEarning.warehouse).distinct().all()]
    commodities = [c[0] for w in db.session.query(ResidualEarning.commodity).distinct().all()]
    return render_template("company/list_residual_earnings.html",
                           rows=rows, warehouses=warehouses, commodities=commodities)

@bp.route("/residual-earnings/<int:rid>/update", methods=["POST"])
def update_earning(rid: int):
    r = ResidualEarning.query.get_or_404(rid)
    r.date = _parse_date(request.form.get("date")) or r.date
    r.warehouse = (request.form.get("warehouse") or r.warehouse).strip()
    r.commodity = (request.form.get("commodity") or r.commodity).strip()
    r.quantity = _f(request.form.get("quantity"), r.quantity)
    r.rate = _f(request.form.get("rate"), r.rate)
    # prefer server-side authoritative recompute if total omitted
    inp_total = request.form.get("total_earning", "").strip()
    r.total_earning = _f(inp_total, r.quantity * r.rate)

    db.session.commit()
    flash("Residual earning updated.", "success")
    return redirect(url_for("residual_earning.list_earnings"))

@bp.route("/residual-earnings/<int:rid>/delete", methods=["POST"])
def delete_earning(rid: int):
    r = ResidualEarning.query.get_or_404(rid)
    db.session.delete(r)
    db.session.commit()
    flash("Residual earning deleted.", "info")
    return redirect(url_for("residual_earning.list_earnings"))
