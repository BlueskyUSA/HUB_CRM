"""Change history (Administrator menu): who changed what, and when. Every save, add, remove or import made inside the Hub is
recorded automatically with the person's name, the time, the page, and the message the Hub showed afterward.
It never records what was typed into a form (so no passwords or private details are copied into the log)."""
import re
from datetime import datetime
from flask import render_template, request, session, flash

PAGE = 100
SKIP_PREFIXES = ("crm.chat", "crm.keepalive", "crm.logout")
ROLE_WORDS = {"Team": "Volunteer Team", "Leadership": "Leadership", "Accounting": "Accounting & Legal"}
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
        show_owner = request.args.get("owner") == "1"
        who = request.args.get("who") or ""
        who_id = int(who) if who.isdigit() else None
        conds, args = [], []
        if not show_owner:
            conds.append("COALESCE(staff_role, '') <> 'Owner'")      # the everyone-list hides Owner activity unless asked for
        if q:
            conds.append("(staff_name ILIKE ? OR action ILIKE ? OR path ILIKE ? OR result ILIKE ?)")
            args += [f"%{q}%"] * 4
        where = ("WHERE " + " AND ".join(conds)) if conds else ""
        conn = get_db()
        try:
            _ensure(conn)
            total = conn.execute(f"SELECT COUNT(*) c FROM change_log {where}", args).fetchone()["c"]
            rows = conn.execute(f"SELECT * FROM change_log {where} ORDER BY id DESC LIMIT ? OFFSET ?",
                                args + [PAGE, (page - 1) * PAGE]).fetchall()
            # One drop-down per person: everyone with a login, plus anyone who appears in the log.
            staff = {r["id"]: r for r in conn.execute("SELECT id, name, role, is_owner, active FROM staff").fetchall()}
            stats = {r["staff_id"]: r for r in conn.execute(
                """SELECT staff_id, MAX(id) AS mid, COUNT(*) AS n, MAX(at) AS last_at,
                          MAX(CASE WHEN action = 'Signed in' THEN at END) AS last_in
                   FROM change_log WHERE staff_id IS NOT NULL GROUP BY staff_id""").fetchall()}
            people = []
            for sid in set(staff) | set(stats):
                st, sx = staff.get(sid), stats.get(sid)
                if st is not None and not st["active"] and not sx:
                    continue
                if st is not None:
                    name = st["name"]
                    role = "Owner" if st["is_owner"] == 1 else ("Administrator" if st["is_owner"] == 2 else ROLE_WORDS.get(st["role"], st["role"]))
                    active = bool(st["active"])
                else:
                    last = conn.execute("SELECT staff_name, staff_role FROM change_log WHERE id = ?", (sx["mid"],)).fetchone()
                    name, role, active = (last["staff_name"] or "Unknown"), (last["staff_role"] or ""), False
                n = sx["n"] if sx else 0
                cap = 300 if sid == who_id else 25
                acts = conn.execute("SELECT at, action, path, result FROM change_log WHERE staff_id = ? ORDER BY id DESC LIMIT ?",
                                    (sid, cap)).fetchall() if n else []
                people.append(dict(id=sid, name=name, role=role, active=active, n=n,
                                   last_at=(sx["last_at"] if sx else ""), last_in=(sx["last_in"] if sx else ""), acts=acts))
            people.sort(key=lambda p: p["name"].lower())
            people.sort(key=lambda p: p["last_at"] or "", reverse=True)
            people.sort(key=lambda p: p["n"] == 0)      # people with no activity go last (stable)
        finally:
            conn.close()
        pages = max(1, (total + PAGE - 1) // PAGE)
        return render_template("change_history.html", rows=rows, q=q, page=page, pages=pages, total=total,
                               show_owner=show_owner, who=who, who_id=who_id, people=people)
