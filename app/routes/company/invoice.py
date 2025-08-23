# app/routes/company/invoice.py
from __future__ import annotations

from io import BytesIO
from datetime import datetime, date
from typing import Dict, Any

from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.lib.units import mm
from reportlab.platypus import (
    SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, HRFlowable
)
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_LEFT, TA_CENTER, TA_RIGHT

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
    """
    Generate a professional PDF using ReportLab/Platypus with a proper
    header (company details), invoice meta box, items table, and totals.
    Falls back to HTML if reportlab is missing.
    """
    inv: Invoice | None = Invoice.query.get(invoice_id)
    if not inv:
        flash("Invoice not found.", "danger")
        return redirect(url_for("invoice.new_invoice"))

    # Try importing reportlab – fallback to printable HTML if unavailable
    try:
        from reportlab.lib import colors
        from reportlab.platypus import Table, TableStyle
    except Exception:
        items = InvoiceItem.query.filter_by(invoice_id=inv.id).all()
        flash("PDF engine (ReportLab) not available on server. Showing printable HTML.", "warning")
        return render_template("company/invoice_pdf_fallback.html", inv=inv, items=items)

    # ---------- Build PDF with Platypus (auto-layout, no overlap) ----------
    buf = BytesIO()
    doc = SimpleDocTemplate(
        buf,
        pagesize=A4,
        leftMargin=18*mm, rightMargin=18*mm,
        topMargin=16*mm, bottomMargin=16*mm,
        title=f"Invoice #{inv.invoice_no}"
    )

    styles = getSampleStyleSheet()
    styles.add(ParagraphStyle(name="H1White", parent=styles["Heading1"], alignment=TA_CENTER, textColor=colors.white, fontSize=16, spaceAfter=4))
    styles.add(ParagraphStyle(name="MetaKey", parent=styles["Normal"], fontName="Helvetica-Bold"))
    styles.add(ParagraphStyle(name="RightBold", parent=styles["Normal"], alignment=TA_RIGHT, fontName="Helvetica-Bold"))
    styles.add(ParagraphStyle(name="Small", parent=styles["Normal"], fontSize=9))
    styles.add(ParagraphStyle(name="Tiny", parent=styles["Normal"], fontSize=8, textColor=colors.grey))

    els = []

    # -- Header band with company name
    header_band = Table([[Paragraph(CO_NAME, styles["H1White"])]], colWidths=[doc.width])
    header_band.setStyle(TableStyle([
        ("BACKGROUND", (0,0), (-1,-1), colors.HexColor("#E67E22")),  # orange
        ("LEFTPADDING", (0,0), (-1,-1), 6),
        ("RIGHTPADDING", (0,0), (-1,-1), 6),
        ("TOPPADDING", (0,0), (-1,-1), 10),
        ("BOTTOMPADDING", (0,0), (-1,-1), 10),
    ]))
    els += [header_band]

    # -- Company info block in header (address, mobile, email, website, GSTIN)
    co_info = [
        [Paragraph("<b>Address</b>", styles["Small"]), Paragraph(CO_ADDR, styles["Small"])],
        [Paragraph("<b>Mobile</b>", styles["Small"]), Paragraph(CO_MOBILE, styles["Small"])],
        [Paragraph("<b>Email</b>", styles["Small"]), Paragraph(CO_EMAIL, styles["Small"])],
        [Paragraph("<b>Website</b>", styles["Small"]), Paragraph(CO_WEBSITE, styles["Small"])],
        [Paragraph("<b>GSTIN</b>", styles["Small"]), Paragraph(CO_GSTIN, styles["Small"])],
    ]
    co_table = Table(co_info, colWidths=[28*mm, doc.width - 28*mm])
    co_table.setStyle(TableStyle([
        ("BACKGROUND", (0,0), (0,-1), colors.whitesmoke),
        ("BOX", (0,0), (-1,-1), 0.25, colors.lightgrey),
        ("INNERGRID", (0,0), (-1,-1), 0.25, colors.lightgrey),
        ("VALIGN", (0,0), (-1,-1), "MIDDLE"),
        ("LEFTPADDING", (0,0), (-1,-1), 6),
        ("RIGHTPADDING", (0,0), (-1,-1), 6),
        ("TOPPADDING", (0,0), (-1,-1), 4),
        ("BOTTOMPADDING", (0,0), (-1,-1), 4),
    ]))
    els += [Spacer(1, 6), co_table, Spacer(1, 10)]

    # -- Invoice meta (customer + invoice info)
    meta_data = [
        ["CUSTOMER NAME", inv.customer_name, "INVOICE NO.", str(inv.invoice_no)],
        ["INVOICE DATE", inv.date.strftime("%d-%m-%Y"), "DRIVER NO", (getattr(inv, "driver_no", "") or "")],
        ["VEHICLE NO", (getattr(inv, "vehicle_no", "") or ""), "ADDRESS", (getattr(inv, "address", "") or "")],
    ]
    meta = Table(meta_data, colWidths=[30*mm, (doc.width/2 - 30*mm), 30*mm, (doc.width/2 - 30*mm)])
    meta.setStyle(TableStyle([
        ("BOX", (0,0), (-1,-1), 0.6, colors.black),
        ("INNERGRID", (0,0), (-1,-1), 0.4, colors.black),
        ("BACKGROUND", (0,0), (0,-1), colors.whitesmoke),
        ("BACKGROUND", (2,0), (2,-1), colors.whitesmoke),
        ("VALIGN", (0,0), (-1,-1), "MIDDLE"),
        ("FONTNAME", (0,0), (-1,-1), "Helvetica"),
        ("FONTNAME", (0,0), (-1,0), "Helvetica"),
        ("LEFTPADDING", (0,0), (-1,-1), 6),
        ("RIGHTPADDING", (0,0), (-1,-1), 6),
        ("TOPPADDING", (0,0), (-1,-1), 4),
        ("BOTTOMPADDING", (0,0), (-1,-1), 4),
    ]))
    els += [meta, Spacer(1, 10)]

    # -- Items table
    items = InvoiceItem.query.filter_by(invoice_id=inv.id).all()
    data = [["SL NO", "DESCRIPTION OF GOODS", "PRICE", "QTY (Quintal)", "AMOUNT"]]
    for idx, it in enumerate(items, start=1):
        data.append([
            str(idx),
            Paragraph(it.description or "", styles["Small"]),
            f"{(it.price or 0):.2f}",
            f"{(it.qty or 0):g}",
            f"{(it.amount or 0):.2f}",
        ])

    col_widths = [15*mm, doc.width - (15*mm + 25*mm + 30*mm + 30*mm), 25*mm, 30*mm, 30*mm]
    tbl = Table(data, colWidths=col_widths, repeatRows=1)
    tbl.setStyle(TableStyle([
        ("GRID", (0,0), (-1,-1), 0.5, colors.black),
        ("BACKGROUND", (0,0), (-1,0), colors.lightgrey),
        ("FONTNAME", (0,0), (-1,0), "Helvetica-Bold"),
        ("ALIGN", (2,1), (4,-1), "RIGHT"),
        ("VALIGN", (0,0), (-1,-1), "MIDDLE"),
        ("LEFTPADDING", (0,0), (-1,-1), 6),
        ("RIGHTPADDING", (0,0), (-1,-1), 6),
        ("TOPPADDING", (0,0), (-1,-1), 4),
        ("BOTTOMPADDING", (0,0), (-1,-1), 4),
    ]))
    els += [tbl, Spacer(1, 8)]

    # -- Totals (right-aligned small box)
    if hasattr(inv, "sub_total"):
        s_total = float(inv.sub_total or 0.0)
    else:
        s_total = float(getattr(inv, "subtotal", 0.0) or 0.0)

    cgst = float(getattr(inv, "cgst", 0.0) or 0.0)
    sgst = float(getattr(inv, "sgst", 0.0) or 0.0)
    g_total = float(getattr(inv, "grand_total", 0.0) or 0.0)

    totals = [
        ["Subtotal", f"{s_total:.2f}"],
        ["CGST",     f"{cgst:.2f}"],
        ["SGST",     f"{sgst:.2f}"],
        ["Grand Total", f"{g_total:.2f}"],
    ]
    t2 = Table(totals, colWidths=[40*mm, 35*mm], hAlign="RIGHT")
    t2.setStyle(TableStyle([
        ("GRID", (0,0), (-1,-1), 0.5, colors.black),
        ("BACKGROUND", (0,0), (0,-1), colors.whitesmoke),
        ("FONTNAME", (0,0), (-1,-2), "Helvetica"),
        ("FONTNAME", (0,-1), (-1,-1), "Helvetica-Bold"),
        ("ALIGN", (1,0), (1,-1), "RIGHT"),
        ("LEFTPADDING", (0,0), (-1,-1), 6),
        ("RIGHTPADDING", (0,0), (-1,-1), 6),
        ("TOPPADDING", (0,0), (-1,-1), 4),
        ("BOTTOMPADDING", (0,0), (-1,-1), 4),
    ]))
    els += [t2, Spacer(1, 12)]

    # -- Footer / signature
    els += [
        HRFlowable(width="100%", thickness=0.6, color=colors.lightgrey),
        Spacer(1, 6),
        Paragraph("Thank you for your business!", styles["Tiny"]),
        Spacer(1, 10),
        Table(
            [
                ["", f"For {CO_NAME}"],
                ["", ""],
                ["", "(Authorised Signatory)"]
            ],
            colWidths=[doc.width - 60*mm, 60*mm]
        )
    ]

    doc.build(els)
    buf.seek(0)

    filename = f"invoice_{inv.invoice_no}.pdf"
    return send_file(buf, mimetype="application/pdf", as_attachment=True, download_name=filename)

