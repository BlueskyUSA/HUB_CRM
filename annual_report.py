"""Annual report (public "Finances" page): actual revenue and spending for each year and a link to the Form 990.
The Owner or an Administrator types the figures in the Hub and ticks "Show on the public site" for a year when it is ready.
Nothing is public until a year is published, and the Finances button only appears once at least one year is."""
import re
from datetime import datetime
from flask import render_template, request, redirect, url_for, session, flash


ENTITIES = {
    "nonprofit": dict(title="Nonprofit (Form 990)", short="Nonprofit",
                      revenue=["Training fees", "Donations and sponsorships", "Other revenue"],
                      spending=["Venues and facilities", "Food", "Materials and printing", "Marketing",
                                "Software license fee to the LLC", "Insurance, fees and professional services", "Other spending"]),
    "llc": dict(title="Software LLC", short="Software LLC",
                revenue=["Software license fees from the nonprofit", "Other revenue"],
                spending=["Claude, ChatGPT (AI tools)", "GitHub", "Render (hosting)", "Brevo (email)", "Pushover (phone alerts)",
                          "QuickBooks Online", "Other infrastructure and fees"]),
}


def _ensure(conn):
    conn.execute("""CREATE TABLE IF NOT EXISTS annual_reports (id SERIAL PRIMARY KEY, year INTEGER NOT NULL,
        published INTEGER NOT NULL DEFAULT 0, form990_url TEXT, note TEXT, revenue_text TEXT, expense_text TEXT,
        updated_by TEXT, updated_at TEXT)""")
    conn.execute("ALTER TABLE annual_reports ADD COLUMN IF NOT EXISTS entity TEXT NOT NULL DEFAULT 'nonprofit'")
    conn.execute("ALTER TABLE annual_reports DROP CONSTRAINT IF EXISTS annual_reports_year_key")
    conn.execute("CREATE UNIQUE INDEX IF NOT EXISTS annual_reports_entity_year ON annual_reports (entity, year)")
    conn.commit()


def _zero_text(labels):
    return "\n".join(f"{l} | 0" for l in labels)


def parse_lines(text):
    """'Label | amount' per line -> (rows, bad_lines). Amount may have $ and commas."""
    rows, bad = [], []
    for raw in (text or "").splitlines():
        line = raw.strip()
        if not line:
            continue
        if "|" not in line:
            bad.append(line); continue
        label, amt = line.rsplit("|", 1)
        label = label.strip()
        a = re.sub(r"[\s$,]", "", amt)
        neg = a.startswith("(") and a.endswith(")")
        a = a.strip("()")
        try:
            v = round(float(a) * (-1 if neg else 1), 2)
        except ValueError:
            bad.append(line); continue
        if not label:
            bad.append(line); continue
        rows.append((label, v))
    return rows, bad


def money(v):
    return ("-$" if v < 0 else "$") + f"{abs(v):,.0f}" if float(v).is_integer() else ("-$" if v < 0 else "$") + f"{abs(v):,.2f}"


def published_years(get_db, entity="nonprofit"):
    try:
        conn = get_db()
        try:
            _ensure(conn)
            rows = conn.execute("SELECT * FROM annual_reports WHERE published = 1 AND entity = ? ORDER BY year DESC", (entity,)).fetchall()
        finally:
            conn.close()
        out = []
        for r in rows:
            rev, _ = parse_lines(r["revenue_text"]); exp, _ = parse_lines(r["expense_text"])
            tr = sum(v for _, v in rev); te = sum(v for _, v in exp)
            out.append(dict(year=r["year"], revenue=rev, expenses=exp, total_rev=tr, total_exp=te, net=tr - te,
                            form990_url=r["form990_url"], note=r["note"]))
        return out
    except Exception:
        return []


