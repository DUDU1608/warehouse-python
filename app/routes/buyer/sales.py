# app/routes/buyer/sales.py
from __future__ import annotations

from datetime import date, datetime
from flask import Blueprint, render_template, request, redirect, url_for, flash
from sqlalchemy import func
from app import db
from app.models import (
    Buyer, BuyerSale, BuyerPayment,
    Stockist, StockExit, StockData, StockistLoanRepayment
)

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
    """Find StockExit row corresponding to a sale (best effort)."""
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
    """Create or update StockExit row mirroring BuyerSale."""
    mobile = _stockist_mobile(sale.stockist_name)

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
            rate=sale.rate,
            cost=sale.cost,
            handling=sale.handling_charge,
            net_cost=sale.net_cost,
            quality=sale.quality,
        )
        db.session.add(sx)
    else:
        sx.date = sale.date
        sx.warehouse = sale.warehouse or ""
        sx.stockist_name = sale.stockist_name or ""
        sx.mobile = mobile
        sx.commodity = sale.commodity or ""
        sx.quantity = sale.quantity
        sx.reduction = 0.0
        sx.net_qty = sale.quantity
        sx.rate = sale.rate
        sx.cost = sale.cost
        sx.handling = sale.handling_charge
        sx.net_cost = sale.net_cost
        sx.quality = sale.quality


def _delete_stockexit_for_sale(sale: BuyerSale):
    """Delete StockExit row matching a sale (best effort)."""
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


def _avg_price_anunay(commodity: str | None, quality: str | None) -> float:
    """
    Weighted average price for ANUNAY AGRO from StockData:
        avg_price = (sum(cost) / sum(quantity))
    Returns 0.0 if no data.
    """
    if not commodity:
        return 0.0

    q = StockData.query.filter(
        StockData.stockist_name == "ANUNAY AGRO",
        StockData.commodity == commodity
    )
    # Match quality exactly as stored (None vs string)
    if quality is None:
        q = q.filter(StockData.quality.is_(None))
    else:
        q = q.filter(StockData.quality == quality)

    total_qty, total_cost = q.with_entities(
        func.coalesce(func.sum(StockData.quantity), 0.0),
        func.coalesce(func.sum(StockData.cost), 0.0),
    ).first() or (0.0, 0.0)

    if not total_qty or float(total_qty) == 0.0:
        return 0.0
    return float(total_cost) / float(total_qty)


# ---- Repayment helpers (ANUNAY AGRO only) ----
def _is_anunay(name: str | None) -> bool:
    return (name or "").strip().upper() == "ANUNAY AGRO"


def _repayment_amount_for_sale(sale: BuyerSale) -> float:
    avg_price = _avg_price_anunay(sale.commodity, sale.quality)
    return round((sale.quantity or 0.0) * avg_price, 2)


def _find_repayment_for_sale(
    when: date,
    warehouse: str | None,
    commodity: str | None,
    stockist_name: str | None,
):
    """
    Try to find a repayment row for this sale.
    We intentionally do NOT include amount in the fingerprint because it
    may change when the sale is edited.
    """
    return StockistLoanRepayment.query.filter(
        StockistLoanRepayment.date == when,
        StockistLoanRepayment.warehouse == (warehouse or ""),
        StockistLoanRepayment.commodity == (commodity or ""),
        StockistLoanRepayment.stockist_name == (stockist_name or ""),
    ).first()


def _ensure_repayment_for_sale(sale: BuyerSale):
    """Create or update repayment (ANUNAY AGRO only)."""
    if not _is_anunay(sale.stockist_name):
        return

    amount = _repayment_amount_for_sale(sale)
    if amount <= 0:
        # If a zero/negative computed amount, remove any existing repayment
        rep = _find_repayment_for_sale(sale.date, sale.warehouse, sale.commodity, "ANUNAY AGRO")
        if rep:
            db.session.delete(rep)
        return

    rep = _find_repayment_for_sale(sale.date, sale.warehouse, sale.commodity, "ANUNAY AGRO")
    if not rep:
        rep = StockistLoanRepayment(
            date=sale.date,
            warehouse=sale.warehouse or "",
            commodity=sale.commodity or "",
            stockist_name="ANUNAY AGRO",
            amount=amount,
        )
        db.session.add(rep)
    else:
        rep.date = sale.date
        rep.warehouse = sale.warehouse or ""
        rep.commodity = sale.commodity or ""
        rep.stockist_name = "ANUNAY AGRO"
        rep.amount = amount


