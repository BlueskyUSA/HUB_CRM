"""Training budgets: the structure, defaults and arithmetic.

FORMAT 2 (Nov 2026) follows Kent's reworked Art of Us workbook: key variables (hotel rate with discount, tax and
card fee; room counts; food rates with banquet service), then Income, Hotel rooms (head count, rooms, room rate,
nights), Meals (count x rate), Other operating expenses, contingency, NOI and break-even, then the one-time
expenses and the "after one-time expenses" lines.

One budget belongs to one training. It is stored as JSON: key variables plus a list of lines, each with a quantity,
a unit cost and a number of times (nights or days). Quantity / unit cost / head count can also be a link to a shared
value, written "=couples" (number of couples), "=trainees" (couples x 2), "=roomrate" (the room rate after
discount, tax and card fee), "=team" (all team people), "=team_dance" (team people at the dinner dance),
"=ta_rooms", "=lunch" "=dinner" "=hors" "=dance" (food rates with banquet service) and so on. Everything else is
arithmetic, so the page, the Excel file and the PDF always agree.
"""
import copy
import json
import math

FORMAT = 2

# (key, label, default, kind, note)  kind: money2 | pct | int
KEY_VARS = [
    ("rack", "Hotel rack rate per room per night", 109, "money2",
     "PLACEHOLDER: one guest's average Fri-Sun rate here in Oct. 2025 (hotelplanner.com), not the rack rate. Replace with the hotel's quote."),
    ("room_discount", "Negotiated discount off room rate", 0.20, "pct", "Percent off the rack rate (0% = none)."),
    ("room_tax", "Hotel tax on rooms", 0.13, "pct", "Total taxes of 13% listed for this hotel. Confirm."),
    ("room_cc", "Credit card processing fee on the hotel bill", 0.035, "pct", "ESTIMATE. Added to the room rate."),
    ("trainee_per_room", "Room count: Trainees, people per room (1 or 2)", 2, "choice12",
     "2 = each couple shares one room. 1 = everyone gets their own room. The number of trainees comes from the couples line in Income."),
    ("fac_people", "Room count: Facilitators (people)", 3, "int", ""),
    ("fac_per_room", "Facilitators: people per room (1 or 2)", 2, "choice12", "Rooms are rounded up (3 people at 2 per room = 2 rooms)."),
    ("ta_people", "Room count: TA's (people)", 10, "int", ""),
    ("ta_per_room", "TA's: people per room (1 or 2)", 2, "choice12", ""),
    ("av_people", "Room count: Audio/Visual (people)", 1, "int", ""),
    ("av_per_room", "Audio/Visual: people per room (1 or 2)", 2, "choice12", ""),
    ("staff_people", "Room count: Staff (people)", 2, "int", ""),
    ("staff_per_room", "Staff: people per room (1 or 2)", 2, "choice12", ""),
    ("lunch_rate", "Lunch rate (per person)", 35, "money2", "Hotel food price before the banquet service charge."),
    ("lunch_svc", "Lunch banquet service charge", 0.25, "pct", "ESTIMATE: hotels commonly add service charge plus tax to food. Confirm."),
    ("dinner_rate", "Dinner rate (per person)", 60, "money2", ""),
    ("dinner_svc", "Dinner banquet service charge", 0.25, "pct", ""),
    ("hors_rate", "d'oeuvres service (flat)", 200, "money2", ""),
    ("hors_svc", "d'oeuvres banquet service charge", 0.25, "pct", ""),
    ("dance_rate", "Dinner/Dance rate (per person)", 75, "money2", ""),
    ("dance_svc", "Dinner/Dance banquet service charge", 0.25, "pct", ""),
    ("contingency", "Budget contingency", 0.05, "pct", "Percent of operating expenses held in reserve."),
]

ART_OF_US_SCHEDULE = [
    "Friday: 3pm Room Set Up - Chairs, Video/Audio, Training Begins 7pm. (Get permission to hang 3 15' banners on the wall)",
    "Saturday: 7:00am - TA Breakfast, Training Begins 8:30 am",
    "Saturday: 12 Noon, 1 Hour Break for Lunch",
    "Saturday: 5pm, Training Concludes, Set up Dance Floor",
    "Saturday: 6:00pm, d'oeuvres delivered",
    "Saturday: 6:30pm, Photos taken",
    "Saturday: 7pm, Doors open, Dinner begins. Dinner Dance Concludes 10 pm",
    "Sunday: TA Breakfast 7am",
    "Sunday: Training Concludes between 1 to 1:30 pm.",
    "Sunday: Breakdown, Room Leave by 3pm",
]