def reports_for_public(get_db):
    """[(title, years)]: the nonprofit always (current year at $0 until a year is published); the LLC only once a year is published."""
    out = []
    ys = published_years(get_db, "nonprofit")
    if not ys:
        e = ENTITIES["nonprofit"]
        rev, _ = parse_lines(_zero_text(e["revenue"])); exp, _ = parse_lines(_zero_text(e["spending"]))
        ys = [dict(year=datetime.now().year, revenue=rev, expenses=exp, total_rev=0, total_exp=0, net=0, form990_url=None, note=None)]
    out.append((ENTITIES["nonprofit"]["title"], "nonprofit", ys))
    ly = published_years(get_db, "llc")
    if ly:
        out.append((ENTITIES["llc"]["title"], "llc", ly))
    return out


def register(app, crm, owner_required, get_db):
    app.jinja_env.filters.setdefault("money", money)

    @app.route("/about-the-program/finances")
    def public_finances():
        return render_template("public_finances.html", reports=reports_for_public(get_db))

    @crm.route("/annual-report")
    @owner_required
    def annual_report_hub():
        conn = get_db()
        try:
            _ensure(conn)
            rows = conn.execute("SELECT * FROM annual_reports ORDER BY year DESC").fetchall()
        finally:
            conn.close()
        return render_template("annual_report_hub.html", rows=rows, this_year=datetime.now().year, entities=ENTITIES)

    @crm.route("/annual-report/save", methods=["POST"])
    @owner_required
    def annual_report_save():
        entity = request.form.get("entity") or "nonprofit"
        if entity not in ENTITIES:
            entity = "nonprofit"
        try:
            year = int(request.form.get("year") or 0)
        except ValueError:
            year = 0
        if year < 2000 or year > 2100:
            flash("Please give a year such as 2026. Nothing was saved.")
            return redirect(url_for(".annual_report_hub"))
        if "revenue_text" not in request.form:      # the "Add a year" form: start from the standard lines at zero
            rev, exp = _zero_text(ENTITIES[entity]["revenue"]), _zero_text(ENTITIES[entity]["spending"])
        else:
            rev = request.form.get("revenue_text") or ""
            exp = request.form.get("expense_text") or ""
        bad = parse_lines(rev)[1] + parse_lines(exp)[1]
        if bad:
            flash("These lines were not understood, so nothing was saved. Use: Label | amount (for example: Training fees | 48,500). Problem lines: " + "; ".join(b[:60] for b in bad[:5]))
            return redirect(url_for(".annual_report_hub") + f"#y{entity}{year}")
        url = (request.form.get("form990_url") or "").strip()
        if url and not re.match(r"https?://", url, re.I):
            flash("The Form 990 link must start with http:// or https://. Nothing was saved.")
            return redirect(url_for(".annual_report_hub") + f"#y{entity}{year}")
        published = 1 if request.form.get("published") else 0
        now = datetime.now().strftime("%Y-%m-%d %H:%M")
        conn = get_db()
        try:
            _ensure(conn)
            conn.execute("""INSERT INTO annual_reports (entity, year, published, form990_url, note, revenue_text, expense_text, updated_by, updated_at)
                            VALUES (?,?,?,?,?,?,?,?,?)
                            ON CONFLICT (entity, year) DO UPDATE SET published = EXCLUDED.published, form990_url = EXCLUDED.form990_url,
                              note = EXCLUDED.note, revenue_text = EXCLUDED.revenue_text, expense_text = EXCLUDED.expense_text,
                              updated_by = EXCLUDED.updated_by, updated_at = EXCLUDED.updated_at""",
                         (entity, year, published, url or None, (request.form.get("note") or "").strip() or None, rev.strip(), exp.strip(),
                          session.get("staff_name"), now))
            conn.commit()
        finally:
            conn.close()
        flash(f"{ENTITIES[entity]['short']} {year} saved." + (" It is showing on the public site." if published else " It is NOT public yet."))
        return redirect(url_for(".annual_report_hub") + f"#y{entity}{year}")

    @crm.route("/annual-report/<entity>/<int:year>/delete", methods=["POST"])
    @owner_required
    def annual_report_delete(entity, year):
        conn = get_db()
        try:
            conn.execute("DELETE FROM annual_reports WHERE entity = ? AND year = ?", (entity, year))
            conn.commit()
        finally:
            conn.close()
        flash(f"{year} was removed.")
        return redirect(url_for(".annual_report_hub"))
