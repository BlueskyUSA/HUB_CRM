"""Change history (Administrator menu): who changed what, and when. Every save, add, remove or import made inside the Hub is
recorded automatically with the person's name, the time, the page, and the message the Hub showed afterward.
It never records what was typed into a form (so no passwords or private details are copied into the log)."""
import re
import time
from datetime import datetime, timezone
from flask import render_template, request, session, flash

PAGE = 100
SKIP_PREFIXES = ("crm.chat", "crm.keepalive", "crm.logout")
ROLE_WORDS = {"Team": "Volunteer Team", "Leadership": "Leadership", "Accounting": "Accounting & Legal"}
LOGIN_ENDPOINTS = ("crm.login", "crm.team_login", "crm.leadership_login", "crm.accounting_login",
                   "crm.administrator_login", "crm.owner_login")


def _central(at):
    """The log stores the server's clock (UTC on Render). Show it in Central time so dates match the person's day."""
    try:
        dt = datetime.strptime((at or "")[:19], "%Y-%m-%d %H:%M:%S")
    except ValueError:
        return at or ""
    if time.timezone == 0 and not time.daylight:
        try:
            from zoneinfo import ZoneInfo
            dt = dt.replace(tzinfo=timezone.utc).astimezone(ZoneInfo("America/Chicago")).replace(tzinfo=None)
        except Exception:
            pass
    return dt.strftime("%Y-%m-%d %H:%M:%S")


def _clock(at):
    try:
        return datetime.strptime(at[:19], "%Y-%m-%d %H:%M:%S").strftime("%I:%M %p").lstrip("0")
    except ValueError:
        return at


