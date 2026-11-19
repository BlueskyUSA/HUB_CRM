"""Builds the Excel version of a budget in the layout of Kent's reworked Art of Us workbook (Nov 2026):
key variables, room counts, food rates, venue schedule, Income, Hotel rooms (head count / rooms / room rate / nights),
Meals, Other operating expenses, contingency, NOI and break-even, then one-time expenses and the "after one-time"
lines. Live formulas, so it recalculates in Excel."""
import io
from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
import brand
import budget_model as bm

A = Font(name="Arial", size=10)
B = Font(name="Arial", size=10, bold=True)
BL = Font(name="Arial", size=10, color="0000FF")
WH = Font(name="Arial", size=10, bold=True, color="FFFFFF")
BIG = Font(name="Arial", size=22, bold=True)
H2 = Font(name="Arial", size=14, bold=True)
TEAL = PatternFill("solid", fgColor="0C4561")
YEL = PatternFill("solid", fgColor="FFFF00")
TOP = Border(top=Side(style="thin", color="000000"))
M = "$#,##0;($#,##0);-"
M2 = "$#,##0.00;($#,##0.00);-"
RIGHT = Alignment(horizontal="right")
RATE_LINKS = ("=roomrate", "=lunch", "=dinner", "=hors", "=dance")


def _brand_name():
    n = brand.current()
    return "Discovery!" if n.lower() == "discovery" else n


