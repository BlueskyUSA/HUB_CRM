"""PDF copy of a budget (values as saved, same sections and columns as the Excel version)."""
import io
from reportlab.lib import colors
from reportlab.lib.pagesizes import letter, landscape
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
import budget_model as bm


def _m(x):
    return f"(${-x:,.0f})" if x < 0 else f"${x:,.0f}"


def build_pdf(label, kind, data, updated_at=None):
    rows, totals = bm.compute(data)
    st = getSampleStyleSheet()
    small = ParagraphStyle("s", parent=st["Normal"], fontSize=8, leading=10)
    h2 = ParagraphStyle("h2", parent=st["Heading3"], spaceBefore=10, spaceAfter=4)
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=landscape(letter), leftMargin=0.5 * inch, rightMargin=0.5 * inch,
                            topMargin=0.5 * inch, bottomMargin=0.5 * inch, title=f"Budget: {label}")
    el = [Paragraph("Sojourn", st["Title"]), Paragraph(f"Budget: {label}", st["Heading2"]),
          Paragraph("Confidential. Prices marked ESTIMATE or PLACEHOLDER are not quotes."
                    + (f" Saved {updated_at}." if updated_at else " Starting template, not yet saved."), small), Spacer(1, 8)]
    if kind == "training":
        summ = [["Total income", "Expenses", "Net", "Break-even", "Expense per couple"],
                [_m(totals["income"]), _m(totals["expenses"]), _m(totals["net"]),
                 f"{totals['breakeven']} couples" if totals["breakeven"] else "-", _m(totals["per_couple_expense"])]]
    elif kind == "fixed":
        summ = [["Total fixed and one-time expenses"], [_m(totals["onetime"])]]
    else:
        summ = [["Income", "Expenses", "Net"], [_m(totals["income"]), _m(totals["other"]), _m(totals["income"] - totals["other"])]]
    t = Table(summ)
    t.setStyle(TableStyle([("FONTNAME", (0, 0), (-1, 0), "Helvetica"), ("FONTSIZE", (0, 0), (-1, 0), 8),
                           ("FONTNAME", (0, 1), (-1, 1), "Helvetica-Bold"), ("FONTSIZE", (0, 1), (-1, 1), 13),
                           ("BOX", (0, 0), (-1, -1), 0.5, colors.grey), ("LEFTPADDING", (0, 0), (-1, -1), 10)]))
    el += [t, Spacer(1, 6)]
    if kind == "training":
        el.append(Paragraph("Key variables", h2))
        kv = [["Variable", "Value", "Note"]]
        for k, lab, _d, vk, note in bm.KEY_VARS:
            v = data["vars"].get(k, _d)
            val = f"{v * 100:g}%" if vk == "pct" else (f"${v:,.2f}" if vk == "money2" else f"{v:g}")
            kv.append([Paragraph(lab, small), val, Paragraph(note, small)])
        kt = Table(kv, colWidths=[3.2 * inch, 0.9 * inch, 5.9 * inch], repeatRows=1)
        kt.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#0C4561")), ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                                ("FONTSIZE", (0, 0), (-1, -1), 8), ("VALIGN", (0, 0), (-1, -1), "TOP"),
                                ("LINEBELOW", (0, 0), (-1, -1), 0.25, colors.lightgrey)]))
        el.append(kt)
    for sec, sec_label in bm.sections_for(kind):
        el.append(Paragraph(sec_label, h2))
        tb = [["Item", "Quantity", "Unit cost", "Times", "Budget", "Notes"]]
        for r in [x for x in rows if x["section"] == sec]:
            tb.append([Paragraph(r["label"], small), f"{r['qv']:,.0f}", f"${r['uv']:,.2f}", f"{r['tv']:,.0f}",
                       _m(r["amount"]), Paragraph(r.get("note", ""), small)])
        tb.append(["Total", "", "", "", _m(totals[sec]), ""])
        if sec == "other" and kind == "training":
            tb.append([f"Contingency ({data['vars']['contingency'] * 100:g}% of operating expenses)", "", "", "", _m(totals["contingency"]), ""])
        tt = Table(tb, colWidths=[3.0 * inch, 0.8 * inch, 0.9 * inch, 0.6 * inch, 1.0 * inch, 3.7 * inch], repeatRows=1)
        n = len(tb)
        tt.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#0C4561")), ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                                ("FONTSIZE", (0, 0), (-1, -1), 8), ("VALIGN", (0, 0), (-1, -1), "TOP"),
                                ("ALIGN", (1, 0), (4, -1), "RIGHT"), ("LINEBELOW", (0, 0), (-1, -1), 0.25, colors.lightgrey),
                                ("FONTNAME", (0, n - (2 if sec == "other" and kind == "training" else 1)), (-1, n - (2 if sec == "other" and kind == "training" else 1)), "Helvetica-Bold")]))
        el.append(tt)
    doc.build(el)
    return buf.getvalue()
