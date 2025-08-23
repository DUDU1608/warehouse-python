# app/routes/company/invoice.py
from __future__ import annotations

from io import BytesIO
from datetime import datetime, date
from typing import Dict, Any

from flask import (
    Blueprint, render_template, request, redirect,
    url_for, flash, send_file
)
from sqlalchemy import func

from app import db
from app.models import Buyer, Invoice, InvoiceItem  # using your existing models

bp = Blueprint("invoice", __name__, url_prefix="/company/invoice")

# --- Company static header info (per your spec) ---
CO_NAME = "Shree Anunay Agro Pvt Ltd"
CO_ADDR = "Dalsingsarai, Samastipur"
CO_MOBILE = "9771899097 / 6299176297"
CO_EMAIL = "skchy@anunayagro.co.in"
CO_WEBSITE = "www.shreeanunayagro.com"
CO_GSTIN = "10ABOCS8567L1ZO"


# ----------------- Helpers -----------------
def _next_invoice_no() -> int:
    """Next invoice number starting from 1."""
    max_no = db.session.query(func.max(Invoice.invoice_no)).scalar()
    return int(max_no or 0) + 1


def _parse_float(x, default=0.0) -> float:
    try:
        return float((x or "").strip() or default)
    except Exception:
        return default


def _parse_date(s: str) -> date:
    return datetime.strptime(s, "%Y-%m-%d").date()


# ----------------- Routes -----------------
@bp.get("/new")
def new_invoice():
    buyers = Buyer.query.order_by(Buyer.buyer_name.asc()).all()
    return render_template(
        "company/invoice_form.html",
        buyers=buyers,
        invoice_no=_next_invoice_no(),
        today=date.today().isoformat(),
    )


@bp.post("/new")
def create_invoice():
    # Customer
    try:
        buyer_id = int(request.form.get("buyer_id"))
    except Exception:
        flash("Please select a valid customer.", "danger")
        return redirect(url_for("invoice.new_invoice"))

    buyer = Buyer.query.get(buyer_id)
    if not buyer:
        flash("Customer not found.", "danger")
        return redirect(url_for("invoice.new_invoice"))

    # Basics
    date_str = request.form.get("date") or date.today().isoformat()
    try:
        inv_date = _parse_date(date_str)
    except Exception:
        flash("Invalid date.", "danger")
        return redirect(url_for("invoice.new_invoice"))

    vehicle_no = (request.form.get("vehicle_no") or "").strip()
    driver_no = (request.form.get("driver_no") or "").strip()
    address = (request.form.get("address") or buyer.address or "").strip()

    # Line items (arrays)
    descs = request.form.getlist("item_desc[]")
    prices = request.form.getlist("item_price[]")
    qtys = request.form.getlist("item_qty[]")

    items: list[InvoiceItem] = []
    subtotal = 0.0
    for i in range(len(descs)):
        desc = (descs[i] or "").strip()
        if not desc:
            continue
        price = _parse_float(prices[i] if i < len(prices) else 0.0)
        qty = _parse_float(qtys[i] if i < len(qtys) else 0.0)
        amount = round(price * qty, 2)
        if amount <= 0:
            continue
        subtotal += amount
        items.append(InvoiceItem(description=desc, price=price, qty=qty, amount=amount))

    if not items:
        flash("Add at least one line item.", "danger")
        return redirect(url_for("invoice.new_invoice"))

    cgst = 0.0   # per your spec
    sgst = 0.0   # per your spec
    grand_total = round(subtotal + cgst + sgst, 2)

    # Build kwargs compatibly with whatever your Invoice model has
    # (buyer_id vs customer_id, sub_total vs subtotal)
    inv_kwargs: Dict[str, Any] = dict(
        invoice_no=_next_invoice_no(),
        date=inv_date,
        customer_name=buyer.buyer_name,
        vehicle_no=vehicle_no,
        driver_no=driver_no,
        address=address,
        cgst=cgst,
        sgst=sgst,
        grand_total=grand_total,
    )
    if hasattr(Invoice, "buyer_id"):
        inv_kwargs["buyer_id"] = buyer.id
    elif hasattr(Invoice, "customer_id"):
        inv_kwargs["customer_id"] = buyer.id

    if hasattr(Invoice, "sub_total"):
        inv_kwargs["sub_total"] = round(subtotal, 2)
    elif hasattr(Invoice, "subtotal"):
        inv_kwargs["subtotal"] = round(subtotal, 2)

    inv = Invoice(**inv_kwargs)
    db.session.add(inv)
    db.session.flush()  # get inv.id

    for it in items:
        it.invoice_id = inv.id
        db.session.add(it)

    db.session.commit()
    flash(f"Invoice #{inv.invoice_no} created.", "success")
    return redirect(url_for("invoice.pdf", invoice_id=inv.id))


@bp.get("/list")
def list_invoices():
    rows = Invoice.query.order_by(Invoice.date.desc(), Invoice.invoice_no.desc()).all()
    return render_template("company/invoice_list.html", invoices=rows)


