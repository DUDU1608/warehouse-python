# app/routes/buyer/sales.py
from __future__ import annotations

from datetime import date, datetime
from flask import Blueprint, render_template, request, redirect, url_for, flash
from sqlalchemy import and_
from app import db
from app.models import Buyer, BuyerSale, BuyerPayment, Stockist, StockExit

bp = Blueprint("sales", __name__, url_prefix="/buyer/sales")


# ---------- helpers ----------
def _parse_date(s: str | None, default: date | None = None) -> date | None:
    if not s:
        return default
    try:
        return datetime.strptime(s, "%Y-%m-%d").date()
    except ValueError:
        return default

def _f(x, default=0.0) -> float:
    try:
        return float(x)
    except Exception:
        return default

def _q(x) -> float:
    """quantity parser with 3-decimals typical for kg"""
    return _f(x, 0.0)

def _compute_costs(qty: float, rate: float, handling: float) -> tuple[float, float]:
    cost = qty * rate
    net = cost + handling
    return round(cost, 2), round(net, 2)


def _stockist_mobile(name: str | None) -> str | None:
    if not name:
        return None
    s = Stockist.query.filter(Stockist.name == name).first()
    return s.mobile if s else None


def _find_matching_stockexit(
    when: date,
    stockist_name: str | None,
    warehouse: str | None,
    commodity: str | None,
    quality: str | None,
    quantity: float | None,
):
    """
    Try to locate the StockExit row that was created for a given sale.
    We match on the combination we originally wrote:
    (date, stockist_name, warehouse, commodity, quality, quantity).
    If multiple match (unlikely), return the first.
    """
    q = StockExit.query.filter(
        StockExit.date == when,
        StockExit.stockist_name == (stockist_name or ""),
        StockExit.warehouse == (warehouse or ""),
        StockExit.commodity == (commodity or ""),
        StockExit.quality == (quality or None),
        StockExit.quantity == (quantity or 0.0),
    )
    return q.first()


def _ensure_stockexit_for_sale(sale: BuyerSale):
    """
    Create or update the StockExit row corresponding to this sale.
    Rules:
      • quantity -> sale.quantity
      • net_qty  -> same as quantity (no reduction logic from sale)
      • reduction/rate/cost/handling/net_cost -> 0
      • mobile auto-fills from Stockist by name
    """
    mobile = _stockist_mobile(sale.stockist_name)

    # Try to find an exact match row first
    sx = _find_matching_stockexit(
        when=sale.date,
        stockist_name=sale.stockist_name or "",
        warehouse=sale.warehouse or "",
        commodity=sale.commodity or "",
        quality=sale.quality,
        quantity=sale.quantity,
    )

    if not sx:
        sx = StockExit(
            date=sale.date,
            warehouse=sale.warehouse or "",
            stockist_name=sale.stockist_name or "",
            mobile=mobile,
            commodity=sale.commodity or "",
            quantity=sale.quantity,
            reduction=0.0,
            net_qty=sale.quantity,
            rate=0.0,
            cost=0.0,
            handling=0.0,
            net_cost=0.0,
            quality=sale.quality,
        )
        db.session.add(sx)
    else:
        # Update fields that could have changed
        sx.date = sale.date
        sx.warehouse = sale.warehouse or ""
        sx.stockist_name = sale.stockist_name or ""
        sx.mobile = mobile
        sx.commodity = sale.commodity or ""
        sx.quantity = sale.quantity
        sx.reduction = 0.0
        sx.net_qty = sale.quantity
        sx.rate = 0.0
        sx.cost = 0.0
        sx.handling = 0.0
        sx.net_cost = 0.0
        sx.quality = sale.quality

    # No commit here; caller decides


def _delete_stockexit_for_sale(sale: BuyerSale):
    """Delete the StockExit row that matches the sale's current values (best-effort)."""
    sx = _find_matching_stockexit(
        when=sale.date,
        stockist_name=sale.stockist_name or "",
        warehouse=sale.warehouse or "",
        commodity=sale.commodity or "",
        quality=sale.quality,
        quantity=sale.quantity,
    )
    if sx:
        db.session.delete(sx)


# ---------- routes ----------

@bp.get("/add")
def add_sale_form():
    """Render add form."""
    buyers = Buyer.query.order_by(Buyer.buyer_name.asc()).all()
    stockists = Stockist.query.order_by(Stockist.name.asc()).all()
    today = date.today().strftime("%Y-%m-%d")
    return render_template(
        "buyer/add_sale.html",
        buyers=buyers,
        stockists=stockists,
        now=today,
    )