def _L(id, section, label, q, u, t, mode, note="", h=None):
    ln = {"id": id, "section": section, "label": label, "q": q, "u": u, "t": t, "mode": mode, "note": note}
    if h is not None:
        ln["h"] = h
    return ln


# modes: plain (q*u*t) | room (a line added by hand: q*u*t with discount, tax and card fee on the room rate)
DEFAULT_LINES = [
    _L("fee_income", "income", "Total Trainee Couples - Program Fee Income", 40, 1299, 1, "plain",
       "Couples x price per couple ($1,299; one payment covers both partners)"),
    _L("merch", "income", "Merchandise Sales Income", 0, 0, 1, "plain", "None planned"),
    _L("donations", "income", "Financial Partnerships / donations", 0, 0, 1, "plain", "None assumed"),
    _L("r_trainees", "rooms", "Trainees", "=trainee_rooms", "=roomrate", 2, "plain", "Trainees divided by people per room (see Key variables)", h="=trainees"),
    _L("r_fac", "rooms", "Facilitators", "=fac_rooms", "=roomrate", 2, "plain", "", h="=fac"),
    _L("r_ta", "rooms", "TA's", "=ta_rooms", "=roomrate", 2, "plain", "", h="=ta"),
    _L("r_av", "rooms", "Audio/Visual Coordinator", "=av_rooms", "=roomrate", 2, "plain", "", h="=av"),
    _L("r_staff", "rooms", "Staff", "=staff_rooms", "=roomrate", 2, "plain", "", h="=staff"),
    _L("meeting", "rooms", "Meeting rooms / convention center", 0, 0, 1, "plain", "Included with room block"),
    _L("m_fri", "meals", "5pm Friday TA Dinner 5pm", "=team", "=dinner", 1, "plain",
       "Two per room - Hotel included...Trainees are assigned rooms - Double Beds required."),
    _L("m_satb", "meals", "Saturday Breakfast (On your own)", 0, 0, 1, "plain", ""),
    _L("m_lunch", "meals", "Saturday Team Lunch", "=team", "=lunch", 1, "plain",
       "Need private meeting room to have lunch & discuss the training"),
    _L("m_hors", "meals", "Saturday: 6:00pm, d'oeuvres", 1, "=hors", 1, "plain", ""),
    _L("m_dance", "meals", "Saturday Dinner Dance", "=team_dance", "=dance", 1, "plain",
       "All three trainings - Need private meeting room to have lunch & discuss the training"),
    _L("m_sunb", "meals", "Sunday Breakfast (On your own)", 0, 0, 1, "plain", ""),
    _L("m_water", "meals", "Weekend Water and Snacks", 1, 400, 1, "plain", "Water and Snack Basket provided by Discovery"),
    _L("photo", "other", "Photographer", 1, 500, 1, "plain", ""),
    _L("supplies", "other", "Training Supplies & Support", 1, 500, 1, "plain", "ESTIMATE (name tags, workbooks, printing)"),
    _L("marketing", "other", "Marketing & Awareness", 1, 500, 1, "plain", "ESTIMATE"),
    _L("office", "other", "General Office Material", 1, 400, 1, "plain", "Office supplies, software, postage; ESTIMATE"),
    _L("polos", "other", "Polo Shirts with Logo (TA's Security/Greeters/Registration)", 20, 25, 1, "plain", ""),
    _L("hub", "onetime", "HUB Operating Expenses", 1, 300, 1, "plain", ""),
    _L("speakers", "onetime", "Speakers (powered)", 2, 400, 1, "plain", "2 speakers; ESTIMATE, Costco or similar"),
    _L("stands", "onetime", "Speaker stands", 2, 50, 1, "plain", "ESTIMATE"),
    _L("tv", "onetime", "64-inch TV", 1, 500, 1, "plain", "ESTIMATE"),
    _L("tv_stand", "onetime", "Rolling TV stand / platform", 1, 150, 1, "plain", "ESTIMATE"),
    _L("mics", "onetime", "Trainee microphones", 2, 120, 1, "plain", "Kent: 2 microphones for trainees; ESTIMATE"),
    _L("lavs", "onetime", "Lavalier microphones", 3, 150, 1, "plain", "Kent: 3 lavaliers; ESTIMATE (wireless sets cost more)"),
    _L("mixer", "onetime", "Audio mixer", 1, 259, 1, "plain", "https://phenyxpro.com/products/ptl-800"),
    _L("uhf", "onetime", "UHF Wireless Microphone System", 1, 597.99, 1, "plain", "https://phenyxpro.com/products/ptu-6000-8b?variant=45963282743533"),
    _L("mixer_cabinet", "onetime", "Audio mixer rolling cabinet", 1, 319.99, 1, "plain", "https://www.amazon.com/dp/B00BQ91THC"),
    _L("amp", "onetime", "Amplifier", 1, 300, 1, "plain", "https://www.amazon.com/dp/B0099XRF0W/ref=emc_bcc_2_i"),
    _L("cables", "onetime", "Cables and adapters, Misc", 1, 600, 1, "plain", "ESTIMATE, include spares"),
    _L("banners", "onetime", "Printed banners (about 20 ft each)", 3, 250, 1, "plain",
       "Banner 1: \"You can't change or heal what you don't acknowledge.\" Banners 2 and 3: text to be decided; get a printer quote"),
    _L("insurance", "onetime", "General Liability Insurance (annual premium)", 1, 1850, 1, "plain",
       "PLACEHOLDER: Austin paid $1,825 for 2025. Replace with a written quote. Paid once a year, so it is shown here as one-time."),
    _L("npo", "onetime", "501(c)(3) Formation (legal and filing)", 1, 4500, 1, "plain",
       "ESTIMATE: attorney about $3,500 plus the $25 state and $600 IRS filing fees (about $4,125); see the nonprofit packet"),
]

