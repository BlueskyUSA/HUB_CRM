"""Hub Ownership page (Administrator menu): the legal entities that own and use the Hub, the documents that prove it,
and the professionals involved. Owner and Administrators. No passwords, no personal Social Security or bank account numbers."""
from datetime import datetime
from flask import render_template, request, redirect, url_for, session, flash

TABLES = {
    "entity": ("ownership_entities", ["name", "kind", "state", "formed_on", "ein", "address", "registered_agent", "status", "notes"]),
    "doc": ("ownership_documents", ["entity", "title", "status", "doc_date", "where_kept", "link", "notes"]),
    "person": ("ownership_people", ["role", "name", "firm", "email", "phone", "notes"]),
}
DOC_STATUS = ["Not started", "In progress", "Done"]
ENTITY_STATUS = ["Planned", "In progress", "Active"]

SEED_ENTITIES = [
    ("Software and equipment LLC (name to be chosen)", "LLC", "Texas", "Owns the Hub software, the IP and equipment; licenses the software to the nonprofit for its monthly cost (about $200 per month)", "Planned"),
    ("Nonprofit running the trainings (name to be chosen)", "501(c)(3) nonprofit", "Texas", "Runs the trainings, collects fees and donations; pays the LLC the monthly license fee", "Planned"),
    ("InVision Technologies, Inc.", "Corporation", "Texas", "Existing corporation (Coppell, TX)", "Active"),
]
SEED_DOCS = [
    ("Software LLC", "Articles of Organization (Texas Secretary of State)"),
    ("Software LLC", "Operating agreement"),
    ("Software LLC", "EIN confirmation letter from the IRS"),
    ("Software LLC", "Software license agreement with the nonprofit (monthly cost-based fee)"),
    ("Software LLC", "Assignment of the Hub software and code to the LLC"),
    ("Nonprofit", "Certificate of formation"),
    ("Nonprofit", "Bylaws and board list"),
    ("Nonprofit", "EIN confirmation letter from the IRS"),
    ("Nonprofit", "IRS determination letter (501(c)(3))"),
    ("Both", "Agreement with Keith / purchase of the Discovery assets, if reached"),
    ("Both", "Trademark filings and clearance"),
]
SEED_PEOPLE = [("Attorney", ""), ("Accountant / bookkeeper", ""), ("Registered agent", "")]


def _true_owner():
    """Only the real Owner (an Administrator is not the Owner)."""
    return bool(session.get("is_owner")) and not session.get("is_admin")


