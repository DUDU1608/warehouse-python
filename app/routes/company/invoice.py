# app/routes/company/invoice.py
from __future__ import annotations

import os
from io import BytesIO
from decimal import Decimal, ROUND_HALF_UP
from datetime import datetime

from flask import (
    Blueprint, current_app, render_template, request,
    redirect, url_for, send_file, flash
)
from sqlalchemy import func

from app import db
from app.models import Buyer, Invoice, InvoiceItem

# -------- ReportLab --------
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas
from reportlab.platypus import Table, TableStyle, Paragraph
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle

bp = Blueprint("invoice", __name__, url_prefix="/company/invoice")

# --- Company static header info ---
CO_NAME = "Shree Anunay Agro Pvt Ltd"
CO_ADDR = "Dalsingsarai, Samastipur"
CO_MOBILE = "9771899097 / 6299176257"
CO_EMAIL = "skchy@anunayagro.co.in"
CO_WEBSITE = "www.shreeanunayagro.com"
CO_GSTIN = "10ABOCS8567L1ZO"

# ---------- helpers ----------
def _next_invoice_no() -> int:
    max_no = db.session.query(func.max(Invoice.invoice_no)).scalar()
    return (max_no or 0) + 1

def _round2(x: float) -> float:
    return float(Decimal(str(x or 0)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))

def _register_rupee_font() -> tuple[str, str, bool]:
    """
    Register a Unicode font that contains the ₹ glyph.
    We look in app/static/fonts first so it works on VPS without apt.
    Returns: (regular_font_name, bold_font_name, supports_rupee)
    """
    # You can bundle these two files in your repo:
    # app/static/fonts/DejaVuSans.ttf
    # app/static/fonts/DejaVuSans-Bold.ttf
    static_dir = os.path.join(current_app.root_path, "static", "fonts")
    local_reg = os.path.join(static_dir, "DejaVuSans.ttf")
    local_bold = os.path.join(static_dir, "DejaVuSans-Bold.ttf")

    # Fallback system paths
    sys_reg = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"
    sys_bold = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"

    reg_path = local_reg if os.path.exists(local_reg) else sys_reg
    bold_path = local_bold if os.path.exists(local_bold) else sys_bold

    try:
        if os.path.exists(reg_path):
            pdfmetrics.registerFont(TTFont("DejaVu", reg_path))
        if os.path.exists(bold_path):
            pdfmetrics.registerFont(TTFont("DejaVu-Bold", bold_path))
        # If we got here with at least regular available, assume ₹ ok
        if os.path.exists(reg_path):
            return "DejaVu", "DejaVu-Bold" if os.path.exists(bold_path) else "DejaVu", True
    except Exception:
        pass

    # Safe fallback (₹ may not render)
    return "Helvetica", "Helvetica-Bold", False

# ---- Amount in words (Indian numbering) ----
ONES = (
    "", "One", "Two", "Three", "Four", "Five", "Six", "Seven", "Eight", "Nine",
    "Ten", "Eleven", "Twelve", "Thirteen", "Fourteen", "Fifteen",
    "Sixteen", "Seventeen", "Eighteen", "Nineteen",
)
TENS = ("", "", "Twenty", "Thirty", "Forty", "Fifty", "Sixty", "Seventy", "Eighty", "Ninety")

