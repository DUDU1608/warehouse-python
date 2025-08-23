# app/routes/company/invoice.py
from __future__ import annotations

from flask import (
    Blueprint, render_template, request, redirect,
    url_for, flash, send_file
)
from io import BytesIO
from datetime import datetime
from sqlalchemy import func

from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.lib.units import mm
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Spacer
from reportlab.lib.styles import getSampleStyleSheet

from app import db
from app.models import Buyer, Invoice, InvoiceItem

bp = Blueprint("invoice", __name__, url_prefix="/company/invoice")

# --- Company header (per spec) ---
CO_NAME = "Shree Anunay Agro Pvt Ltd"
CO_ADDR = "Dalsingsarai, Samastipur"
CO_MOBILE = "9771899097 / 6299176297"
CO_EMAIL = "skchy@anunayagro.co.in"
CO_WEBSITE = "www.shreeanunayagro.com"
CO_GSTIN = "10ABOCS8567L1ZO"


def _next_invoice_no() -> int:
    """Return next invoice number (max + 1)."""
    max_no = db.session.query(func.max(Invoice.invoice_no)).scalar()
    return (max_no or 0) + 1


@bp.get("/new")
def new_invoice():
    buyers = Buyer.query.order_by(Buyer.buyer_name.asc()).all()
    return render_template(
        "company/invoice_form.html",
        buyers=buyers,
        invoice_no=_next_invoice_no(),
        today=datetime.today().strftime("%Y-%m-%d"),
    )


@bp.post("/new")
def create_invoice():
    # Validate buyer
    try:
        buyer_id = int(request.form.get("buyer_id"))
    except Exception:
        flash("Please select a valid customer.", "danger")
        return redirect(url_for("invoice.new_invoice"))

    buyer = Buyer.query.get(buyer_id)
    if not buyer:
        flash("Customer not found.", "danger")
        return redirect(url_for("invoice.new_invoice"))

    # Server-side invoice number
    invoice_no = _next_invoice_no()

    # Date
    date_str = request.form.get("date") or datetime.today().strftime("%Y-%m-%d")
    try:
        inv_date = datetime.strptime(date_str, "%Y-%m-%d").date()
    except Exception:
        flash("Invalid date.", "danger")
        return redirect(url_for("invoice.new_invoice"))

    # Meta fields
    vehicle_no = (request.form.get("vehicle_no") or "").strip()
    driver_no  = (request.form.get("driver_no") or "").strip()
    address    = (request.form.get("address") or buyer.address or "").strip()

    # Line items
    descs  = request.form.getlist("item_desc[]")
    prices = request.form.getlist("item_price[]")
    qtys   = request.form.getlist("item_qty[]")

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

    # Taxes are always zero as per spec
    cgst = 0.0
    sgst = 0.0
    sub_total = grand_total - cgst - sgst

    inv = Invoice(
        invoice_no=invoice_no,
        date=inv_date,
        buyer_id=buyer.id,
        customer_name=buyer.buyer_name,
        address=address,
        vehicle_no=vehicle_no,
        driver_no=driver_no,
        cgst=cgst,
        sgst=sgst,
        grand_total=round(grand_total, 2),
        sub_total=round(sub_total, 2),  # NOTE: sub_total (with underscore)
    )
    db.session.add(inv)
    db.session.flush()  # obtain inv.id

    for it in items:
        it.invoice_id = inv.id
        db.session.add(it)

    db.session.commit()
    flash(f"Invoice #{invoice_no} created.", "success")
    return redirect(url_for("invoice.pdf", invoice_id=inv.id))


@bp.get("/list")
def list_invoices():
    invoices = Invoice.query.order_by(Invoice.date.desc(), Invoice.invoice_no.desc()).limit(300).all()
    return render_template("company/invoice_list.html", invoices=invoices)


