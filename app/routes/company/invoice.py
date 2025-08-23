# app/routes/company/invoice.py
from __future__ import annotations

import os
from io import BytesIO
from decimal import Decimal, ROUND_HALF_UP
from datetime import datetime

from flask import (
    Blueprint, current_app, render_template, request, redirect,
    url_for, send_file, abort, flash
)

# -------- Blueprint (kept same name as used in templates) --------
bp = Blueprint("invoice", __name__, url_prefix="/company/invoice")


# ====================== PDF GENERATOR (ReportLab) ======================
# pip install reportlab
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, KeepTogether
)
from reportlab.lib.enums import TA_CENTER, TA_RIGHT, TA_LEFT


def _money(x) -> str:
    q = Decimal(str(x or 0)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    return f"{q:,.2f}"


def _pct(x) -> str:
    return f"{Decimal(str(x or 0)).quantize(Decimal('0.01'))}%"


def _sp(h=6):
    return Spacer(1, h)


def _build_invoice_pdf(
    buffer: BytesIO,
    company: dict,
    bill_to: dict,
    invoice_meta: dict,
    items: list[dict],
    taxes: dict | None = None,
    footer_note: str | None = "Thank you for your business!",
):
    page_w, page_h = A4
    margins = dict(left=14 * mm, right=14 * mm, top=16 * mm, bottom=16 * mm)

    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        leftMargin=margins["left"],
        rightMargin=margins["right"],
        topMargin=margins["top"],
        bottomMargin=margins["bottom"],
    )

    styles = getSampleStyleSheet()
    styles.add(ParagraphStyle(name="H1White", fontSize=16, leading=19,
                              alignment=TA_CENTER, textColor=colors.white))
    styles.add(ParagraphStyle(name="Small", fontSize=9, leading=11))
    styles.add(ParagraphStyle(name="CellKey", fontSize=9, backColor=colors.lightgrey, leading=11))
    styles.add(ParagraphStyle(name="Right9", fontSize=9, alignment=TA_RIGHT, leading=11))
    styles.add(ParagraphStyle(name="FooterWhite", fontSize=9, alignment=TA_CENTER, textColor=colors.white))

    brand_orange = colors.HexColor("#E67E22")

    story = []

    # Header band
    title_tbl = Table([[Paragraph(f"<b>{company['name']}</b>", styles["H1White"])]],
                      colWidths=[page_w - margins["left"] - margins["right"]])
    title_tbl.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), brand_orange),
        ("LEFTPADDING", (0, 0), (-1, -1), 8),
        ("RIGHTPADDING", (0, 0), (-1, -1), 8),
        ("TOPPADDING", (0, 0), (-1, -1), 10),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 10),
    ]))
    story.append(title_tbl)

    # Company info (wrapped; prevents overlap)
    comp_rows = [
        [Paragraph(f"<b>Address:</b> {company.get('address','')}", styles["Small"])],
        [Paragraph(f"<b>Mobile:</b> {company.get('mobile','')}", styles["Small"])],
        [Paragraph(f"<b>Email:</b> {company.get('email','')}", styles["Small"])],
        [Paragraph(f"<b>Website:</b> {company.get('website','')}", styles["Small"])],
        [Paragraph(f"<b>GSTIN:</b> {company.get('gstin','')}", styles["Small"])],
    ]
    comp_tbl = Table(comp_rows, colWidths=[page_w - margins["left"] - margins["right"]])
    comp_tbl.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), colors.whitesmoke),
        ("BOX", (0, 0), (-1, -1), 0.6, colors.black),
        ("INNERGRID", (0, 0), (-1, -1), 0.3, colors.black),
        ("LEFTPADDING", (0, 0), (-1, -1), 6),
        ("RIGHTPADDING", (0, 0), (-1, -1), 6),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ]))
    story += [comp_tbl, _sp(8)]

    # Customer + invoice meta
    meta_tbl = Table([
        [Paragraph("<b>Customer Name</b>", styles["CellKey"]),
         Paragraph(bill_to.get("name",""), styles["Small"]),
         Paragraph("<b>Invoice No</b>", styles["CellKey"]),
         Paragraph(str(invoice_meta.get("number","")), styles["Small"])],
        [Paragraph("<b>Invoice Date</b>", styles["CellKey"]),
         Paragraph(invoice_meta.get("date",""), styles["Small"]),
         Paragraph("<b>Driver No</b>", styles["CellKey"]),
         Paragraph(bill_to.get("driver_no",""), styles["Small"])],
        [Paragraph("<b>Vehicle No</b>", styles["CellKey"]),
         Paragraph(bill_to.get("vehicle_no",""), styles["Small"]),
         Paragraph("<b>Address</b>", styles["CellKey"]),
         Paragraph(bill_to.get("address",""), styles["Small"])],
    ], colWidths=[28*mm, 70*mm, 28*mm, 68*mm])
    meta_tbl.setStyle(TableStyle([
        ("GRID", (0, 0), (-1, -1), 0.5, colors.black),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 5),
        ("RIGHTPADDING", (0, 0), (-1, -1), 5),
        ("TOPPADDING", (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
    ]))
    story += [meta_tbl, _sp(8)]

    # Items
    head = [
        Paragraph("<b>SL NO</b>", styles["Small"]),
        Paragraph("<b>DESCRIPTION OF GOODS</b>", styles["Small"]),
        Paragraph("<b>PRICE</b>", styles["Small"]),
        Paragraph("<b>QTY</b>", styles["Small"]),
        Paragraph("<b>UOM</b>", styles["Small"]),
        Paragraph("<b>AMOUNT</b>", styles["Small"]),
    ]
    data = [head]
    subtotal = Decimal("0.00")
    for it in items:
        rate = Decimal(str(it.get("rate", 0)))
        qty = Decimal(str(it.get("qty", 0)))
        amt = rate * qty
        subtotal += amt
        data.append([
            str(it.get("sl", "")),
            Paragraph(it.get("description", ""), styles["Small"]),
            _money(rate), _money(qty),
            it.get("uom", ""), _money(amt)
        ])

    col_widths = [16*mm, 70*mm, 24*mm, 24*mm, 18*mm, 32*mm]
    items_tbl = Table(data, colWidths=col_widths, repeatRows=1)
    items_tbl.setStyle(TableStyle([
        ("GRID", (0, 0), (-1, -1), 0.5, colors.black),
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#E67E22")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("ALIGN", (2, 1), (2, -1), "RIGHT"),
        ("ALIGN", (3, 1), (3, -1), "RIGHT"),
        ("ALIGN", (5, 1), (5, -1), "RIGHT"),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 5),
        ("RIGHTPADDING", (0, 0), (-1, -1), 5),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ]))
    story += [items_tbl, _sp(8)]

    # Totals
    rows = [["Subtotal", _money(subtotal)]]
    cgst = sgst = igst = Decimal("0.00")
    if taxes:
        if taxes.get("igst_rate"):
            r = Decimal(str(taxes["igst_rate"]))
            igst = (subtotal * r / 100).quantize(Decimal("0.01"))
            rows.append([f"IGST ({_pct(r)})", _money(igst)])
        else:
            if taxes.get("cgst_rate"):
                r = Decimal(str(taxes["cgst_rate"]))
                cgst = (subtotal * r / 100).quantize(Decimal("0.01"))
                rows.append([f"CGST ({_pct(r)})", _money(cgst)])
            if taxes.get("sgst_rate"):
                r = Decimal(str(taxes["sgst_rate"]))
                sgst = (subtotal * r / 100).quantize(Decimal("0.01"))
                rows.append([f"SGST ({_pct(r)})", _money(sgst)])

    grand_total = subtotal + cgst + sgst + igst
    rows.append(["Grand Total", _money(grand_total)])

    totals_tbl = Table(rows, colWidths=[page_w - margins["left"] - margins["right"] - 50*mm, 50*mm])
    totals_tbl.setStyle(TableStyle([
        ("GRID", (0, 0), (-1, -1), 0.5, colors.black),
        ("BACKGROUND", (0, -1), (-1, -1), colors.lightgrey),
        ("ALIGN", (1, 0), (1, -1), "RIGHT"),
        ("LEFTPADDING", (0, 0), (-1, -1), 6),
        ("RIGHTPADDING", (0, 0), (-1, -1), 6),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ]))
    story += [totals_tbl, _sp(10)]

    # Declaration + sign
    story += [
        KeepTogether([
            Paragraph("Certified that the particulars given above are true and correct.", styles["Small"]),
            _sp(6),
            Paragraph(f"For <b>{company['name']}</b>", styles["Right9"]),
            _sp(18),
            Paragraph("<b>Authorised Signatory</b>", styles["Right9"]),
        ])
    ]

    # Footer band
    if footer_note:
        ft = Table([[Paragraph(footer_note, styles["FooterWhite"])]],
                   colWidths=[page_w - margins["left"] - margins["right"]])
        ft.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, -1), brand_orange),
            ("TOPPADDING", (0, 0), (-1, -1), 6),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
        ]))
        story.append(ft)

    doc.build(story)


