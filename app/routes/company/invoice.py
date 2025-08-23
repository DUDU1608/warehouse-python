# app/routes/company/invoice.py
from __future__ import annotations

from flask import Blueprint, render_template, request, redirect, url_for, flash, send_file, current_app
from io import BytesIO
from datetime import datetime
from sqlalchemy import func
from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.lib.units import mm
from reportlab.pdfgen import canvas
from reportlab.platypus import Table, TableStyle

from app import db
from app.models import Buyer, Invoice, InvoiceItem

bp = Blueprint("invoice", __name__, url_prefix="/company/invoice")

# --- Company static header info (per your spec) ---
CO_NAME = "Shree Anunay Agro Pvt Ltd"
CO_ADDR = "Dalsingsarai, Samastipur"
CO_MOBILE = "9771899097 / 6299176297"
CO_EMAIL = "skchy@anunayagro.co.in"
CO_WEBSITE = "www.shreeanunayagro.com"
CO_GSTIN = "10ABOCS8567L1ZO"

def _next_invoice_no() -> int:
    max_no = db.session.query(func.max(Invoice.invoice_no)).scalar()
    return (max_no or 0) + 1

@bp.get("/new")
def new_invoice():
    buyers = Buyer.query.order_by(Buyer.buyer_name.asc()).all()
    invoice_no = _next_invoice_no()
    today = datetime.today().strftime("%Y-%m-%d")
    return render_template("company/invoice_form.html", buyers=buyers, invoice_no=invoice_no, today=today)

@bp.post("/new")
def create_invoice():
    try:
        buyer_id = int(request.form.get("buyer_id"))
    except Exception:
        flash("Please select a valid customer.", "danger")
        return redirect(url_for("invoice.new_invoice"))

    buyer = Buyer.query.get(buyer_id)
    if not buyer:
        flash("Customer not found.", "danger")
        return redirect(url_for("invoice.new_invoice"))

    # Auto-increment invoice number
    invoice_no = _next_invoice_no()

    # Basic fields
    date_str = request.form.get("date") or datetime.today().strftime("%Y-%m-%d")
    try:
        inv_date = datetime.strptime(date_str, "%Y-%m-%d").date()
    except Exception:
        flash("Invalid date.", "danger")
        return redirect(url_for("invoice.new_invoice"))

    vehicle_no = (request.form.get("vehicle_no") or "").strip()
    driver_no  = (request.form.get("driver_no") or "").strip()
    address    = (request.form.get("address") or buyer.address or "").strip()

    # Items (arrays)
    descs = request.form.getlist("item_desc[]")
    prices = request.form.getlist("item_price[]")
    qtys = request.form.getlist("item_qty[]")

    items: list[InvoiceItem] = []
    grand_total = 0.0
    for i in range(len(descs)):
        d = (descs[i] or "").strip()
        if not d:
            continue
        try:
            p = float(prices[i] or 0)
            q = float(qtys[i] or 0)
        except Exception:
            continue
        amount = round(p * q, 2)
        grand_total += amount
        items.append(InvoiceItem(description=d, price=p, qty=q, amount=amount))

    if not items:
        flash("Add at least one line item.", "danger")
        return redirect(url_for("invoice.new_invoice"))

    cgst = 0.0
    sgst = 0.0
    sub_total = grand_total - cgst - sgst

    inv = Invoice(
        invoice_no=invoice_no,
        date=inv_date,
        buyer_id=buyer.id,
        customer_name=buyer.buyer_name,
        vehicle_no=vehicle_no,
        driver_no=driver_no,
        address=address,
        cgst=cgst,
        sgst=sgst,
        grand_total=round(grand_total, 2),
        sub_total=round(sub_total, 2),
    )
    db.session.add(inv)
    db.session.flush()  # get inv.id

    for it in items:
        it.invoice_id = inv.id
        db.session.add(it)

    db.session.commit()
    flash(f"Invoice #{invoice_no} created.", "success")
    return redirect(url_for("invoice.pdf", invoice_id=inv.id))

@bp.get("/<int:invoice_id>/pdf")
def pdf(invoice_id: int):
    inv: Invoice | None = Invoice.query.get(invoice_id)
    if not inv:
        flash("Invoice not found.", "danger")
        return redirect(url_for("invoice.new_invoice"))

    buf = BytesIO()
    c = canvas.Canvas(buf, pagesize=A4)
    width, height = A4

    # --- Header band (orange) ---
    band_h = 25 * mm
    c.setFillColorRGB(0.95, 0.45, 0.0)  # orange
    c.rect(20*mm, height - 30*mm, width - 40*mm, band_h, stroke=0, fill=1)
    c.setFillColor(colors.white)
    c.setFont("Helvetica-Bold", 18)
    c.drawCentredString(width/2, height - 22*mm, CO_NAME)

    # --- Company info ---
    y = height - 35*mm
    c.setFillColor(colors.black)
    c.setFont("Helvetica", 10)
    c.drawString(22*mm, y, CO_ADDR); y -= 5*mm
    c.drawString(22*mm, y, f"Mobile: {CO_MOBILE}"); y -= 5*mm
    c.drawString(22*mm, y, f"Email: {CO_EMAIL}"); y -= 5*mm
    c.drawString(22*mm, y, f"Website: {CO_WEBSITE}"); y -= 5*mm
    c.drawString(22*mm, y, f"GSTIN: {CO_GSTIN}")

    # --- Invoice meta box ---
    meta_data = [
        ["CUSTOMER NAME", inv.customer_name, "INVOICE", f"No: {inv.invoice_no}"],
        ["INVOICE DATE", inv.date.strftime("%d-%m-%Y"), "Driver No", inv.driver_no or ""],
        ["Vehicle No", inv.vehicle_no or "", "Address", inv.address or ""],
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

    # --- Items table ---
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

    # --- Totals box (CGST/SGST always 0) ---
    g_total = inv.grand_total
    cgst = inv.cgst
    sgst = inv.sgst
    s_total = inv.sub_total

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