def _daylabel(day):
    try:
        return datetime.strptime(day, "%Y-%m-%d").strftime("%A, %B %d, %Y").replace(" 0", " ")
    except ValueError:
        return day


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

    @crm.after_request
    def _record_visit(resp):
        """Note that a signed-in person is looking around the Hub, even if they save nothing.
        A 'Visited the Hub' entry is added when they come back after 30+ minutes away; last-seen is refreshed at most every 5 minutes."""
        try:
            ep = request.endpoint or ""
            if (request.method != "GET" or ep.startswith(SKIP_PREFIXES) or ep in LOGIN_ENDPOINTS or not session.get("staff_id")
                    or resp.status_code != 200 or "text/html" not in (resp.content_type or "")):
                return resp
            now = datetime.now()
            last = session.get("seen_log_at")
            if last:
                try:
                    if (now - datetime.fromisoformat(last)).total_seconds() < 300:
                        return resp
                except ValueError:
                    pass
            stamp = now.strftime("%Y-%m-%d %H:%M:%S")
            conn = get_db()
            try:
                _ensure(conn)
                conn.execute("CREATE TABLE IF NOT EXISTS staff_seen (staff_id INTEGER PRIMARY KEY, last_seen TEXT)")
                row = conn.execute("SELECT last_seen FROM staff_seen WHERE staff_id = ?", (session.get("staff_id"),)).fetchone()
                gap_long = True
                if row and row["last_seen"]:
                    try:
                        gap_long = (now - datetime.strptime(row["last_seen"], "%Y-%m-%d %H:%M:%S")).total_seconds() > 1800
                    except ValueError:
                        gap_long = True
                if row:
                    conn.execute("UPDATE staff_seen SET last_seen = ? WHERE staff_id = ?", (stamp, session.get("staff_id")))
                else:
                    conn.execute("INSERT INTO staff_seen (staff_id, last_seen) VALUES (?, ?)", (session.get("staff_id"), stamp))
                if gap_long:
                    conn.execute("""INSERT INTO change_log (at, staff_id, staff_name, staff_role, action, path, result)
                                    VALUES (?,?,?,?,?,?,?)""",
                                 (stamp, session.get("staff_id"), session.get("staff_name"),
                                  "Administrator" if session.get("is_admin") else ("Owner" if session.get("is_owner") else session.get("staff_role")),
                                  "Visited the Hub", request.path[:200], "Looking around (no change made)"))
                conn.commit()
            finally:
                conn.close()
            session["seen_log_at"] = now.isoformat()
        except Exception as e:     # keeping a record must never break the page
            print(f"Visit could not be recorded: {e}", flush=True)
        return resp

    def _may_view():
        """The real Owner, or anyone the Owner has ticked 'Change/Access History' for."""
        if session.get("is_owner") and not session.get("is_admin"):
            return True
        if not session.get("staff_id"):
            return False
        conn = get_db()
        try:
            return bool(conn.execute("SELECT 1 FROM access_grants WHERE area_key = 'change_history' AND staff_id = ?",
                                     (session.get("staff_id"),)).fetchone())
        finally:
            conn.close()

    @crm.route("/change-history")
    def change_history():
        if not _may_view():
            return render_template("change_history_owner_only.html")
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
            rows = [dict(r, at=_central(r["at"])) for r in conn.execute(f"SELECT * FROM change_log {where} ORDER BY id DESC LIMIT ? OFFSET ?",
                                args + [PAGE, (page - 1) * PAGE]).fetchall()]
            # One drop-down per person: everyone with a login, plus anyone who appears in the log.
            staff = {r["id"]: r for r in conn.execute("SELECT id, name, role, is_owner, active FROM staff").fetchall()}
            stats = {r["staff_id"]: r for r in conn.execute(
                """SELECT staff_id, MAX(id) AS mid, COUNT(*) AS n, MAX(at) AS last_at,
                          MAX(CASE WHEN action = 'Signed in' THEN at END) AS last_in
                   FROM change_log WHERE staff_id IS NOT NULL GROUP BY staff_id""").fetchall()}
            try:
                seen = {r["staff_id"]: r["last_seen"] for r in conn.execute("SELECT staff_id, last_seen FROM staff_seen").fetchall()}
            except Exception:
                try: conn.rollback()
                except Exception: pass
                seen = {}
            # Signs of activity that exist in the Hub's other records, for the time before this log began.
            earlier = {}
            def _add(sid, at, text):
                if sid is not None and at:
                    earlier.setdefault(sid, []).append((str(at)[:16].replace("T", " "), text))
            def _try(sql, fn):
                try:
                    for r in conn.execute(sql).fetchall():
                        fn(r)
                except Exception:
                    try: conn.rollback()
                    except Exception: pass
            _try("SELECT staff_id, MAX(used_at) AS at, COUNT(*) AS n FROM staff_invites WHERE used_at IS NOT NULL GROUP BY staff_id",
                 lambda r: _add(r["staff_id"], r["at"], "Set their own password from the welcome link"))
            _try("SELECT staff_id, board_seen AS at FROM chat_seen WHERE board_seen IS NOT NULL AND board_seen <> ''",
                 lambda r: _add(r["staff_id"], r["at"], "Opened the Team Chat board"))
            for tbl, label in (("chat_topics", "started a Team Chat topic"), ("chat_replies", "replied in Team Chat"), ("chat_messages", "wrote in the Team Chat room")):
                _try(f"SELECT author_id, MAX(created_at) AS at, COUNT(*) AS n FROM {tbl} GROUP BY author_id",
                     lambda r, label=label: _add(r["author_id"], r["at"], f"Chat: {label} ({r['n']} in all)"))
            _try("SELECT claimed_by, MAX(claimed_at) AS at, COUNT(*) AS n FROM call_requests WHERE claimed_by IS NOT NULL GROUP BY claimed_by",
                 lambda r: _add(r["claimed_by"], r["at"], f"Claimed a call request ({r['n']} in all)"))
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
                acts = [dict(r, at=_central(r["at"])) for r in conn.execute(
                    "SELECT at, action, path, result FROM change_log WHERE staff_id = ? ORDER BY id DESC LIMIT 500", (sid,)).fetchall()] if n else []
                days = []
                for a in acts:
                    day = a["at"][:10]
                    if not days or days[-1]["day"] != day:
                        days.append(dict(day=day, label=_daylabel(day), entries=[]))
                    days[-1]["entries"].append(a)
                for d in days:
                    times = [_clock(x["at"]) for x in d["entries"]]
                    d["first"], d["last"] = times[-1], times[0]
                    d["signins"] = sum(1 for x in d["entries"] if x["action"] == "Signed in")
                people.append(dict(id=sid, name=name, role=role, active=active, n=n,
                                   last_at=_central(sx["last_at"]) if sx else "", last_in=_central(sx["last_in"]) if (sx and sx["last_in"]) else "", seen=_central(seen.get(sid, "")) if seen.get(sid) else "", acts=acts, days=days,
                                   earlier=sorted(earlier.get(sid, []), reverse=True)))
            people.sort(key=lambda p: p["name"].lower())
            people.sort(key=lambda p: p["last_at"] or "", reverse=True)
            people.sort(key=lambda p: p["n"] == 0)      # people with no activity go last (stable)
        finally:
            conn.close()
        pages = max(1, (total + PAGE - 1) // PAGE)
        return render_template("change_history.html", rows=rows, q=q, page=page, pages=pages, total=total,
                               show_owner=show_owner, who=who, who_id=who_id, people=people)