@bp.get("/<int:invoice_id>/pdf")
def pdf(invoice_id: int):
    """Generate the PDF with ReportLab if available. Fallback to printable HTML."""
    inv: Invoice | None = Invoice.query.get(invoice_id)
    if not inv:
        flash("Invoice not found.", "danger")
        return redirect(url_for("invoice.new_invoice"))

    # Try importing reportlab here so blueprint registers even if it's missing.
    try:
        from reportlab.lib.pagesizes import A4
        from reportlab.lib import colors
        from reportlab.lib.units import mm
        from reportlab.pdfgen import canvas
        from reportlab.platypus import Table, TableStyle
    except Exception:
        # Fallback to a printable HTML view
        flash("PDF engine (ReportLab) not available on server. Showing printable HTML.", "warning")
        items = InvoiceItem.query.filter_by(invoice_id=inv.id).all()
        return render_template("company/invoice_pdf_fallback.html", inv=inv, items=items)

    # --- Build PDF ---
    buf = BytesIO()
    c = canvas.Canvas(buf, pagesize=A4)
    width, height = A4

    # Header band
    band_h = 25 * mm
    c.setFillColorRGB(0.95, 0.45, 0.0)  # orange
    c.rect(20*mm, height - 30*mm, width - 40*mm, band_h, stroke=0, fill=1)
    c.setFillColor(colors.white)
    c.setFont("Helvetica-Bold", 18)
    c.drawCentredString(width/2, height - 22*mm, CO_NAME)

    # Company info
    y = height - 35*mm
    c.setFillColor(colors.black)
    c.setFont("Helvetica", 10)
    c.drawString(22*mm, y, CO_ADDR); y -= 5*mm
    c.drawString(22*mm, y, f"Mobile: {CO_MOBILE}"); y -= 5*mm
    c.drawString(22*mm, y, f"Email: {CO_EMAIL}"); y -= 5*mm
    c.drawString(22*mm, y, f"Website: {CO_WEBSITE}"); y -= 5*mm
    c.drawString(22*mm, y, f"GSTIN: {CO_GSTIN}")

    # Invoice meta box
    meta_data = [
        ["CUSTOMER NAME", inv.customer_name, "INVOICE", f"No: {inv.invoice_no}"],
        ["INVOICE DATE", inv.date.strftime("%d-%m-%Y"), "Driver No", getattr(inv, "driver_no", "") or ""],
        ["Vehicle No", getattr(inv, "vehicle_no", "") or "", "Address", getattr(inv, "address", "") or ""],
    ]
    t = Table(meta_data, colWidths=[30*mm, 65*mm, 30*mm, 65*mm])
    t.setStyle(TableStyle([
        ("BOX", (0,0), (-1,-1), 0.75, colors.black),
        ("INNERGRID", (0,0), (-1,-1), 0.25, colors.black),
        ("BACKGROUND", (0,0), (0,-1), colors.whitesmoke),
        ("BACKGROUND", (2,0), (2,-1), colors.whitesmoke),
        ("VALIGN", (0,0), (-1,-1), "MIDDLE"),
        ("FONTNAME", (0,0), (-1,0), "Helvetica-Bold"),
    ]))
    t.wrapOn(c, width-40*mm, 0)
    t.drawOn(c, 20*mm, height - 90*mm)

    # Items table
    items = InvoiceItem.query.filter_by(invoice_id=inv.id).all()
    data = [["SL NO", "DESCRIPTIONS OF GOODS", "PRICE", "QTY (Quintal)", "AMOUNT"]]
    for idx, it in enumerate(items, start=1):
        data.append([
            str(idx),
            it.description,
            f"{it.price:.2f}",
            f"{it.qty:g}",
            f"{it.amount:.2f}",
        ])

    tbl = Table(data, colWidths=[15*mm, 85*mm, 25*mm, 30*mm, 30*mm])
    tbl.setStyle(TableStyle([
        ("GRID", (0,0), (-1,-1), 0.5, colors.black),
        ("BACKGROUND", (0,0), (-1,0), colors.lightgrey),
        ("FONTNAME", (0,0), (-1,0), "Helvetica-Bold"),
        ("VALIGN", (0,0), (-1,-1), "MIDDLE"),
    ]))
    tbl.wrapOn(c, width-40*mm, 0)
    tbl_y = height - 180*mm
    tbl.drawOn(c, 20*mm, tbl_y)

    # Totals box
    # Support sub_total or subtotal attribute names
    if hasattr(inv, "sub_total"):
        s_total = float(inv.sub_total or 0.0)
    else:
        s_total = float(getattr(inv, "subtotal", 0.0) or 0.0)

    cgst = float(getattr(inv, "cgst", 0.0) or 0.0)
    sgst = float(getattr(inv, "sgst", 0.0) or 0.0)
    g_total = float(getattr(inv, "grand_total", 0.0) or 0.0)

    totals = [
        ["G. TOTAL", f"{g_total:.2f}"],
        ["C. GST - %", f"{cgst:.2f}"],
        ["S. GST - %", f"{sgst:.2f}"],
        ["S. TOTAL", f"{s_total:.2f}"],
    ]
    t2 = Table(totals, colWidths=[40*mm, 30*mm])
    t2.setStyle(TableStyle([
        ("GRID", (0,0), (-1,-1), 0.5, colors.black),
        ("BACKGROUND", (0,0), (0,-1), colors.whitesmoke),
        ("FONTNAME", (0,0), (-1,-1), "Helvetica"),
        ("FONTNAME", (0,3), (-1,3), "Helvetica-Bold"),
        ("ALIGN", (1,0), (1,-1), "RIGHT"),
    ]))
    t2.wrapOn(c, 0, 0)
    t2.drawOn(c, width - 20*mm - 70*mm, 40*mm)

    c.showPage()
    c.save()
    buf.seek(0)

    filename = f"invoice_{inv.invoice_no}.pdf"
    return send_file(buf, mimetype="application/pdf", as_attachment=True, download_name=filename)