def _build_invoice_pdf(inv: Invoice, items: list[InvoiceItem]) -> BytesIO:
    """Create invoice PDF and return as BytesIO."""
    buf = BytesIO()
    doc = SimpleDocTemplate(
        buf, pagesize=A4,
        leftMargin=20*mm, rightMargin=20*mm, topMargin=20*mm, bottomMargin=15*mm
    )
    elements = []
    styles = getSampleStyleSheet()

    # Company Header (top line is orange)
    header_data = [
        [CO_NAME],
        [CO_ADDR],
        [f"Mobile: {CO_MOBILE}"],
        [f"Email: {CO_EMAIL} | Website: {CO_WEBSITE}"],
        [f"GSTIN: {CO_GSTIN}"],
    ]
    header_tbl = Table(header_data, colWidths=[170*mm])
    header_tbl.setStyle(TableStyle([
        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#E67E22")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTSIZE", (0, 0), (-1, -1), 10),
        ("BOTTOMPADDING", (0, 0), (-1, 0), 8),
        ("TOPPADDING", (0, 1), (-1, -1), 2),
        ("BOTTOMPADDING", (0, 1), (-1, -1), 2),
    ]))
    elements.append(header_tbl)
    elements.append(Spacer(1, 8))

    # Invoice / Customer block
    meta = [
        ["Customer Name", inv.customer_name],
        ["Invoice No", str(inv.invoice_no)],
        ["Invoice Date", inv.date.strftime("%d-%m-%Y")],
        ["Vehicle No", inv.vehicle_no or ""],
        ["Driver No", inv.driver_no or ""],
        ["Address", inv.address or ""],
    ]
    meta_tbl = Table(meta, colWidths=[35*mm, 135*mm])
    meta_tbl.setStyle(TableStyle([
        ("GRID", (0, 0), (-1, -1), 0.5, colors.black),
        ("BACKGROUND", (0, 0), (0, -1), colors.lightgrey),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("FONTSIZE", (0, 0), (-1, -1), 9.5),
    ]))
    elements.append(meta_tbl)
    elements.append(Spacer(1, 10))

    # Items table
    data = [["SL NO", "DESCRIPTIONS OF GOODS", "PRICE", "QTY (Quintal)", "AMOUNT"]]
    for idx, it in enumerate(items, start=1):
        data.append([
            str(idx),
            it.description,
            f"{(it.price or 0):.2f}",
            f"{(it.qty or 0):g}",
            f"{(it.amount or 0):.2f}",
        ])
    items_tbl = Table(data, colWidths=[15*mm, 85*mm, 25*mm, 30*mm, 30*mm])
    items_tbl.setStyle(TableStyle([
        ("GRID", (0, 0), (-1, -1), 0.5, colors.black),
        ("BACKGROUND", (0, 0), (-1, 0), colors.lightgrey),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("ALIGN", (2, 1), (2, -1), "RIGHT"),
        ("ALIGN", (3, 1), (3, -1), "RIGHT"),
        ("ALIGN", (4, 1), (4, -1), "RIGHT"),
        ("FONTSIZE", (0, 0), (-1, -1), 9.5),
    ]))
    elements.append(items_tbl)
    elements.append(Spacer(1, 10))

    # Totals
    cgst = inv.cgst or 0.0
    sgst = inv.sgst or 0.0
    sub_total = inv.sub_total if inv.sub_total is not None else (inv.grand_total - cgst - sgst)

    totals = [
        ["G. TOTAL", f"{(inv.grand_total or 0):.2f}"],
        ["C. GST - %", f"{cgst:.2f}"],
        ["S. GST - %", f"{sgst:.2f}"],
        ["S. TOTAL", f"{(sub_total or 0):.2f}"],
    ]
    totals_tbl = Table(totals, colWidths=[40*mm, 30*mm])
    totals_tbl.setStyle(TableStyle([
        ("GRID", (0, 0), (-1, -1), 0.5, colors.black),
        ("BACKGROUND", (0, 0), (0, -1), colors.whitesmoke),
        ("ALIGN", (1, 0), (1, -1), "RIGHT"),
        ("FONTNAME", (0, 3), (-1, 3), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 9.5),
    ]))
    # right-align block by wrapping in a 2-col table
    right_wrap = Table([[Spacer(1, 1), totals_tbl]], colWidths=[100*mm, 70*mm])
    right_wrap.setStyle(TableStyle([("ALIGN", (1, 0), (1, 0), "RIGHT")]))
    elements.append(right_wrap)

    doc.build(elements)
    buf.seek(0)
    return buf