SECTIONS = [
    ("income", "Income"),
    ("rooms", "Hotel rooms"),
    ("meals", "Meals"),
    ("other", "Other operating expenses"),
    ("onetime", "One-time expenses (equipment, banners, insurance, nonprofit setup)"),
]

# column headings that differ by section: (head count, quantity, unit cost, times)
SECTION_COLS = {
    "rooms": ("Head count", "Rooms", "Room rate", "Nights"),
    "meals": (None, "Count", "Rate", "Times"),
}


DONATION_LINES = [
    _L("d_partners", "income", "Financial Partnerships / sponsorships", 0, 0, 1, "plain", "Expected sponsor gifts; enter quantity and average gift"),
    _L("d_gifts", "income", "Individual donations", 0, 0, 1, "plain", "Expected gifts from individuals"),
    _L("d_events", "income", "Fundraising events", 0, 0, 1, "plain", ""),
    _L("d_costs", "other", "Fundraising costs (mailings, events, thank-yous)", 1, 0, 1, "plain", "ESTIMATE"),
    _L("d_proc", "other", "Donation processing fees", 1, 0, 1, "plain", ""),
]


def _lines_for(kind):
    """'training' = everything except one-time expenses; 'fixed' = only the one-time / fixed expenses."""
    if kind == "donations":
        return [copy.deepcopy(ln) for ln in DONATION_LINES]
    if kind == "fixed":
        return [copy.deepcopy(ln) for ln in DEFAULT_LINES if ln["section"] == "onetime"]
    return [copy.deepcopy(ln) for ln in DEFAULT_LINES if ln["section"] != "onetime"]


def sections_for(kind):
    if kind == "donations":
        return [x for x in SECTIONS if x[0] in ("income", "other")]
    return [x for x in SECTIONS if (x[0] == "onetime") == (kind == "fixed")]


def default_budget(title="", kind="training", key=None):
    data = {"format": FORMAT, "title": title, "vars": {k: v for k, _, v, _, _ in KEY_VARS},
            "lines": _lines_for(kind), "dates": "", "hotel": "", "schedule": []}
    if kind == "training" and key == "prog_D4":
        data["dates"] = "February 12–14, 2027"
        data["hotel"] = "Four Points by Sheraton Dallas Fort Worth Airport North."
        data["schedule"] = list(ART_OF_US_SCHEDULE)
    return data