def _two_digits(n: int) -> str:
    if n == 0: return ""
    if n < 20: return ONES[n]
    return (TENS[n // 10] + (" " + ONES[n % 10] if n % 10 else "")).strip()

def _three_digits(n: int) -> str:
    s = ""
    if n >= 100:
        s += ONES[n // 100] + " Hundred"
        n %= 100
        if n: s += " "
    s += _two_digits(n)
    return s.strip()

def rupees_in_words(amount: float) -> str:
    amt = Decimal(str(amount or 0)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    rupees = int(amt)
    paise = int((amt - Decimal(rupees)) * 100)

    if rupees == 0:
        words = "Zero"
    else:
        parts = []
        crore = rupees // 10000000; rupees %= 10000000
        lakh  = rupees // 100000;   rupees %= 100000
        thousand = rupees // 1000;  rupees %= 1000
        hundred_part = rupees

        if crore:   parts.append(_two_digits(crore)   + " Crore")
        if lakh:    parts.append(_two_digits(lakh)    + " Lakh")
        if thousand:parts.append(_two_digits(thousand)+ " Thousand")
        if hundred_part: parts.append(_three_digits(hundred_part))
        words = " ".join(parts)

    return (f"{words} Rupees and {_two_digits(paise)} Paise Only"
            if paise else f"{words} Rupees Only")

# ---------- Views ----------
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
    try:
        buyer_id = int(request.form.get("buyer_id"))
    except Exception:
        flash("Please select a valid customer.", "danger")
        return redirect(url_for("invoice.new_invoice"))

    buyer = Buyer.query.get(buyer_id)
    if not buyer:
        flash("Customer not found.", "danger")
        return redirect(url_for("invoice.new_invoice"))

    invoice_no = _next_invoice_no()

    date_str = request.form.get("date") or datetime.today().strftime("%Y-%m-%d")
    try:
        inv_date = datetime.strptime(date_str, "%Y-%m-%d").date()
    except Exception:
        flash("Invalid date.", "danger")
        return redirect(url_for("invoice.new_invoice"))

    vehicle_no = (request.form.get("vehicle_no") or "").strip()
    driver_no  = (request.form.get("driver_no") or "NA").strip()
    address    = (request.form.get("address") or buyer.address or "").strip()

    # gather items
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
        amt = _round2(p * q)
        grand_total += amt
        items.append(InvoiceItem(description=d, price=p, qty=q, amount=amt))

    if not items:
        flash("Add at least one line item.", "danger")
        return redirect(url_for("invoice.new_invoice"))

    cgst = 0.0
    sgst = 0.0
    sub_total = _round2(grand_total - cgst - sgst)

    inv = Invoice(
        invoice_no=invoice_no,
        date=inv_date,
        buyer_id=buyer.id,
        customer_name=buyer.buyer_name,
        vehicle_no=vehicle_no,
        driver_no=driver_no,
        address=address,
        cgst=_round2(cgst),
        sgst=_round2(sgst),
        grand_total=_round2(grand_total),
        sub_total=sub_total,
    )
    db.session.add(inv)
    db.session.flush()  # to get inv.id

    for it in items:
        it.invoice_id = inv.id
        db.session.add(it)

    db.session.commit()
    flash(f"Invoice #{invoice_no} created.", "success")
    return redirect(url_for("invoice.pdf", invoice_id=inv.id))
# list page (endpoint: invoice.list_invoices)

# --- List & view invoices -----------------------------------------------------

@bp.get("/list", endpoint="list_invoices")  # endpoint will be invoice.list_invoices
def list_invoices():
    from app.models import Invoice
    invoices = (
        Invoice.query
        .order_by(Invoice.date.desc(), Invoice.invoice_no.desc())
        .limit(500)
        .all()
    )
    return render_template("company/invoice_list.html", invoices=invoices)

@bp.get("/<int:invoice_id>/pdf")
def pdf(invoice_id: int):
    inv: Invoice | None = Invoice.query.get(invoice_id)
    if not inv:
        flash("Invoice not found.", "danger")
        return redirect(url_for("invoice.new_invoice"))

    font_name, bold_font, has_rupee = _register_rupee_font()
    RUPEE = "₹" if has_rupee else "Rs"

    buf = BytesIO()
    c = canvas.Canvas(buf, pagesize=A4)
    width, height = A4

    # === margins & spacing (same as before) ===
    LEFT, RIGHT, TOP, BOTTOM = 20*mm, 20*mm, 20*mm, 20*mm
    usable_width = width - LEFT - RIGHT
    GAP_BELOW_BAND, GAP_BELOW_META, GAP_BELOW_TBL = 14*mm, 16*mm, 8*mm

    # === header band (unchanged) ===
    band_h = 48*mm
    band_top = height - TOP
    band_bot = band_top - band_h
    c.setFillColorRGB(0.90, 0.45, 0.0)
    c.rect(LEFT, band_bot, usable_width, band_h, stroke=0, fill=1)

    c.setFillColor(colors.white)
    c.setFont(bold_font, 20)
    title_y = band_top - 14*mm
    c.drawCentredString(width/2, title_y, CO_NAME)

    c.setFont(font_name, 10)
    lines = [
        CO_ADDR,
        f"Mobile: {CO_MOBILE}",
        f"Email: {CO_EMAIL} | Website: {CO_WEBSITE}",
        f"GSTIN: {CO_GSTIN}",
    ]
    line_gap = 4.8*mm
    first_line_y = title_y - 7*mm
    for i, txt in enumerate(lines):
        c.drawCentredString(width/2, first_line_y - i*line_gap, txt)

    # === styles & meta table (unchanged) ===
    styles = getSampleStyleSheet()
    wrap   = ParagraphStyle("wrap", parent=styles["Normal"], fontName=font_name, fontSize=10, leading=12, wordWrap="CJK")
    wrap_b = ParagraphStyle("wrap_b", parent=wrap, fontName=bold_font)

    half = usable_width / 2.0
    lbl1, lbl2 = 34*mm, 28*mm
    meta_colwidths = [lbl1, half - lbl1, lbl2, half - lbl2]

    meta_data = [
        [Paragraph("CUSTOMER NAME", wrap_b), Paragraph(inv.customer_name or "", wrap),
         Paragraph("INVOICE", wrap_b),       Paragraph(f"No: {inv.invoice_no}", wrap)],
        [Paragraph("INVOICE DATE", wrap_b),  Paragraph(inv.date.strftime("%d-%m-%Y"), wrap),
         Paragraph("Driver No", wrap_b),     Paragraph(inv.driver_no or "", wrap)],
        [Paragraph("Vehicle No", wrap_b),    Paragraph(inv.vehicle_no or "", wrap),
         Paragraph("Address", wrap_b),       Paragraph(inv.address or "", wrap)],
    ]
    meta = Table(meta_data, colWidths=meta_colwidths)
    meta.setStyle(TableStyle([
        ("BOX", (0,0), (-1,-1), 0.75, colors.black),
        ("INNERGRID", (0,0), (-1,-1), 0.25, colors.black),
        ("BACKGROUND", (0,0), (0,-1), colors.whitesmoke),
        ("BACKGROUND", (2,0), (2,-1), colors.whitesmoke),
        ("VALIGN", (0,0), (-1,-1), "MIDDLE"),
    ]))

    meta_top = band_bot - GAP_BELOW_BAND
    mw, mh = meta.wrap(usable_width, 0)
    meta.drawOn(c, LEFT, meta_top - mh)

    # === items + totals in one table ===
    items = InvoiceItem.query.filter_by(invoice_id=inv.id).all()

    hdr = [
        Paragraph("SL NO", wrap_b),
        Paragraph("DESCRIPTIONS OF GOODS", wrap_b),
        Paragraph(f"PRICE ({RUPEE}/Qt)", wrap_b),
        Paragraph("QTY (Quintal)", wrap_b),
        Paragraph(f"AMOUNT ({RUPEE})", wrap_b),
    ]
    data = [hdr]

    for i, it in enumerate(items, start=1):
        data.append([
            Paragraph(str(i), wrap),
            Paragraph(it.description or "", wrap),
            Paragraph(f"{it.price:,.2f}", wrap),
            Paragraph(f"{it.qty:g}", wrap),
            Paragraph(f"{it.amount:,.2f}", wrap),
        ])

    def _round2(x: float) -> float:
        return round(float(x or 0.0), 2)

    def _tot_row(label: str, value: float, bold=False):
        label_p = Paragraph(label, wrap_b if bold else wrap)
        value_p = Paragraph(f"{_round2(value):,.2f}", wrap_b if bold else wrap)
        return ["", "", "", label_p, value_p]

    data.append(_tot_row("G. TOTAL",  inv.grand_total))
    data.append(_tot_row("C. GST - %", inv.cgst))
    data.append(_tot_row("S. GST - %", inv.sgst))
    data.append(_tot_row("S. TOTAL",  inv.sub_total, bold=True))

    # >>> NEW: "Amount in words" row directly under S. TOTAL (inside the same table)
    words = rupees_in_words(inv.sub_total or inv.grand_total or 0.0)
    words_para = Paragraph(f"Amount in words: {words}", wrap)
    data.append([words_para, "", "", "", ""])  # placeholders will be spanned

    # column widths as proportions of usable width
    col_widths = [
        usable_width * 0.08,  # SL NO
        usable_width * 0.36,  # DESCRIPTION
        usable_width * 0.18,  # PRICE
        usable_width * 0.20,  # QTY
        usable_width * 0.18,  # AMOUNT
    ]
    tbl = Table(data, colWidths=col_widths, repeatRows=1)

    first_total_row = 1 + len(items)
    amount_words_row = first_total_row + 4  # after the 4 totals

    tbl.setStyle(TableStyle([
        ("GRID",       (0,0), (-1,-1), 0.5, colors.black),
        ("BACKGROUND", (0,0), (-1,0),  colors.lightgrey),
        ("VALIGN",     (0,0), (-1,-1), "MIDDLE"),
        ("ALIGN",      (2,1), (2,-1),  "RIGHT"),
        ("ALIGN",      (3,1), (3,-1),  "RIGHT"),
        ("ALIGN",      (4,1), (4,-1),  "RIGHT"),

        # totals block spans
        ("SPAN", (0, first_total_row),   (2, first_total_row)),
        ("SPAN", (0, first_total_row+1), (2, first_total_row+1)),
        ("SPAN", (0, first_total_row+2), (2, first_total_row+2)),
        ("SPAN", (0, first_total_row+3), (2, first_total_row+3)),
        ("FONTNAME", (3, first_total_row+3), (4, first_total_row+3), bold_font),
        ("LINEABOVE", (0, first_total_row),  (-1, first_total_row),  0.75, colors.black),

        # >>> NEW: span the "Amount in words" row across the full table width
        ("SPAN", (0, amount_words_row), (-1, amount_words_row)),
        ("ALIGN", (0, amount_words_row), (-1, amount_words_row), "LEFT"),
        ("LEFTPADDING", (0, amount_words_row), (-1, amount_words_row), 6),
        ("TOPPADDING", (0, amount_words_row), (-1, amount_words_row), 6),
        ("BOTTOMPADDING", (0, amount_words_row), (-1, amount_words_row), 6),
    ]))

    # place items table below meta with safe margins
    tw, th = tbl.wrap(usable_width, 0)
    items_top = (meta_top - mh) - GAP_BELOW_META
    items_y = items_top - th
    if items_y < BOTTOM:
        items_y = BOTTOM
    tbl.drawOn(c, LEFT, items_y)

    # No separate drawString for "Amount in words" anymore

    c.showPage()
    c.save()
    buf.seek(0)
    return send_file(
        buf,
        mimetype="application/pdf",
        as_attachment=True,
        download_name=f"invoice_{inv.invoice_no}.pdf",
    )