def build_xlsx(label, kind, data, updated_at=None, fixed_data=None):
    """Returns the .xlsx file as bytes. For a training budget, pass fixed_data (the shared one-time budget) to add the
    one-time expenses and the 'after one-time expenses' lines at the bottom, as in the Art of Us workbook."""
    wb = Workbook()
    ws = wb.active
    ws.title = (label or "Budget")[:30].replace("/", "-")
    ws["A1"] = "PRELIMINARY BUDGET:"
    ws["A1"].font = BIG
    ws["A2"] = f"{_brand_name()}  {label.upper()}"
    ws["A2"].font = H2
    if data.get("dates"):
        ws["A3"] = " " + data["dates"]
        ws["A3"].font = B
    if data.get("hotel"):
        ws["A4"] = data["hotel"]
        ws["A4"].font = B
    ws["A5"] = ("Blue numbers are inputs; black numbers calculate. Prices marked ESTIMATE or PLACEHOLDER are not quotes."
                + (f" Saved {updated_at}." if updated_at else ""))
    ws["A5"].font = A
    r = 7
    v = data["vars"]

    def band(cols):
        """Header band across A:I; cols = {column letter: text}."""
        nonlocal r
        for col in "ABCDEFGHI":
            ws[f"{col}{r}"].fill = TEAL
            ws[f"{col}{r}"].font = WH
        for col, t in cols.items():
            ws[f"{col}{r}"] = t
            ws[f"{col}{r}"].alignment = Alignment(horizontal="left" if col in "AI" else "right")
        r += 1

    def put(col, row, val, fmt=None, font=A, align=None):
        c = ws[f"{col}{row}"]
        c.value = val
        c.font = font
        if fmt:
            c.number_format = fmt
        if align:
            c.alignment = align
        return c

    def inp(col, row, val, fmt):
        return put(col, row, val, fmt, BL, RIGHT)

    K = {}
    disc_r = tax_r = None
    if kind == "training":
        band({"A": "KEY VARIABLES", "D": "Value", "E": "Note"})
        rack_r = r
        put("A", r, "Hotel rack rate per room per night")
        inp("D", r, v["rack"], M2)
        put("E", r, bm.KEY_VARS[0][4])
        K["rack"] = f"$D${r}"
        r += 1
        put("A", r, "Negotiated discount off room rate")
        inp("D", r, v["room_discount"], "0%")
        put("E", r, "Percent off the rack rate (0% = none).")
        disc_r = r
        r += 1
        put("A", r, "Room Rate (After Discount)")
        put("D", r, f"=(1-D{disc_r})*D{rack_r}", M2, B, RIGHT)
        after_r = r
        r += 1
        put("A", r, "Rate with Room Tax")
        inp("C", r, v["room_tax"], "0%")
        put("D", r, f"=(C{r}+1)*D{after_r}", M2, A, RIGHT)
        put("E", r, bm.KEY_VARS[2][4])
        tax_r = r
        r += 1
        put("A", r, "Total Rm Rate with Credit Card Processing Fee")
        inp("C", r, v["room_cc"], "0.0%")
        put("D", r, f"=(C{r}+1)*D{tax_r}", M2, A, RIGHT)
        K["roomrate"] = f"$D${r}"
        r += 1
        put("A", r, "Room Count (people):", font=B)
        r += 1
        for key, lab in (("fac_people", "Facilitators"), ("ta_people", "TA's"), ("av_people", "Audio/Visual"),
                         ("staff_people", "Staff")):
            put("A", r, lab)
            inp("D", r, v[key], "0")
            K[key] = f"$D${r}"
            r += 1
        put("A", r, "Total team (people)")
        put("D", r, f"=SUM({K['fac_people']}:{K['staff_people']})", "0", B, RIGHT)
        K["team"] = f"$D${r}"
        K["team_dance"] = f"({K['fac_people']}+{K['ta_people']}+{K['av_people']})"
        K["ta_rooms"] = f"({K['ta_people']}/2)"
        r += 2
        put("A", r, "Food Service Rates (CC Fee Included)", font=B)
        put("B", r, "Rate", align=RIGHT)
        put("C", r, "Service", align=RIGHT)
        put("D", r, "With service", align=RIGHT)
        r += 1
        for key, lab in (("lunch", "Lunch Rate"), ("dinner", "Dinner Rate"), ("hors", "d'oeuvres Service"),
                         ("dance", "Dinner/Dance Rate")):
            put("A", r, lab)
            inp("B", r, v[f"{key}_rate"], M)
            inp("C", r, v[f"{key}_svc"], "0%")
            put("D", r, f"=B{r}*(1+C{r})", M2, A, RIGHT)
            K[key] = f"$D${r}"
            r += 1
        r += 1
        put("A", r, "Budget Contingency")
        inp("D", r, v["contingency"], "0%")
        K["contingency"] = f"$D${r}"
        r += 2
        if data.get("schedule"):
            put("A", r, "Venue Schedule:", font=B)
            r += 1
            for s in data["schedule"]:
                put("A", r, "     " + s)
                r += 1
            r += 1

    fee_ref = [None]
    S = {}

    def formula_for(raw, cref):
        """A formula for a link such as '=couples', or None when raw is a plain number."""
        if not (isinstance(raw, str) and raw.startswith("=")):
            return None
        table = {"=couples": cref, "=trainees": f"2*{cref}", "=roomrate": K.get("roomrate"), "=rack": K.get("rack"),
                 "=team": K.get("team"), "=team_dance": K.get("team_dance"), "=ta_rooms": K.get("ta_rooms"),
                 "=lunch": K.get("lunch"), "=dinner": K.get("dinner"), "=hors": K.get("hors"), "=dance": K.get("dance"),
                 "=fac": K.get("fac_people"), "=ta": K.get("ta_people"), "=av": K.get("av_people"),
                 "=staff": K.get("staff_people")}
        return "=" + str(table.get(raw) or 0)

    def lines_of(d, sec):
        return [x for x in d["lines"] if x["section"] == sec]

    def section(sec, sec_label, lines):
        nonlocal r
        if sec == "income":
            band({"A": sec_label.upper(), "D": "Quantity", "E": "Unit cost", "F": "Times (nights / days)", "H": "Income", "I": "Notes"})
        elif sec == "rooms":
            band({"A": "EXPENSES:", "C": "Head Count", "D": "Room Count", "E": "Room Rate", "F": "Nights", "H": "Budget", "I": "Notes"})
            put("A", r, "HOTEL ROOMS:", font=B)
            r += 1
        elif sec == "meals":
            put("A", r, "MEALS:", font=B)
            put("D", r, "Count", font=B, align=RIGHT)
            put("E", r, "Rate", font=B, align=RIGHT)
            put("F", r, "Times", font=B, align=RIGHT)
            r += 1
        elif sec == "other":
            if kind == "donations":
                band({"A": "EXPENSES:", "D": "Quantity", "E": "Unit cost", "F": "Times", "H": "Budget", "I": "Notes"})
            else:
                put("A", r, "OTHER OPERATING EXPENSES:", font=B)
                r += 1
        elif sec == "onetime":
            band({"A": sec_label.upper(), "D": "Quantity", "E": "Unit cost", "F": "Times", "H": "Budget", "I": "Notes"})
        first = r
        for ln in lines:
            cref = f"$D${fee_ref[0]}" if fee_ref[0] else "0"
            put("A", r, "    " + ln["label"])
            if "h" in ln:
                put("C", r, formula_for(ln["h"], cref) or ln["h"], "#,##0", A, RIGHT)
            for col, raw, fmt in (
                    ("D", ln["q"], "#,##0"),
                    ("E", ln["u"], M2 if ((isinstance(ln["u"], (int, float)) and ln["u"] % 1) or ln["u"] in RATE_LINKS) else M),
                    ("F", ln["t"], "0")):
                f = formula_for(raw, cref)
                if f:
                    put(col, r, f, fmt, A, RIGHT)
                else:
                    inp(col, r, raw, fmt)
            formula = f"=D{r}*E{r}*F{r}"
            if ln.get("mode") == "room" and disc_r:
                formula += f"*(1-D{disc_r})*(1+C{tax_r})*(1+C{tax_r + 1})"
            put("H", r, formula, M, A)
            put("I", r, ln.get("note", ""))
            if ln["id"] == "fee_income":
                fee_ref[0] = r
            r += 1
        word = {"income": "Income", "rooms": "Hotel Rooms", "meals": "Meals", "other": "Other Operating Expenses",
                "onetime": "One-Time Expenses"}[sec]
        put("A", r, f"  Total for {word}", font=B)
        c = put("H", r, f"=SUM(H{first}:H{r - 1})" if r > first else 0, M, B)
        c.border = TOP
        if sec == "rooms":
            put("C", r, f"=SUM(C{first}:C{r - 1})", "#,##0", B, RIGHT)
            put("D", r, f"=SUM(D{first}:D{r - 1})", "#,##0", B, RIGHT)
        S[sec] = r
        r += 2

    def yellow(row):
        for col in "ABCDEFGHI":
            ws[f"{col}{row}"].fill = YEL

    if kind == "training":
        section("income", "Income", lines_of(data, "income"))
        section("rooms", "Hotel rooms", lines_of(data, "rooms"))
        section("meals", "Meals", lines_of(data, "meals"))
        section("other", "Other operating expenses", lines_of(data, "other"))
        put("A", r, "SUBTOTAL - EXPENSES", font=B)
        put("H", r, f"=H{S['rooms']}+H{S['meals']}+H{S['other']}", M, B)
        yellow(r)
        sub = r
        r += 2
        put("A", r, "  Contingency")
        put("F", r, f"={K['contingency']}", "0%", A, RIGHT)
        put("H", r, f"=F{r}*H{sub}", M, A)
        cont = r
        r += 1
        put("A", r, "TOTAL EXPENSES", font=B)
        put("H", r, f"=H{cont}+H{sub}", M, B)
        tot = r
        r += 1
        put("A", r, "NOI  (Before One-time Expenses)", font=B)
        put("H", r, f"=H{S['income']}-H{tot}", M, B)
        r += 1
        put("A", r, "BREAK EVEN (No of Couples)", font=B)
        put("H", r, f"=ROUNDUP(H{tot}/E{fee_ref[0]},0)", "0", B)
        yellow(r)
        r += 2
        if fixed_data is not None:
            section("onetime", "One-time expenses (equipment and banners)", lines_of(fixed_data, "onetime"))
            ot = S["onetime"]
            put("A", r, "Total Operating & One Time Expenses", font=B)
            put("H", r, f"=H{ot}+H{tot}", M, B)
            allr = r
            r += 2
            put("A", r, "Net before one-time expenses", font=B)
            put("H", r, f"=H{S['income']}-H{allr}+H{ot}", M, B)
            r += 1
            put("A", r, "Net Operating Income", font=B)
            put("H", r, f"=H{S['income']}-H{allr}", M, B)
            r += 1
            put("A", r, "BREAK EVEN (No of Couples)", font=B)
            put("H", r, f"=ROUNDUP(H{allr}/E{fee_ref[0]},0)", "0", B)
            yellow(r)
            r += 1
    elif kind == "fixed":
        section("onetime", "One-time expenses (equipment and banners)", lines_of(data, "onetime"))
    else:  # donations
        section("income", "Income", lines_of(data, "income"))
        section("other", "Expenses", lines_of(data, "other"))
        put("A", r, "NET DONATIONS", font=B)
        put("H", r, f"=H{S['income']}-H{S['other']}", M, B)
    for col, w in zip("ABCDEFGHI", (58, 8, 11, 11, 13, 11, 3, 14, 90)):
        ws.column_dimensions[col].width = w
    ws.sheet_view.showGridLines = False
    ws.page_setup.orientation = "landscape"
    ws.page_setup.fitToWidth = 1
    ws.page_setup.fitToHeight = 0
    ws.sheet_properties.pageSetUpPr.fitToPage = True
    wb.calculation.fullCalcOnLoad = True
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()