def parse(text, kind="training"):
    """Stored JSON -> (data, is_current). Budgets saved before format 2 come back as is_current False so the
    caller can archive them and start from the new template (donation budgets simply carry over)."""
    try:
        data = json.loads(text)
        if not isinstance(data, dict) or "lines" not in data:
            return None, False
    except (TypeError, ValueError):
        return None, False
    if kind == "donations":
        data["format"] = FORMAT
        is_current = True
    else:
        is_current = data.get("format") == FORMAT
    data.setdefault("vars", {})
    for k, _, v, _, _ in KEY_VARS:
        data["vars"].setdefault(k, v)
    data.setdefault("dates", "")
    data.setdefault("hotel", "")
    data.setdefault("schedule", [])
    # budgets saved before the people-per-room choices had typed-in room counts: switch the untouched ones to the new link
    moves = {"r_trainees": ("=couples", "=trainee_rooms"), "r_fac": (2, "=fac_rooms"), "r_av": (1, "=av_rooms"),
             "r_staff": (1, "=staff_rooms")}
    for ln in data["lines"]:
        m = moves.get(ln.get("id"))
        if m and ln.get("q") == m[0]:
            ln["q"] = m[1]
    return data, is_current


def loads(text, kind="training", key=None):
    data, ok = parse(text, kind)
    if data is None or not ok:
        return default_budget(kind=kind, key=key)
    return data


def _num(x, default=0.0):
    try:
        return float(x)
    except (TypeError, ValueError):
        return default


def derived(data):
    """Calculated values shown beside the key variables (not typed in)."""
    v = {k: _num(data["vars"].get(k)) for k, *_ in KEY_VARS}
    couples = 0.0
    for ln in data.get("lines", []):
        if ln.get("id") == "fee_income":
            couples = _num(ln.get("q"))
    def per(key):
        return 1 if v[key] < 1.5 else 2

    per_room = per("trainee_per_room")
    trainee_people = 2 * couples
    trainee_rooms = math.ceil(trainee_people / per_room)
    rooms = {g: math.ceil(v[g + "_people"] / per(g + "_per_room")) for g in ("fac", "ta", "av", "staff")}
    after_discount = v["rack"] * (1 - v["room_discount"])
    with_tax = after_discount * (1 + v["room_tax"])
    roomrate = with_tax * (1 + v["room_cc"])
    team = v["fac_people"] + v["ta_people"] + v["av_people"] + v["staff_people"]
    return {
        "couples": couples, "per_room": per_room, "trainee_people": trainee_people, "trainee_rooms": trainee_rooms,
        "after_discount": after_discount, "with_tax": with_tax, "roomrate": roomrate,
        "team": team, "team_dance": v["fac_people"] + v["ta_people"] + v["av_people"],
        "fac_rooms": rooms["fac"], "ta_rooms": rooms["ta"], "av_rooms": rooms["av"], "staff_rooms": rooms["staff"],
        "fac_people": v["fac_people"], "ta_people": v["ta_people"], "av_people": v["av_people"], "staff_people": v["staff_people"],
        "lunch": v["lunch_rate"] * (1 + v["lunch_svc"]), "dinner": v["dinner_rate"] * (1 + v["dinner_svc"]),
        "hors": v["hors_rate"] * (1 + v["hors_svc"]), "dance": v["dance_rate"] * (1 + v["dance_svc"]),
    }


