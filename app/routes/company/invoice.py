# invoice.py
# pip install reportlab==3.6.12

from datetime import datetime
from decimal import Decimal, ROUND_HALF_UP
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, KeepTogether
)
from reportlab.lib.enums import TA_CENTER, TA_RIGHT, TA_LEFT


# ---------- Helpers ----------
def money(x):
    """Format number as 2‑decimal currency string."""
    if x is None:
        x = 0
    q = Decimal(x).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    return f"{q:,.2f}"

def pct(x):
    return f"{Decimal(x).quantize(Decimal('0.01'))}%"

def line(height=6):
    return Spacer(1, height)

# ---------- Core Generator ----------
def build_invoice_pdf(
    out_path,
    company,
    bill_to,
    invoice_meta,
    items,
    taxes=None,
    footer_note="Thank you for your business!"
):
    """
    company: dict(name, address, mobile, email, website, gstin)
    bill_to: dict(name, address, driver_no, vehicle_no)
    invoice_meta: dict(number, date, place=None)
    items: list of dicts with keys: sl, description, rate, qty, uom ('Quintal', etc)
    taxes: dict with keys:
        - cgst_rate, sgst_rate  (if interstate, pass igst_rate instead)
    """

    # --- Document ---
    page_w, page_h = A4
    margins = dict(left=14*mm, right=14*mm, top=16*mm, bottom=16*mm)
    doc = SimpleDocTemplate(
        out_path, pagesize=A4,
        leftMargin=margins["left"], rightMargin=margins["right"],
        topMargin=margins["top"], bottomMargin=margins["bottom"]
    )

    # --- Styles ---
    styles = getSampleStyleSheet()
    styles.add(ParagraphStyle(name="H1White", fontSize=16, leading=19,
                              alignment=TA_CENTER, textColor=colors.white))
    styles.add(ParagraphStyle(name="Small", fontSize=9, leading=11))
    styles.add(ParagraphStyle(name="SmallBold", fontSize=9, leading=11, spaceAfter=0, spaceBefore=0, leftIndent=0))
    styles.add(ParagraphStyle(name="CellKey", fontSize=9, backColor=colors.lightgrey, leading=11))
    styles.add(ParagraphStyle(name="Right9", fontSize=9, alignment=TA_RIGHT, leading=11))
    styles.add(ParagraphStyle(name="Left9", fontSize=9, alignment=TA_LEFT, leading=11))
    styles.add(ParagraphStyle(name="FooterWhite", fontSize=9, alignment=TA_CENTER, textColor=colors.white))

    brand_orange = colors.HexColor("#E67E22")

    story = []

    # ---------- HEADER BAND ----------
    title_tbl = Table([[Paragraph(f"<b>{company['name']}</b>", styles["H1White"])]],
                      colWidths=[page_w - margins["left"] - margins["right"]])
    title_tbl.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), brand_orange),
        ("LEFTPADDING", (0, 0), (-1, -1), 8),
        ("RIGHTPADDING", (0, 0), (-1, -1), 8),
        ("TOPPADDING", (0, 0), (-1, -1), 10),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 10),
    ]))
    story += [title_tbl]

    # Company info inside header section (wrapped)
    comp_rows = [
        [Paragraph(f"<b>Address:</b> {company.get('address','')}", styles["Small"])],
        [Paragraph(f"<b>Mobile:</b> {company.get('mobile','')}", styles["Small"])],
        [Paragraph(f"<b>Email:</b> {company.get('email','')}", styles["Small"])],
        [Paragraph(f"<b>Website:</b> {company.get('website','')}", styles["Small"])],
        [Paragraph(f"<b>GSTIN:</b> {company.get('gstin','')}", styles["Small"])]
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
    story += [comp_tbl, line(8)]

    # ---------- BILL TO + INVOICE META ----------
    meta_tbl = Table([
        [Paragraph("<b>Customer Name</b>", styles["CellKey"]),
         Paragraph(bill_to.get("name",""), styles["Left9"]),
         Paragraph("<b>Invoice No</b>", styles["CellKey"]),
         Paragraph(str(invoice_meta.get("number","")), styles["Left9"])],
        [Paragraph("<b>Invoice Date</b>", styles["CellKey"]),
         Paragraph(invoice_meta.get("date",""), styles["Left9"]),
         Paragraph("<b>Driver No</b>", styles["CellKey"]),
         Paragraph(bill_to.get("driver_no",""), styles["Left9"])],
        [Paragraph("<b>Vehicle No</b>", styles["CellKey"]),
         Paragraph(bill_to.get("vehicle_no",""), styles["Left9"]),
         Paragraph("<b>Address</b>", styles["CellKey"]),
         Paragraph(bill_to.get("address",""), styles["Left9"])],
    ], colWidths=[28*mm, 70*mm, 28*mm, 68*mm])
    meta_tbl.setStyle(TableStyle([
        ("GRID", (0, 0), (-1, -1), 0.5, colors.black),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 5),
        ("RIGHTPADDING", (0, 0), (-1, -1), 5),
        ("TOPPADDING", (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
    ]))
    story += [meta_tbl, line(8)]

    # ---------- ITEMS ----------
    item_header = [
        Paragraph("<b>SL NO</b>", styles["Small"]),
        Paragraph("<b>DESCRIPTION OF GOODS</b>", styles["Small"]),
        Paragraph("<b>PRICE</b>", styles["Small"]),
        Paragraph("<b>QTY</b>", styles["Small"]),
        Paragraph("<b>UOM</b>", styles["Small"]),
        Paragraph("<b>AMOUNT</b>", styles["Small"]),
    ]

    data_rows = [item_header]
    subtotal = Decimal("0.00")
    for it in items:
        rate = Decimal(str(it.get("rate", 0)))
        qty = Decimal(str(it.get("qty", 0)))
        amt = rate * qty
        subtotal += amt
        data_rows.append([
            str(it.get("sl","")),
            Paragraph(it.get("description",""), styles["Small"]),
            money(rate),
            money(qty),
            it.get("uom", ""),
            money(amt),
        ])

    col_widths = [16*mm, 70*mm, 24*mm, 24*mm, 18*mm, 32*mm]
    tbl = Table(data_rows, colWidths=col_widths, repeatRows=1)
    tbl.setStyle(TableStyle([
        ("GRID", (0, 0), (-1, -1), 0.5, colors.black),
        ("BACKGROUND", (0, 0), (-1, 0), brand_orange),
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
    story += [tbl, line(8)]

    # ---------- TOTALS / TAX ----------
    totals_rows = [["Subtotal", money(subtotal)]]

    cgst = sgst = igst = Decimal("0.00")
    if taxes:
        if "igst_rate" in taxes and taxes["igst_rate"]:
            igst_rate = Decimal(str(taxes["igst_rate"]))
            igst = (subtotal * igst_rate / 100).quantize(Decimal("0.01"))
            totals_rows.append([f"IGST ({pct(igst_rate)})", money(igst)])
        else:
            cgst_rate = Decimal(str(taxes.get("cgst_rate", 0)))
            sgst_rate = Decimal(str(taxes.get("sgst_rate", 0)))
            if cgst_rate:
                cgst = (subtotal * cgst_rate / 100).quantize(Decimal("0.01"))
                totals_rows.append([f"CGST ({pct(cgst_rate)})", money(cgst)])
            if sgst_rate:
                sgst = (subtotal * sgst_rate / 100).quantize(Decimal("0.01"))
                totals_rows.append([f"SGST ({pct(sgst_rate)})", money(sgst)])

    grand_total = subtotal + cgst + sgst + igst
    totals_rows.append(["Grand Total", money(grand_total)])

    totals_tbl = Table(totals_rows, colWidths=[page_w - margins["left"] - margins["right"] - 50*mm, 50*mm])
    totals_tbl.setStyle(TableStyle([
        ("GRID", (0, 0), (-1, -1), 0.5, colors.black),
        ("BACKGROUND", (0, -1), (-1, -1), colors.lightgrey),
        ("ALIGN", (1, 0), (1, -1), "RIGHT"),
        ("LEFTPADDING", (0, 0), (-1, -1), 6),
        ("RIGHTPADDING", (0, 0), (-1, -1), 6),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ]))
    story += [totals_tbl, line(10)]

    # ---------- DECLARATION / SIGN ----------
    declaration = KeepTogether([
        Paragraph("Certified that the particulars given above are true and correct.", styles["Small"]),
        line(6),
        Paragraph("For <b>{}</b>".format(company["name"]), styles["Right9"]),
        line(18),
        Paragraph("<b>Authorised Signatory</b>", styles["Right9"]),
    ])
    story += [declaration, line(10)]

    # ---------- FOOTER BAND ----------
    if footer_note:
        footer_tbl = Table([[Paragraph(footer_note, styles["FooterWhite"])]],
                           colWidths=[page_w - margins["left"] - margins["right"]])
        footer_tbl.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, -1), brand_orange),
            ("TOPPADDING", (0, 0), (-1, -1), 6),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
        ]))
        story.append(footer_tbl)

    # Build
    doc.build(story)


