"""Annual report (public "Finances" page): actual revenue and spending for each year and a link to the Form 990.
The Owner or an Administrator types the figures in the Hub and ticks "Show on the public site" for a year when it is ready.
Nothing is public until a year is published, and the Finances button only appears once at least one year is."""
import re
from datetime import datetime
from flask import render_template, request, redirect, url_for, session, flash


def _ensure(conn):
    conn.execute("""CREATE TABLE IF NOT EXISTS annual_reports (id SERIAL PRIMARY KEY, year INTEGER NOT NULL UNIQUE,
        published INTEGER NOT NULL DEFAULT 0, form990_url TEXT, note TEXT, revenue_text TEXT, expense_text TEXT,
        updated_by TEXT, updated_at TEXT)""")
    conn.commit()


DEFAULT_REVENUE = ["Training fees", "Donations and sponsorships", "Other revenue"]
DEFAULT_SPENDING = ["Venues and facilities", "Food", "Materials and printing", "Marketing", "Software and technology",
                    "Insurance, fees and professional services", "Other spending"]


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


def published_years(get_db):
    try:
        conn = get_db()
        try:
            _ensure(conn)
            rows = conn.execute("SELECT * FROM annual_reports WHERE published = 1 ORDER BY year DESC").fetchall()
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


def years_for_public(get_db):
    """Published years; if none are published yet, the current year with every line at $0 so the page is never empty."""
    ys = published_years(get_db)
    if ys:
        return ys
    rev, _ = parse_lines(_zero_text(DEFAULT_REVENUE)); exp, _ = parse_lines(_zero_text(DEFAULT_SPENDING))
    return [dict(year=datetime.now().year, revenue=rev, expenses=exp, total_rev=0, total_exp=0, net=0, form990_url=None, note=None)]


def register(app, crm, owner_required, get_db):
    app.jinja_env.filters.setdefault("money", money)

    @app.route("/about-the-program/finances")
    def public_finances():
        years = years_for_public(get_db)
        return render_template("public_finances.html", years=years)

    @crm.route("/annual-report")
    @owner_required
    def annual_report_hub():
        conn = get_db()
        try:
            _ensure(conn)
            rows = conn.execute("SELECT * FROM annual_reports ORDER BY year DESC").fetchall()
        finally:
            conn.close()
        return render_template("annual_report_hub.html", rows=rows, this_year=datetime.now().year)

    @crm.route("/annual-report/save", methods=["POST"])
    @owner_required
    def annual_report_save():
        try:
            year = int(request.form.get("year") or 0)
        except ValueError:
            year = 0
        if year < 2000 or year > 2100:
            flash("Please give a year such as 2026. Nothing was saved.")
            return redirect(url_for(".annual_report_hub"))
        if "revenue_text" not in request.form:      # the "Add a year" form: start from the standard lines at zero
            rev, exp = _zero_text(DEFAULT_REVENUE), _zero_text(DEFAULT_SPENDING)
        else:
            rev = request.form.get("revenue_text") or ""
            exp = request.form.get("expense_text") or ""
        bad = parse_lines(rev)[1] + parse_lines(exp)[1]
        if bad:
            flash("These lines were not understood, so nothing was saved. Use: Label | amount (for example: Training fees | 48,500). Problem lines: " + "; ".join(b[:60] for b in bad[:5]))
            return redirect(url_for(".annual_report_hub") + f"#y{year}")
        url = (request.form.get("form990_url") or "").strip()
        if url and not re.match(r"https?://", url, re.I):
            flash("The Form 990 link must start with http:// or https://. Nothing was saved.")
            return redirect(url_for(".annual_report_hub") + f"#y{year}")
        published = 1 if request.form.get("published") else 0
        now = datetime.now().strftime("%Y-%m-%d %H:%M")
        conn = get_db()
        try:
            _ensure(conn)
            conn.execute("""INSERT INTO annual_reports (year, published, form990_url, note, revenue_text, expense_text, updated_by, updated_at)
                            VALUES (?,?,?,?,?,?,?,?)
                            ON CONFLICT (year) DO UPDATE SET published = EXCLUDED.published, form990_url = EXCLUDED.form990_url,
                              note = EXCLUDED.note, revenue_text = EXCLUDED.revenue_text, expense_text = EXCLUDED.expense_text,
                              updated_by = EXCLUDED.updated_by, updated_at = EXCLUDED.updated_at""",
                         (year, published, url or None, (request.form.get("note") or "").strip() or None, rev.strip(), exp.strip(),
                          session.get("staff_name"), now))
            conn.commit()
        finally:
            conn.close()
        flash(f"{year} saved." + (" It is showing on the public site." if published else " It is NOT public yet."))
        return redirect(url_for(".annual_report_hub") + f"#y{year}")

    @crm.route("/annual-report/<int:year>/delete", methods=["POST"])
    @owner_required
    def annual_report_delete(year):
        conn = get_db()
        try:
            conn.execute("DELETE FROM annual_reports WHERE year = ?", (year,))
            conn.commit()
        finally:
            conn.close()
        flash(f"{year} was removed.")
        return redirect(url_for(".annual_report_hub"))