def compute(data):
    """Returns (rows, totals). rows keep the input order and gain 'amount', 'qv', 'uv', 'tv', 'hv' (resolved values)."""
    v = {k: _num(data["vars"].get(k)) for k, *_ in KEY_VARS}
    d = derived(data)
    lines = data["lines"]
    by_id = {ln["id"]: ln for ln in lines}
    couples = _num(by_id.get("fee_income", {}).get("q"), 0)
    links = {"=couples": couples, "=trainees": 2 * couples, "=trainee_rooms": d["trainee_rooms"], "=roomrate": d["roomrate"], "=rack": v["rack"],
             "=team": d["team"], "=team_dance": d["team_dance"], "=ta_rooms": d["ta_rooms"], "=fac_rooms": d["fac_rooms"], "=av_rooms": d["av_rooms"], "=staff_rooms": d["staff_rooms"],
             "=lunch": d["lunch"], "=dinner": d["dinner"], "=hors": d["hors"], "=dance": d["dance"],
             "=fac": v["fac_people"], "=ta": v["ta_people"], "=av": v["av_people"], "=staff": v["staff_people"]}

    def resolve(x):
        return links[x] if isinstance(x, str) and x in links else _num(x)

    room_f = (1 - v["room_discount"]) * (1 + v["room_tax"]) * (1 + v["room_cc"])
    rows = []
    for ln in lines:
        q, u, t = resolve(ln["q"]), resolve(ln["u"]), _num(ln["t"], 1)
        amt = q * u * t
        if ln.get("mode") == "room":
            amt *= room_f
        h = resolve(ln["h"]) if "h" in ln else None
        rows.append(dict(ln, qv=q, uv=u, tv=t, amount=amt, hv=h))
    tot = {}
    for sec, _ in SECTIONS:
        tot[sec] = sum(r["amount"] for r in rows if r["section"] == sec)
    operating = tot["rooms"] + tot["meals"] + tot["other"]
    contingency = operating * v["contingency"]
    expenses = operating + contingency
    net = tot["income"] - expenses
    price = _num(by_id.get("fee_income", {}).get("u"))
    couples_n = couples or 1
    room_lines = [r for r in rows if r["section"] == "rooms" and r["hv"] is not None]
    totals = dict(tot, operating=operating, contingency=contingency, expenses=expenses, net=net,
                  net_before_onetime=net, per_couple_expense=expenses / couples_n, per_couple_net=net / couples_n,
                  breakeven=(math.ceil(expenses / price) if price > 0 else None), couples=couples,
                  people=2 * couples + d["team"], room_count=sum(r["qv"] for r in room_lines),
                  head_count=sum(r["hv"] for r in room_lines), price=price, derived=d)
    return rows, totals


def with_onetime(totals, onetime):
    """Adds the 'after one-time expenses' lines (Kent's Total Operating & One Time Expenses, Net Operating Income and
    the break-even that covers everything). `onetime` is the total of the shared one-time budget."""
    t = dict(totals)
    t["onetime_total"] = onetime
    t["all_expenses"] = totals["expenses"] + onetime
    t["net_after_onetime"] = totals["income"] - t["all_expenses"]
    t["breakeven_all"] = math.ceil(t["all_expenses"] / totals["price"]) if totals.get("price", 0) > 0 else None
    return t


def apply_form(data, form):
    """Updates key variables, the heading text and the editable numbers of each line from a posted form."""
    for k, _lbl, _d, kind, _n in KEY_VARS:
        if f"var_{k}" in form:
            val = _num(form.get(f"var_{k}"), data["vars"].get(k, 0) * (100 if kind == "pct" else 1))
            if kind == "choice12":
                val = 1 if val < 1.5 else 2
            data["vars"][k] = val / 100 if kind == "pct" else val
    if "dates" in form:
        data["dates"] = (form.get("dates") or "").strip()[:120]
    if "hotel" in form:
        data["hotel"] = (form.get("hotel") or "").strip()[:200]
    if "schedule" in form:
        data["schedule"] = [s.strip()[:300] for s in (form.get("schedule") or "").splitlines() if s.strip()][:40]
    for ln in data["lines"]:
        for field in ("q", "u", "t"):
            key = f"{field}_{ln['id']}"
            if key in form and not (isinstance(ln[field], str) and ln[field].startswith("=")):
                ln[field] = _num(form.get(key), ln[field])
        if f"note_{ln['id']}" in form:
            ln["note"] = (form.get(f"note_{ln['id']}") or "")[:300]
    # delete ticked lines (the couples/price income line must stay: everything else is based on it)
    data["lines"] = [ln for ln in data["lines"] if ln["id"] == "fee_income" or not form.get(f"del_{ln['id']}")]
    # add new lines, one optional new line per section
    import secrets as _secrets
    for sec, _ in SECTIONS:
        label = (form.get(f"new_label_{sec}") or "").strip()[:120]
        if not label:
            continue
        mode = form.get(f"new_mode_{sec}")
        if mode not in ("plain", "room"):
            mode = "plain"
        new = _L("x" + _secrets.token_hex(4), sec, label, _num(form.get(f"new_q_{sec}"), 1),
                 _num(form.get(f"new_u_{sec}"), 0), _num(form.get(f"new_t_{sec}"), 1), mode,
                 (form.get(f"new_note_{sec}") or "")[:300])
        idx = max([i for i, ln in enumerate(data["lines"]) if ln["section"] == sec], default=len(data["lines"]) - 1)
        data["lines"].insert(idx + 1, new)
    return data