@bp.get("/<int:invoice_id>/pdf")
def pdf(invoice_id: int):
    from io import BytesIO
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.units import mm
    from reportlab.lib import colors
    from reportlab.platypus import (
        SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
    )
    from reportlab.lib.styles import getSampleStyleSheet

    inv: Invoice | None = Invoice.query.get(invoice_id)
    if not inv:
        flash("Invoice not found.", "danger")
        return redirect(url_for("invoice.list_invoices"))

    items = InvoiceItem.query.filter_by(invoice_id=inv.id).all()

    # --- PDF doc (margins leave space for the header band we draw) ---
    buf = BytesIO()
    doc = SimpleDocTemplate(
        buf,
        pagesize=A4,
        leftMargin=18 * mm,
        rightMargin=18 * mm,
        topMargin=48 * mm,     # header area
        bottomMargin=20 * mm,
        title=f"Invoice {inv.invoice_no}",
    )
    styles = getSampleStyleSheet()
    story = []

    # ---------- Meta block ----------
    meta = [
        ["CUSTOMER NAME", inv.customer_name, "INVOICE", f"No: {inv.invoice_no}"],
        ["INVOICE DATE", inv.date.strftime("%d-%m-%Y"), "Driver No", inv.driver_no or ""],
        ["Vehicle No", inv.vehicle_no or "", "Address", inv.address or ""],
    ]
    meta_tbl = Table(meta, colWidths=[30*mm, 75*mm, 25*mm, None])
    meta_tbl.setStyle(TableStyle([
        ("BOX", (0,0), (-1,-1), 0.8, colors.black),
        ("INNERGRID", (0,0), (-1,-1), 0.3, colors.black),
        ("BACKGROUND", (0,0), (0,-1), colors.whitesmoke),
        ("BACKGROUND", (2,0), (2,-1), colors.whitesmoke),
        ("VALIGN", (0,0), (-1,-1), "MIDDLE"),
        ("FONTNAME", (0,0), (-1,-1), "Helvetica"),
        ("FONTNAME", (0,0), (-1,0), "Helvetica-Bold"),
        ("LEFTPADDING", (0,0), (-1,-1), 6),
        ("RIGHTPADDING", (0,0), (-1,-1), 6),
        ("TOPPADDING", (0,0), (-1,-1), 5),
        ("BOTTOMPADDING", (0,0), (-1,-1), 5),
    ]))
    story.append(meta_tbl)
    story.append(Spacer(1, 6 * mm))

    # ---------- Items table ----------
    data = [["SL NO", "DESCRIPTIONS OF GOODS", "PRICE (₹/Qt)", "QTY (Quintal)", "AMOUNT (₹)"]]
    for idx, it in enumerate(items, start=1):
        data.append([
            str(idx),
            it.description,
            f"{it.price:.2f}",
            f"{it.qty:g}",
            f"{it.amount:.2f}",
        ])

    item_tbl = Table(
        data,
        colWidths=[12*mm, None, 30*mm, 30*mm, 32*mm],
        repeatRows=1
    )

    # zebra striping for readability
    style_cmds = [
        ("GRID", (0,0), (-1,-1), 0.4, colors.black),
        ("BACKGROUND", (0,0), (-1,0), colors.lightgrey),
        ("FONTNAME", (0,0), (-1,0), "Helvetica-Bold"),
        ("VALIGN", (0,0), (-1,-1), "MIDDLE"),
        ("LEFTPADDING", (0,0), (-1,-1), 5),
        ("RIGHTPADDING", (0,0), (-1,-1), 5),
        ("TOPPADDING", (0,0), (-1,-1), 4),
        ("BOTTOMPADDING", (0,0), (-1,-1), 4),
        ("ALIGN", (2,1), (2,-1), "RIGHT"),
        ("ALIGN", (3,1), (3,-1), "RIGHT"),
        ("ALIGN", (4,1), (4,-1), "RIGHT"),
    ]
    for r in range(1, len(data)):
        if r % 2 == 0:
            style_cmds.append(("BACKGROUND", (0, r), (-1, r), colors.whitesmoke))
    item_tbl.setStyle(TableStyle(style_cmds))
    story.append(item_tbl)
    story.append(Spacer(1, 6 * mm))

    # ---------- Totals (right aligned box) ----------
    totals = [
        ["G. TOTAL", f"{inv.grand_total:.2f}"],
        ["C. GST - %", f"{inv.cgst:.2f}"],
        ["S. GST - %", f"{inv.sgst:.2f}"],
        ["S. TOTAL", f"{inv.sub_total:.2f}"],
    ]
    totals_tbl = Table(totals, colWidths=[40*mm, 35*mm], hAlign="RIGHT")
    totals_tbl.setStyle(TableStyle([
        ("GRID", (0,0), (-1,-1), 0.4, colors.black),
        ("BACKGROUND", (0,0), (0,-1), colors.whitesmoke),
        ("FONTNAME", (0,0), (-1,-1), "Helvetica"),
        ("FONTNAME", (0,3), (-1,3), "Helvetica-Bold"),
        ("ALIGN", (1,0), (1,-1), "RIGHT"),
        ("LEFTPADDING", (0,0), (-1,-1), 6),
        ("RIGHTPADDING", (0,0), (-1,-1), 6),
        ("TOPPADDING", (0,0), (-1,-1), 4),
        ("BOTTOMPADDING", (0,0), (-1,-1), 4),
    ]))
    story.append(totals_tbl)
    story.append(Spacer(1, 4 * mm))

    # ---------- Amount in words + signature ----------
    try:
        words = _amount_to_words_rupees(inv.grand_total)  # uses helper in your file
    except NameError:
        words = f"{inv.grand_total:.2f}"
    story.append(Paragraph(f"<b>Amount in words:</b> {words}", styles["Normal"]))
    story.append(Spacer(1, 10 * mm))
    story.append(Paragraph("For <b>Shree Anunay Agro Pvt Ltd</b><br/>Authorized Signatory", styles["Normal"]))

    # ---------- Header/Footer drawing ----------
    def _draw_header_footer(canv, doc_):
        width, height = A4
        canv.saveState()

        # Header band
        band_h = 22 * mm
        canv.setFillColorRGB(0.95, 0.45, 0.0)
        canv.rect(18*mm, height - 30*mm, width - 36*mm, band_h, stroke=0, fill=1)
        canv.setFillColor(colors.white)
        canv.setFont("Helvetica-Bold", 16)
        canv.drawCentredString(width / 2, height - 22*mm, CO_NAME)

        # Company info
        canv.setFillColor(colors.black)
        canv.setFont("Helvetica", 9)
        y = height - 36*mm
        canv.drawString(20*mm, y, CO_ADDR); y -= 4.2*mm
        canv.drawString(20*mm, y, f"Mobile: {CO_MOBILE}"); y -= 4.2*mm
        canv.drawString(20*mm, y, f"Email: {CO_EMAIL} | Website: {CO_WEBSITE}"); y -= 4.2*mm
        canv.drawString(20*mm, y, f"GSTIN: {CO_GSTIN}")

        # Footer page number
        canv.setFont("Helvetica", 8)
        canv.drawRightString(width - 18*mm, 12*mm, f"Page {doc_.page}")
        canv.restoreState()

    doc.build(story, onFirstPage=_draw_header_footer, onLaterPages=_draw_header_footer)

    buf.seek(0)
    return send_file(buf, mimetype="application/pdf", as_attachment=True,
                     download_name=f"invoice_{inv.invoice_no}.pdf")

