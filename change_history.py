"""Change history (Administrator menu): who changed what, and when. Every save, add, remove or import made inside the Hub is
recorded automatically with the person's name, the time, the page, and the message the Hub showed afterward.
It never records what was typed into a form (so no passwords or private details are copied into the log)."""
import re
from datetime import datetime
from flask import render_template, request, session, flash

PAGE = 100
SKIP_PREFIXES = ("crm.chat", "crm.keepalive", "crm.logout")
LOGIN_ENDPOINTS = ("crm.login", "crm.team_login", "crm.leadership_login", "crm.accounting_login",
                   "crm.administrator_login", "crm.owner_login")


def _ensure(conn):
    conn.execute("""CREATE TABLE IF NOT EXISTS change_log (id SERIAL PRIMARY KEY, at TEXT, staff_id INTEGER, staff_name TEXT,
        staff_role TEXT, action TEXT, path TEXT, result TEXT)""")
    conn.commit()


def _label(endpoint):
    name = (endpoint or "").split(".")[-1]
    return re.sub(r"\s+", " ", name.replace("_", " ")).strip().capitalize() or "Change"


def register(app, crm, owner_required, get_db):
    @crm.after_request
    def _record(resp):
        try:
            ep = request.endpoint or ""
            if request.method != "POST" or ep.startswith(SKIP_PREFIXES) or not session.get("staff_id") or resp.status_code >= 400:
                return resp
            result = ""
            fl = session.get("_flashes") or []
            if fl:
                result = str(fl[-1][1])[:240]
            action = "Signed in" if ep in LOGIN_ENDPOINTS else _label(ep)
            if ep in LOGIN_ENDPOINTS and not resp.headers.get("Location"):
                return resp
            conn = get_db()
            try:
                _ensure(conn)
                conn.execute("""INSERT INTO change_log (at, staff_id, staff_name, staff_role, action, path, result)
                                VALUES (?,?,?,?,?,?,?)""",
                             (datetime.now().strftime("%Y-%m-%d %H:%M:%S"), session.get("staff_id"), session.get("staff_name"),
                              "Administrator" if session.get("is_admin") else ("Owner" if session.get("is_owner") else session.get("staff_role")),
                              action, request.path[:200], result))
                conn.commit()
            finally:
                conn.close()
        except Exception as e:     # keeping a record must never break the page
            print(f"Change history could not be recorded: {e}", flush=True)
        return resp

    @crm.route("/change-history")
    @owner_required
    def change_history():
        q = (request.args.get("q") or "").strip()
        try:
            page = max(1, int(request.args.get("page") or 1))
        except ValueError:
            page = 1
        where, args = "", []
        if q:
            where = "WHERE staff_name ILIKE ? OR action ILIKE ? OR path ILIKE ? OR result ILIKE ?"
            args = [f"%{q}%"] * 4
        conn = get_db()
        try:
            _ensure(conn)
            total = conn.execute(f"SELECT COUNT(*) c FROM change_log {where}", args).fetchone()["c"]
            rows = conn.execute(f"SELECT * FROM change_log {where} ORDER BY id DESC LIMIT ? OFFSET ?",
                                args + [PAGE, (page - 1) * PAGE]).fetchall()
        finally:
            conn.close()
        pages = max(1, (total + PAGE - 1) // PAGE)
        return render_template("change_history.html", rows=rows, q=q, page=page, pages=pages, total=total)