def _delete_repayment_for_sale(sale: BuyerSale):
    """Delete repayment row for this sale (best effort)."""
    rep = _find_repayment_for_sale(sale.date, sale.warehouse, sale.commodity, "ANUNAY AGRO")
    if rep:
        db.session.delete(rep)


# ---------- routes ----------
@bp.get("/add")
def add_sale_form():
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

    warehouse = (request.form.get("warehouse") or "").strip()
    quality = (request.form.get("quality") or "").strip() or None
    qty = _q(request.form.get("quantity"))
    rate = _f(request.form.get("rate"))
    handling = _f(request.form.get("handling_charge"))
    cost, net = _compute_costs(qty, rate, handling)
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
    db.session.flush()  # ensure sale.id

    # Mirror StockExit
    _ensure_stockexit_for_sale(sale)
    # Mirror Repayment (ANUNAY AGRO only)
    _ensure_repayment_for_sale(sale)

    db.session.commit()
    flash("Sale saved, stock exit & repayment synced.", "success")
    return redirect(url_for("sales.list_sales"))


@bp.get("")
def list_sales():
    buyers = Buyer.query.order_by(Buyer.buyer_name.asc()).all()
    q = BuyerSale.query

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
    sale = BuyerSale.query.get_or_404(sale_id)

    # Snapshot old values to locate existing child rows
    old = dict(
        date=sale.date,
        warehouse=sale.warehouse or "",
        stockist_name=sale.stockist_name or "",
        commodity=sale.commodity or "",
        quality=sale.quality,
        quantity=sale.quantity,
    )

    # Apply incoming edits
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

    # If stockist_name is editable, capture it; else keep existing
    stockist_name = (request.form.get("stockist_name") or sale.stockist_name or None)
    sale.stockist_name = stockist_name
    mobile = _stockist_mobile(sale.stockist_name)

    # ---- Sync StockExit (update or recreate) ----
    sx = _find_matching_stockexit(
        when=old["date"],
        stockist_name=old["stockist_name"],
        warehouse=old["warehouse"],
        commodity=old["commodity"],
        quality=old["quality"],
        quantity=old["quantity"],
    )
    if sx:
        sx.date = sale.date
        sx.warehouse = sale.warehouse or ""
        sx.stockist_name = sale.stockist_name or ""
        sx.mobile = mobile
        sx.commodity = sale.commodity or ""
        sx.quantity = sale.quantity
        sx.reduction = 0.0
        sx.net_qty = sale.quantity
        sx.rate = sale.rate
        sx.cost = sale.cost
        sx.handling = sale.handling_charge
        sx.net_cost = sale.net_cost
        sx.quality = sale.quality
    else:
        _ensure_stockexit_for_sale(sale)

    # ---- Sync Repayment (ANUNAY AGRO only) ----
    was_anunay = _is_anunay(old["stockist_name"])
    is_anunay = _is_anunay(sale.stockist_name)

    if was_anunay and not is_anunay:
        # Previously had repayment; remove it
        dummy_sale_old = type("S", (), {
            "date": old["date"],
            "warehouse": old["warehouse"],
            "commodity": old["commodity"]
        })()
        _delete_repayment_for_sale(dummy_sale_old)  # delete by old fingerprint
    elif is_anunay:
        # Update existing repayment matching *old* fingerprint, or create if missing
        # First try to find using old fingerprint
        rep = _find_repayment_for_sale(old["date"], old["warehouse"], old["commodity"], "ANUNAY AGRO")
        amount = _repayment_amount_for_sale(sale)
        if amount <= 0:
            if rep:
                db.session.delete(rep)
        else:
            if not rep:
                # Create fresh
                _ensure_repayment_for_sale(sale)
            else:
                # Update in place to new values
                rep.date = sale.date
                rep.warehouse = sale.warehouse or ""
                rep.commodity = sale.commodity or ""
                rep.stockist_name = "ANUNAY AGRO"
                rep.amount = amount

    db.session.commit()
    flash("Sale updated; stock exit & repayment synced.", "success")
    return redirect(url_for("sales.list_sales"))


@bp.post("/<int:sale_id>/delete")
def delete_sale(sale_id: int):
    sale = BuyerSale.query.get_or_404(sale_id)

    # Delete StockExit
    _delete_stockexit_for_sale(sale)

    # Delete repayment (if ANUNAY AGRO)
    if _is_anunay(sale.stockist_name):
        _delete_repayment_for_sale(sale)

    db.session.delete(sale)
    db.session.commit()
    flash("Sale deleted; stock exit & repayment removed.", "success")
    return redirect(url_for("sales.list_sales"))