def register(app, crm, owner_required, get_db):
    def ensure(conn):
        conn.execute("""CREATE TABLE IF NOT EXISTS ownership_entities (id SERIAL PRIMARY KEY, name TEXT, kind TEXT, state TEXT,
            formed_on TEXT, ein TEXT, address TEXT, registered_agent TEXT, status TEXT, notes TEXT, updated_by TEXT, updated_at TEXT)""")
        conn.execute("""CREATE TABLE IF NOT EXISTS ownership_documents (id SERIAL PRIMARY KEY, entity TEXT, title TEXT, status TEXT,
            doc_date TEXT, where_kept TEXT, link TEXT, notes TEXT, updated_by TEXT, updated_at TEXT)""")
        conn.execute("""CREATE TABLE IF NOT EXISTS ownership_people (id SERIAL PRIMARY KEY, role TEXT, name TEXT, firm TEXT,
            email TEXT, phone TEXT, notes TEXT, updated_by TEXT, updated_at TEXT)""")
        conn.execute("""CREATE TABLE IF NOT EXISTS dev_hours (id SERIAL PRIMARY KEY, work_date TEXT, hours DOUBLE PRECISION,
            rate DOUBLE PRECISION, what TEXT, who TEXT, updated_by TEXT, updated_at TEXT)""")
        if not conn.execute("SELECT 1 FROM ownership_entities LIMIT 1").fetchone():
            for n, k, st, notes, status in SEED_ENTITIES:
                conn.execute("INSERT INTO ownership_entities (name, kind, state, notes, status) VALUES (?,?,?,?,?)", (n, k, st, notes, status))
            for e, t in SEED_DOCS:
                conn.execute("INSERT INTO ownership_documents (entity, title, status) VALUES (?,?,'Not started')", (e, t))
            for r, n in SEED_PEOPLE:
                conn.execute("INSERT INTO ownership_people (role, name) VALUES (?,?)", (r, n))
        conn.commit()

    @crm.route("/hub-ownership")
    @owner_required
    def hub_ownership():
        conn = get_db()
        try:
            ensure(conn)
            entities = conn.execute("SELECT * FROM ownership_entities ORDER BY id").fetchall()
            docs = conn.execute("SELECT * FROM ownership_documents ORDER BY id").fetchall()
            people = conn.execute("SELECT * FROM ownership_people ORDER BY id").fetchall()
            months, totals = [], None
            if _true_owner():
                rows = conn.execute("SELECT * FROM dev_hours ORDER BY work_date DESC, id DESC").fetchall()
                by = {}
                for r in rows:
                    by.setdefault((r["work_date"] or "")[:7] or "No date", []).append(r)
                this_month, this_year = datetime.now().strftime("%Y-%m"), datetime.now().strftime("%Y")
                allh = sum((r["hours"] or 0) for r in rows)
                value = sum((r["hours"] or 0) * (r["rate"] or 0) for r in rows)
                totals = dict(all=allh, year=sum((r["hours"] or 0) for r in rows if (r["work_date"] or "")[:4] == this_year),
                              month=sum((r["hours"] or 0) for r in rows if (r["work_date"] or "")[:7] == this_month),
                              value=value, count=len(rows), this_year=this_year)
                for key in sorted(by, reverse=True):
                    try:
                        label = datetime.strptime(key, "%Y-%m").strftime("%B %Y")
                    except ValueError:
                        label = key
                    items = by[key]
                    months.append(dict(key=key, label=label, rows=items, hours=sum((r["hours"] or 0) for r in items),
                                       value=sum((r["hours"] or 0) * (r["rate"] or 0) for r in items)))
        finally:
            conn.close()
        return render_template("hub_ownership.html", entities=entities, docs=docs, people=people,
                               doc_status=DOC_STATUS, entity_status=ENTITY_STATUS,
                               hours_ok=_true_owner(), hour_months=months, hour_totals=totals,
                               today=datetime.now().strftime("%Y-%m-%d"))

    @crm.route("/hub-ownership/hours/save", methods=["POST"])
    @owner_required
    def hub_ownership_hours_save():
        if not _true_owner():
            flash("The development hours are for the Owner only.")
            return redirect(url_for(".hub_ownership"))
        f = request.form
        import re
        txt = re.sub(r"(?i)\s*(hours?|hrs?)\.?\s*$", "", (f.get("hours") or "").replace(",", "").strip())
        try:
            hours = float(txt)
            if not (0 < hours <= 10000):
                raise ValueError
        except ValueError:
            flash("Please enter the hours as a number, such as 1.5 or 200. Nothing was saved.")
            return redirect(url_for(".hub_ownership") + "#hours")
        rate_txt = (f.get("rate") or "").replace("$", "").strip()
        try:
            rate = float(rate_txt) if rate_txt else None
        except ValueError:
            flash("The hourly rate should be a number, such as 75. Nothing was saved.")
            return redirect(url_for(".hub_ownership") + "#hours")
        day = (f.get("work_date") or "").strip()
        try:
            datetime.strptime(day, "%Y-%m-%d")
        except ValueError:
            flash("Please enter the date like 2026-11-19. Nothing was saved.")
            return redirect(url_for(".hub_ownership") + "#hours")
        what, who = (f.get("what") or "").strip(), (f.get("who") or "").strip()
        conn = get_db()
        try:
            ensure(conn)
            rid = f.get("id")
            if rid:
                conn.execute("UPDATE dev_hours SET work_date=?, hours=?, rate=?, what=?, who=?, updated_by=?, updated_at=to_char(now(), 'YYYY-MM-DD') WHERE id=?",
                             (day, hours, rate, what, who, session.get("staff_name"), rid))
            else:
                conn.execute("INSERT INTO dev_hours (work_date, hours, rate, what, who, updated_by, updated_at) VALUES (?,?,?,?,?,?,to_char(now(), 'YYYY-MM-DD'))",
                             (day, hours, rate, what, who, session.get("staff_name")))
            conn.commit()
        finally:
            conn.close()
        flash("Hours saved.")
        return redirect(url_for(".hub_ownership") + "#hours")

    @crm.route("/hub-ownership/hours/<int:rid>/delete", methods=["POST"])
    @owner_required
    def hub_ownership_hours_delete(rid):
        if _true_owner():
            conn = get_db()
            try:
                conn.execute("DELETE FROM dev_hours WHERE id = ?", (rid,))
                conn.commit()
            finally:
                conn.close()
            flash("Removed.")
        return redirect(url_for(".hub_ownership") + "#hours")

    @crm.route("/hub-ownership/<kind>/save", methods=["POST"])
    @owner_required
    def hub_ownership_save(kind):
        if kind not in TABLES:
            return redirect(url_for(".hub_ownership"))
        table, cols = TABLES[kind]
        f = request.form
        vals = [(f.get(c) or "").strip() for c in cols]
        if not any(vals[:2]):
            flash("Nothing to save.")
            return redirect(url_for(".hub_ownership") + "#" + kind)
        who = session.get("staff_name")
        conn = get_db()
        try:
            ensure(conn)
            rid = f.get("id")
            if rid:
                sets = ", ".join(f"{c} = ?" for c in cols)
                conn.execute(f"UPDATE {table} SET {sets}, updated_by = ?, updated_at = to_char(now(), 'YYYY-MM-DD') WHERE id = ?",
                             vals + [who, rid])
            else:
                names = ", ".join(cols)
                marks = ", ".join("?" for _ in cols)
                conn.execute(f"INSERT INTO {table} ({names}, updated_by, updated_at) VALUES ({marks}, ?, to_char(now(), 'YYYY-MM-DD'))",
                             vals + [who])
            conn.commit()
        finally:
            conn.close()
        flash("Saved.")
        return redirect(url_for(".hub_ownership") + "#" + kind)

    @crm.route("/hub-ownership/<kind>/<int:rid>/delete", methods=["POST"])
    @owner_required
    def hub_ownership_delete(kind, rid):
        if kind in TABLES:
            conn = get_db()
            try:
                conn.execute(f"DELETE FROM {TABLES[kind][0]} WHERE id = ?", (rid,))
                conn.commit()
            finally:
                conn.close()
            flash("Removed.")
        return redirect(url_for(".hub_ownership") + "#" + kind)