@bp.post("/add")
def save_sale():
    """Create a sale + mirror a StockExit row."""
    # Required fields
    buyer_id = request.form.get("buyer_id")
    buyer = Buyer.query.get(int(buyer_id)) if buyer_id else None
    if not buyer:
        flash("Please select a valid buyer.", "danger")
        return redirect(url_for("sales.add_sale"))

    sale_date = _parse_date(request.form.get("date"), default=date.today())
    rst_no = (request.form.get("rst_no") or "").strip()
    commodity = (request.form.get("commodity") or "").strip()
    if not rst_no or not commodity:
        flash("RST No and Commodity are required.", "danger")
        return redirect(url_for("sales.add_sale"))

    # Optional / numeric fields
    warehouse = (request.form.get("warehouse") or "").strip()
    quality = (request.form.get("quality") or "").strip() or None
    qty = _q(request.form.get("quantity"))
    rate = _f(request.form.get("rate"))
    handling = _f(request.form.get("handling_charge"))
    cost, net = _compute_costs(qty, rate, handling)

    # NEW: stockist chosen for this sale
    stockist_name = (request.form.get("stockist_name") or "").strip()

    sale = BuyerSale(
        date=sale_date,
        rst_no=rst_no,
        warehouse=warehouse or None,
        buyer_id=buyer.id,
        buyer_name=buyer.buyer_name,
        mobile=buyer.mobile_no,
        commodity=commodity,
        quantity=qty,
        rate=rate,
        cost=cost,
        handling_charge=handling,
        net_cost=net,
        quality=quality,
        stockist_name=stockist_name or None,
    )

    db.session.add(sale)
    db.session.flush()  # have sale.id

    # Mirror StockExit
    _ensure_stockexit_for_sale(sale)

    db.session.commit()
    flash("Sale saved and stock exit recorded.", "success")
    return redirect(url_for("sales.list_sales"))


@bp.get("")
def list_sales():
    """List + filter."""
    buyers = Buyer.query.order_by(Buyer.buyer_name.asc()).all()

    q = BuyerSale.query

    # Filters (match your list_sales.html)
    mobile = request.args.get("mobile") or ""
    commodity = request.args.get("commodity") or ""
    quality = request.args.get("quality") or ""
    warehouse = request.args.get("warehouse") or ""
    d_from = _parse_date(request.args.get("from"))
    d_to = _parse_date(request.args.get("to"))

    if mobile:
        q = q.filter(BuyerSale.mobile == mobile)
    if commodity:
        q = q.filter(BuyerSale.commodity == commodity)
    if quality:
        q = q.filter(BuyerSale.quality == quality)
    if warehouse:
        q = q.filter(BuyerSale.warehouse == warehouse)
    if d_from:
        q = q.filter(BuyerSale.date >= d_from)
    if d_to:
        q = q.filter(BuyerSale.date <= d_to)

    q = q.order_by(BuyerSale.date.desc(), BuyerSale.id.desc())
    sales = q.all()

    return render_template("buyer/list_sales.html", buyers=buyers, sales=sales)


@bp.post("/<int:sale_id>/update")
def update_sale(sale_id: int):
    """
    Inline update from list view. Recomputes cost/net_cost and keeps
    the StockExit row in sync (best-effort match by old values).
    """
    sale = BuyerSale.query.get_or_404(sale_id)

    # Keep a snapshot of OLD values for locating the StockExit row
    old = dict(
        date=sale.date,
        warehouse=sale.warehouse or "",
        stockist_name=sale.stockist_name or "",
        commodity=sale.commodity or "",
        quality=sale.quality,
        quantity=sale.quantity,
    )

    # Apply edits
    sale.date = _parse_date(request.form.get("date"), default=sale.date) or sale.date
    sale.rst_no = (request.form.get("rst_no") or sale.rst_no).strip()
    sale.commodity = (request.form.get("commodity") or sale.commodity).strip()
    sale.quality = (request.form.get("quality") or None)
    sale.warehouse = (request.form.get("warehouse") or "").strip() or None

    qty = _q(request.form.get("quantity"))
    rate = _f(request.form.get("rate"))
    handling = _f(request.form.get("handling_charge"))
    sale.quantity = qty
    sale.rate = rate
    sale.cost, sale.net_cost = _compute_costs(qty, rate, handling)
    sale.handling_charge = handling

    # Update StockExit:
    # 1) Try to find using the OLD fingerprint and update it to the NEW values.
    sx = _find_matching_stockexit(
        when=old["date"],
        stockist_name=old["stockist_name"],
        warehouse=old["warehouse"],
        commodity=old["commodity"],
        quality=old["quality"],
        quantity=old["quantity"],
    )

    # Ensure we have stockist_name persisted (if you decide to make it editable later, pull from form)
    stockist_name = sale.stockist_name or (request.form.get("stockist_name") or None)
    sale.stockist_name = stockist_name

    mobile = _stockist_mobile(sale.stockist_name)

    if sx:
        sx.date = sale.date
        sx.warehouse = sale.warehouse or ""
        sx.stockist_name = sale.stockist_name or ""
        sx.mobile = mobile
        sx.commodity = sale.commodity or ""
        sx.quantity = sale.quantity
        sx.reduction = 0.0
        sx.net_qty = sale.quantity
        sx.rate = 0.0
        sx.cost = 0.0
        sx.handling = 0.0
        sx.net_cost = 0.0
        sx.quality = sale.quality
    else:
        # If not found, create a fresh row with the NEW values
        _ensure_stockexit_for_sale(sale)

    db.session.commit()
    flash("Sale updated.", "success")
    return redirect(url_for("sales.list_sales"))


@bp.post("/<int:sale_id>/delete")
def delete_sale(sale_id: int):
    """
    Delete a sale and its mirrored StockExit (best-effort by current values).
    """
    sale = BuyerSale.query.get_or_404(sale_id)
    _delete_stockexit_for_sale(sale)

    db.session.delete(sale)
    db.session.commit()
    flash("Sale deleted.", "success")
    return redirect(url_for("sales.list_sales"))

