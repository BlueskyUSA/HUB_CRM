"""PDF copy of a budget (values as saved; same order and wording as the Excel version, in the Art of Us layout)."""
import io
from reportlab.lib import colors
from reportlab.lib.pagesizes import letter, landscape
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
import brand
import budget_model as bm

TEAL = colors.HexColor("#0C4561")
YEL = colors.HexColor("#FFFF00")


def _m(x):
    return f"(${-x:,.0f})" if x < 0 else f"${x:,.0f}"


def _m2(x):
    return f"${x:,.2f}"


def _brand_name():
    n = brand.current()
    return "Discovery!" if n.lower() == "discovery" else n


def build_pdf(label, kind, data, updated_at=None, fixed_data=None):
    rows, totals = bm.compute(data)
    fixed_total = None
    if kind == "training" and fixed_data is not None:
        _, ft = bm.compute(fixed_data)
        fixed_total = ft["onetime"]
        totals = bm.with_onetime(totals, fixed_total)
    st = getSampleStyleSheet()
    small = ParagraphStyle("s", parent=st["Normal"], fontSize=8, leading=10)
    h2 = ParagraphStyle("h2", parent=st["Heading3"], spaceBefore=10, spaceAfter=4)
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=landscape(letter), leftMargin=0.5 * inch, rightMargin=0.5 * inch,
                            topMargin=0.5 * inch, bottomMargin=0.5 * inch, title=f"Budget: {label}")
    el = [Paragraph("PRELIMINARY BUDGET:", st["Title"]), Paragraph(f"{_brand_name()}  {label.upper()}", st["Heading2"])]
    if data.get("dates"):
        el.append(Paragraph(f"<b>{data['dates']}</b>", small))
    if data.get("hotel"):
        el.append(Paragraph(f"<b>{data['hotel']}</b>", small))
    el += [Paragraph("Confidential. Prices marked ESTIMATE or PLACEHOLDER are not quotes."
                     + (f" Saved {updated_at}." if updated_at else " Starting template, not yet saved."), small), Spacer(1, 8)]
    if kind == "training":
        head = ["Total income", "Expenses", "NOI before one-time", "Break-even (before one-time)"]
        vals = [_m(totals["income"]), _m(totals["expenses"]), _m(totals["net"]),
                f"{totals['breakeven']} couples" if totals["breakeven"] else "-"]
        if fixed_total is not None:
            head += ["Net after one-time", "Break-even (all costs)"]
            vals += [_m(totals["net_after_onetime"]), f"{totals['breakeven_all']} couples" if totals["breakeven_all"] else "-"]
        summ = [head, vals]
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
        d = totals["derived"]
        el.append(Paragraph("Key variables", h2))
        kv = [["Variable", "Value", "Note"]]
        for k, lab, _d, vk, note in bm.KEY_VARS:
            val_ = data["vars"].get(k, _d)
            val = f"{val_ * 100:g}%" if vk == "pct" else (f"${val_:,.2f}" if vk == "money2" else (f"{val_:g} per room" if vk == "choice12" else f"{val_:g}"))
            kv.append([Paragraph(lab, small), val, Paragraph(note, small)])
        kv += [[Paragraph("<b>Room Rate (After Discount)</b>", small), _m2(d["after_discount"]), ""],
               [Paragraph("<b>Rate with Room Tax</b>", small), _m2(d["with_tax"]), ""],
               [Paragraph("<b>Total Rm Rate with Credit Card Processing Fee</b>", small), _m2(d["roomrate"]), ""],
               [Paragraph("<b>Rooms: trainees / facilitators / TA's / A-V / staff</b>", small),
                " / ".join(f"{d[g + '_rooms']:g}" for g in ("trainee", "fac", "ta", "av", "staff")), ""],
               [Paragraph("<b>Total team (people)</b>", small), f"{d['team']:g}", ""],
               [Paragraph("<b>Lunch / Dinner / d'oeuvres / Dinner-Dance with service</b>", small),
                " / ".join(_m2(d[x]) for x in ("lunch", "dinner", "hors", "dance")), ""]]
        kt = Table(kv, colWidths=[3.4 * inch, 2.0 * inch, 4.6 * inch], repeatRows=1)
        kt.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, 0), TEAL), ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                                ("FONTSIZE", (0, 0), (-1, -1), 8), ("VALIGN", (0, 0), (-1, -1), "TOP"),
                                ("LINEBELOW", (0, 0), (-1, -1), 0.25, colors.lightgrey)]))
        el.append(kt)
        if data.get("schedule"):
            el.append(Paragraph("Venue Schedule", h2))
            for s in data["schedule"]:
                el.append(Paragraph(s, small))
    secs = bm.sections_for(kind)
    all_rows = rows
    if kind == "training" and fixed_data is not None:
        frows, _ = bm.compute(fixed_data)
        all_rows = rows + [x for x in frows if x["section"] == "onetime"]
        secs = list(secs) + [x for x in bm.SECTIONS if x[0] == "onetime"]
    for sec, sec_label in secs:
        el.append(Paragraph(sec_label, h2))
        cols = bm.SECTION_COLS.get(sec)
        has_h = bool(cols and cols[0])
        names = cols if cols else (None, "Quantity", "Unit cost", "Times")
        head = ["Item"] + (["Head count"] if has_h else []) + list(names[1:]) + ["Budget", "Notes"]
        tb = [head]
        for r in [x for x in all_rows if x["section"] == sec]:
            row = [Paragraph(r["label"], small)]
            if has_h:
                row.append(f"{r['hv']:,.0f}" if r["hv"] is not None else "")
            row += [f"{r['qv']:,.0f}", _m2(r["uv"]), f"{r['tv']:,.0f}", _m(r["amount"]), Paragraph(r.get("note", ""), small)]
            tb.append(row)
        n = len(tb)
        tot_row = ["Total"] + ([""] if has_h else []) + ["", "", "", _m(totals[sec]), ""]
        tb.append(tot_row)
        widths = [3.0 * inch] + ([0.7 * inch] if has_h else []) + [0.7 * inch, 0.9 * inch, 0.6 * inch, 0.9 * inch]
        widths.append(10.0 * inch - sum(widths))
        tt = Table(tb, colWidths=widths, repeatRows=1)
        first_num = 1
        last_num = 4 + (1 if has_h else 0)
        tt.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, 0), TEAL), ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                                ("FONTSIZE", (0, 0), (-1, -1), 8), ("VALIGN", (0, 0), (-1, -1), "TOP"),
                                ("ALIGN", (first_num, 0), (last_num, -1), "RIGHT"),
                                ("LINEBELOW", (0, 0), (-1, -1), 0.25, colors.lightgrey),
                                ("FONTNAME", (0, n), (-1, n), "Helvetica-Bold")]))
        el.append(tt)
    if kind == "training":
        el.append(Spacer(1, 8))
        lines = [["SUBTOTAL - EXPENSES", _m(totals["operating"])],
                 [f"Contingency ({data['vars']['contingency'] * 100:g}%)", _m(totals["contingency"])],
                 ["TOTAL EXPENSES", _m(totals["expenses"])],
                 ["NOI (Before One-time Expenses)", _m(totals["net"])],
                 ["BREAK EVEN (No of Couples)", str(totals["breakeven"]) if totals["breakeven"] else "-"]]
        if fixed_total is not None:
            lines += [["Total Operating & One Time Expenses", _m(totals["all_expenses"])],
                      ["Net before one-time expenses", _m(totals["net"])],
                      ["Net Operating Income", _m(totals["net_after_onetime"])],
                      ["BREAK EVEN (No of Couples), all costs", str(totals["breakeven_all"]) if totals["breakeven_all"] else "-"]]
        bt = Table(lines, colWidths=[4.0 * inch, 1.4 * inch])
        styles = [("FONTSIZE", (0, 0), (-1, -1), 9), ("FONTNAME", (0, 0), (-1, -1), "Helvetica-Bold"),
                  ("ALIGN", (1, 0), (1, -1), "RIGHT"), ("LINEBELOW", (0, 0), (-1, -1), 0.25, colors.lightgrey)]
        for i, (lab, _v) in enumerate(lines):
            if lab.startswith("SUBTOTAL") or lab.startswith("BREAK EVEN"):
                styles.append(("BACKGROUND", (0, i), (-1, i), YEL))
        bt.setStyle(TableStyle(styles))
        el.append(bt)
    doc.build(el)
    return buf.getvalue()