# ---------- Example usage ----------
if __name__ == "__main__":
    company_info = {
        "name": "Shree Anunay Agro Pvt Ltd",
        "address": "Dalsingsarai, Samastipur, Bihar",
        "mobile": "9771899097 / 6299176297",
        "email": "skchy@anunayagro.co.in",
        "website": "www.shreeanunayagro.com",
        "gstin": "10ABOCS8567L1ZO",
    }

    bill_to_info = {
        "name": "Banga Enterprises (Chandan, Teghra)",
        "address": "Teghra, Begusarai, Bihar",
        "driver_no": "1234567890",
        "vehicle_no": "BR-06GC-4169",
    }

    invoice_meta_info = {
        "number": 2,
        "date": datetime.strptime("23-08-2025", "%d-%m-%Y").strftime("%d-%m-%Y"),
        "place": "Samastipur"
    }

    items_list = [
        {"sl": 1, "description": "Wheat", "rate": 2700.00, "qty": 243.85, "uom": "Quintal"},
        # add more items as needed …
    ]

    taxes_info = {
        "cgst_rate": 0.0,
        "sgst_rate": 0.0,
        # For IGST use: "igst_rate": 18.0
    }

    build_invoice_pdf(
        out_path="invoice.pdf",
        company=company_info,
        bill_to=bill_to_info,
        invoice_meta=invoice_meta_info,
        items=items_list,
        taxes=taxes_info,
        footer_note="For queries, contact: {} | {}".format(
            company_info["mobile"], company_info["email"]
        ),
    )