# ============================ ROUTES ============================

@bp.get("/new")
def new_invoice():
    """
    Renders your existing form template:
    templates/company/invoice_new.html
    Keep your current HTML; this route name is unchanged: 'invoice.new_invoice'
    """
    return render_template("company/invoice_new.html")


@bp.post("/new")
def create_invoice():
    """
    Reads posted form fields (use your current form names).
    Saves a PDF to instance/invoices/invoice_<number>.pdf
    then redirects to /company/invoice/<number>/pdf
    """
    form = request.form

    # Minimal field names; adapt only if your form uses different keys.
    number = form.get("invoice_no") or form.get("number") or "1"
    date_str = form.get("invoice_date") or datetime.utcnow().strftime("%d-%m-%Y")

    company = {
        "name": "Shree Anunay Agro Pvt Ltd",
        "address": "Dalsingsarai, Samastipur, Bihar",
        "mobile": "9771899097 / 6299176297",
        "email": "skchy@anunayagro.co.in",
        "website": "www.shreeanunayagro.com",
        "gstin": "10ABOCS8567L1ZO",
    }

    bill_to = {
        "name": form.get("customer_name", ""),
        "address": form.get("customer_address", ""),
        "driver_no": form.get("driver_no", ""),
        "vehicle_no": form.get("vehicle_no", ""),
    }

    invoice_meta = {
        "number": number,
        "date": date_str,
        "place": form.get("place", ""),
    }

    # Single-line item by default; extend as per your form
    items = [{
        "sl": 1,
        "description": form.get("description", "Goods"),
        "rate": form.get("rate", "0"),
        "qty": form.get("qty", "0"),
        "uom": form.get("uom", "Quintal"),
    }]

    taxes = {
        "cgst_rate": form.get("cgst_rate", 0) or 0,
        "sgst_rate": form.get("sgst_rate", 0) or 0,
        # Use igst_rate if applicable
    }

    # Ensure output dir
    out_dir = os.path.join(current_app.instance_path, "invoices")
    os.makedirs(out_dir, exist_ok=True)
    pdf_path = os.path.join(out_dir, f"invoice_{number}.pdf")

    # Generate PDF
    buf = BytesIO()
    _build_invoice_pdf(
        buffer=buf,
        company=company,
        bill_to=bill_to,
        invoice_meta=invoice_meta,
        items=items,
        taxes=taxes,
        footer_note=f"For queries: {company['mobile']} | {company['email']}",
    )
    with open(pdf_path, "wb") as f:
        f.write(buf.getvalue())

    return redirect(url_for("invoice.view_pdf", invoice_id=number))


@bp.get("/<int:invoice_id>/pdf")
def view_pdf(invoice_id: int):
    """
    Serves the generated PDF from instance/invoices.
    Matches your previous working URL: /company/invoice/<id>/pdf
    """
    pdf_path = os.path.join(current_app.instance_path, "invoices", f"invoice_{invoice_id}.pdf")
    if not os.path.exists(pdf_path):
        abort(404)
    return send_file(pdf_path, mimetype="application/pdf", download_name=f"invoice_{invoice_id}.pdf")
