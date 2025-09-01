# app/routes/company/company_stock.py
from __future__ import annotations

from decimal import Decimal, InvalidOperation
from flask import Blueprint, render_template, request, redirect, url_for, flash
from sqlalchemy import func
from app import db
from app.models import CompanyStock

bp = Blueprint("company_stock", __name__, url_prefix="/company/stock")

COMMODITY_CHOICES = ["Wheat", "Maize", "Paddy"]
QUALITY_CHOICES = ["Good", "BD"]

def _to_decimal(value: str, places: int = 2) -> Decimal:
    if not value:
        return Decimal("0")
    try:
        return Decimal(str(value).replace(",", "").strip())
    except (InvalidOperation, ValueError):
        return Decimal("0")

@bp.route("/", methods=["GET", "POST"])
def index():
    if request.method == "POST":
        warehouse = (request.form.get("warehouse") or "").strip()
        commodity = (request.form.get("commodity") or "").strip()
        quality = (request.form.get("quality") or "").strip()
        quantity = _to_decimal(request.form.get("quantity"), 3)
        average_price = _to_decimal(request.form.get("average_price"), 2)

        errors = []
        if not warehouse:
            errors.append("Warehouse is required.")
        if commodity not in COMMODITY_CHOICES:
            errors.append("Invalid commodity.")
        if quality not in QUALITY_CHOICES:
            errors.append("Invalid quality.")
        if quantity <= 0:
            errors.append("Quantity must be > 0.")
        if average_price < 0:
            errors.append("Average price cannot be negative.")

        if errors:
            for e in errors:
                flash(e, "danger")
        else:
            row = CompanyStock(
                warehouse=warehouse,
                commodity=commodity,
                quantity=quantity,
                quality=quality,
                average_price=average_price,
            )
            db.session.add(row)
            db.session.commit()
            flash("Stock entry added successfully.", "success")
            return redirect(url_for("company_stock.index"))

    # fetch all rows + sum
    rows = db.session.query(CompanyStock).order_by(CompanyStock.created_at.desc()).all()
    total_sum = (
        db.session.query(func.coalesce(func.sum(CompanyStock.total_price), 0))
        .scalar()
    )

    return render_template(
        "company/company_stock.html",
        rows=rows,
        total_sum=total_sum,
        commodities=COMMODITY_CHOICES,
        qualities=QUALITY_CHOICES,
    )

