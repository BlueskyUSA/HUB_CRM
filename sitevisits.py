"""Site Visits: a privacy-friendly visit counter for the public website, plus personal links.

What it records, for each public page a visitor opens: the date and time, the page, the website they came from (just the
site name), the kind of device, and a random visitor number kept in a cookie. It never records IP addresses, names or
anything typed into a form. Search-engine bots and link-preview robots are skipped, and so are team members who are
logged in and visitors whose browser says "Do Not Track".

Personal links: the Owner makes a link such as https://<site>/v/abc123 for one person or group. When someone opens it they
land on the page the Owner chose, and every page they look at during that visit (and for 30 days after) is tied to that
link. A link tells you the link was opened, not who is holding the phone: a forwarded link or a mail program that opens
links automatically can look like a visit.

Private preview: while it is ON (the Owner switches it on the Site Visits page) the public marketing pages show a "coming soon"
page to everyone except logged-in team members and people who opened one of the Owner's personal links, which work as
invitations (a signed cookie keeps the invitation for 90 days; turning a link off cancels it). Pages people reach by a private
emailed link (questionnaires, profile links, feedback, unsubscribe and so on) are not affected.

Owner-only page: Site Visits (under the Administrator menu).
"""
import hashlib
import hmac
import os
import re
import secrets
import time
from datetime import datetime, timedelta
from urllib.parse import urlparse
from zoneinfo import ZoneInfo

from flask import render_template, request, redirect, url_for, flash, session, g, make_response, abort

CT = ZoneInfo("America/Chicago")
COOKIE_VISITOR = "sv"        # random visitor number, one year
COOKIE_LINK = "svl"          # which personal link brought them, 30 days
COOKIE_FIRST = "svf"         # "this is the first page after opening a link", one day
COOKIE_INVITE = "svi"        # signed invitation, 90 days
_ready = False
_cache = {"at": 0.0, "private": True, "message": "", "active": set()}

# The public marketing pages the private preview covers. Pages reached by an emailed private link are deliberately not here.
GATED_EXACT = {"/", "/relationship-training", "/our-story", "/meet-the-team", "/about-the-program", "/programs", "/register",
               "/contact", "/reconnect", "/discovery", "/donate", "/free-book", "/free-resources", "/stories", "/sponsor",
               "/sponsor-training", "/talk-to-us", "/talk-to-us/thanks", "/share"}
GATED_PREFIX = ("/programs/", "/free-resources/", "/stories/", "/preview/")

# Pages the Owner can point a personal link at.
LINK_TARGETS = [
    ("/", "Home"),
    ("/programs/the-art-of-us", "The Art of Us"),
    ("/programs/the-beginning", "The Beginning"),
    ("/programs/awakening", "Awakening"),
    ("/programs/vision", "Vision"),
    ("/about-the-program", "About"),
    ("/free-resources", "Recommended Resources"),
    ("/register", "Register"),
    ("/donate", "Donate"),
]
PAGE_NAMES = dict(LINK_TARGETS)
PAGE_NAMES.update({
    "/programs": "Programs", "/our-story": "Our Story, Our Mission", "/meet-the-team": "Meet the Team",
    "/contact": "Contact", "/free-book": "Free little book", "/free-resources/brain": "The Remarkable Human Brain",
})

_BOT_WORDS = (
    "bot", "crawl", "spider", "slurp", "preview", "facebookexternalhit", "whatsapp", "curl/", "python-requests", "python-urllib",
    "monitor", "uptime", "headless", "lighthouse", "wget", "go-http", "okhttp", "scanner", "mail.ru", "skypeuri",
    "proofpoint", "barracuda", "mimecast", "safelinks", "pingdom", "datadog", "node-fetch", "axios", "java/", "httpclient",
    "feedfetcher", "embedly",
)


def is_bot(ua):
    ua = (ua or "").lower()
    return len(ua) < 20 or any(w in ua for w in _BOT_WORDS)


def device_of(ua):
    ua = (ua or "").lower()
    if "ipad" in ua or "tablet" in ua:
        return "Tablet"
    if "mobi" in ua or "iphone" in ua or "android" in ua:
        return "Phone"
    return "Computer"


def _ensure(conn):
    global _ready
    if _ready:
        return
    conn.execute("""CREATE TABLE IF NOT EXISTS site_visit_links (
        id SERIAL PRIMARY KEY, token TEXT NOT NULL UNIQUE, label TEXT NOT NULL, contact_id INTEGER,
        target_path TEXT NOT NULL DEFAULT '/', created_at TEXT NOT NULL, active INTEGER NOT NULL DEFAULT 1)""")
    conn.execute("""CREATE TABLE IF NOT EXISTS site_visits (
        id SERIAL PRIMARY KEY, seen_at TEXT NOT NULL, seen_day TEXT NOT NULL, path TEXT NOT NULL, ref_host TEXT,
        device TEXT, visitor TEXT NOT NULL, link_id INTEGER, entry INTEGER NOT NULL DEFAULT 0)""")
    conn.execute("CREATE INDEX IF NOT EXISTS site_visits_day_idx ON site_visits (seen_day)")
    conn.execute("CREATE TABLE IF NOT EXISTS site_settings (skey TEXT PRIMARY KEY, svalue TEXT)")
    conn.commit()
    _ready = True


def _now():
    return datetime.now(CT)


def _opted_out():
    return request.headers.get("DNT") == "1" or request.headers.get("Sec-GPC") == "1"


def _secure():
    return request.is_secure or request.headers.get("X-Forwarded-Proto", "") == "https"


def _is_gated(path):
    p = path.rstrip("/") or "/"
    return p in GATED_EXACT or p.startswith(GATED_PREFIX)


def register(app, crm, owner_view, get_db, full_name_sql, log_message=None):

    def _state():
        """Private-preview settings and which invitations are on, refreshed every few seconds. Defaults to private."""
        if time.time() - _cache["at"] < 5:
            return _cache
        try:
            conn = get_db()
            try:
                _ensure(conn)
                rows = {r["skey"]: r["svalue"] for r in conn.execute("SELECT skey, svalue FROM site_settings").fetchall()}
                active = {r["id"] for r in conn.execute("SELECT id FROM site_visit_links WHERE active = 1").fetchall()}
            finally:
                conn.close()
            _cache.update(private=rows.get("private_mode", "1") != "0", message=rows.get("private_message") or "", active=active)
        except Exception as e:
            print(f"private preview settings not read: {e!r}", flush=True)
        _cache["at"] = time.time()
        return _cache

    def _sig(link_id):
        return hmac.new((app.secret_key or "x").encode() if isinstance(app.secret_key, str) else (app.secret_key or b"x"),
                        str(link_id).encode(), hashlib.sha256).hexdigest()[:24]

    def _has_invite(st):
        v = request.cookies.get(COOKIE_INVITE) or ""
        lid, _, sig = v.partition(".")
        if not (lid.isdigit() and hmac.compare_digest(sig, _sig(lid))):
            return False
        if int(lid) not in st["active"]:           # a link made moments ago: look again right away
            _cache["at"] = 0.0
            return int(lid) in _state()["active"]
        return True

    @app.before_request
    def _private_preview():
        if not _is_gated(request.path) or request.method == "OPTIONS" or session.get("staff_id"):
            return None
        st = _state()
        if not st["private"] or _has_invite(st):
            return None
        g.site_gated = True
        return make_response(render_template("site_private.html", message=st["message"]))

    @app.after_request
    def _no_index_while_private(resp):
        try:
            if _cache["private"] and resp.mimetype == "text/html":
                resp.headers["X-Robots-Tag"] = "noindex, nofollow"
        except Exception:
            pass
        return resp

    @app.after_request
    def _log_visit(resp):
        try:
            if request.method != "GET" or resp.status_code != 200 or resp.mimetype != "text/html":
                return resp
            ep = request.endpoint or ""
            if not ep.startswith("public_") or ep.endswith("_preview"):
                return resp
            if session.get("staff_id") or is_bot(request.headers.get("User-Agent")) or _opted_out():
                return resp
            if request.headers.get("Sec-Purpose", "").lower().startswith("prefetch") or request.headers.get("Purpose", "").lower() == "prefetch":
                return resp
            vid = request.cookies.get(COOKIE_VISITOR)
            new_vid = not (vid and re.fullmatch(r"[A-Za-z0-9_-]{6,40}", vid))
            if new_vid:
                vid = secrets.token_urlsafe(9)
            link_id = request.cookies.get(COOKIE_LINK)
            link_id = int(link_id) if link_id and link_id.isdigit() else None
            entry = 1 if request.cookies.get(COOKIE_FIRST) == "1" else 0
            ref = ""
            if request.referrer:
                host = (urlparse(request.referrer).netloc or "").lower().removeprefix("www.")
                own = (request.host or "").lower().removeprefix("www.")
                ref = "(internal)" if host == own else host[:80]
            now = _now()
            conn = get_db()
            try:
                _ensure(conn)
                conn.execute(
                    "INSERT INTO site_visits (seen_at, seen_day, path, ref_host, device, visitor, link_id, entry) VALUES (?,?,?,?,?,?,?,?)",
                    (now.strftime("%Y-%m-%d %H:%M:%S"), now.strftime("%Y-%m-%d"),
                     ("blocked:" if getattr(g, "site_gated", False) else "") + (request.path[:190].rstrip("/") or "/"), ref,
                     device_of(request.headers.get("User-Agent")), vid, link_id, entry))
                conn.commit()
            finally:
                conn.close()
            if new_vid:
                resp.set_cookie(COOKIE_VISITOR, vid, max_age=31536000, httponly=True, samesite="Lax", secure=_secure())
            if entry:
                resp.delete_cookie(COOKIE_FIRST)
        except Exception as e:
            print(f"site visit not logged: {e!r}", flush=True)
        return resp

    @app.route("/v/<token>")
    def track_link(token):
        """A personal link. Remembers which link brought the visitor, then sends them to the page the Owner chose."""
        target = "/"
        try:
            conn = get_db()
            try:
                _ensure(conn)
                row = conn.execute("SELECT * FROM site_visit_links WHERE token = ? AND active = 1", (token,)).fetchone()
            finally:
                conn.close()
        except Exception as e:
            print(f"personal link lookup failed: {e!r}", flush=True)
            row = None
        if row:
            t = row["target_path"] or "/"
            target = t if t.startswith("/") and not t.startswith("//") else "/"
        resp = redirect(target)
        if row and not is_bot(request.headers.get("User-Agent")):
            resp.set_cookie(COOKIE_INVITE, f"{row['id']}.{_sig(row['id'])}", max_age=90 * 86400, httponly=True, samesite="Lax", secure=_secure())
        if row and not is_bot(request.headers.get("User-Agent")) and not _opted_out():
            resp.set_cookie(COOKIE_LINK, str(row["id"]), max_age=30 * 86400, httponly=True, samesite="Lax", secure=_secure())
            resp.set_cookie(COOKIE_FIRST, "1", max_age=86400, httponly=True, samesite="Lax", secure=_secure())
        return resp

    @app.route("/invitation-request", methods=["POST"])
    def invite_request():
        """The form on the coming-soon page. Saves the person as an Interested Party contact in the Hub."""
        import call_flow
        f = request.form
        way = {"email": "Email", "text": "Text", "call": "Call"}.get(f.get("way") or "", "")
        msg = (f.get("message") or "").strip()[:500]
        note = "Asked for an invitation to the private preview." + (f" Prefers: {way}." if way else "") + (f" Message: {msg}" if msg else "")
        form = {"first_name": f.get("first_name"), "last_name": f.get("last_name"), "email": f.get("email"),
                "phone": f.get("phone"), "message": note, "page": "other", "website": f.get("website"), "bg": f.get("bg")}
        ok, _yes, err = call_flow.create_interest(get_db, form, "Private preview invitation request")
        if not ok:
            return render_template("site_private.html", message=_state()["message"], error=err, form=f), 200
        return redirect(url_for("invite_request_thanks"))

    @app.route("/invitation-request/thanks")
    def invite_request_thanks():
        return render_template("site_private.html", message=_state()["message"], thanks=True)

    def _state_fresh():
        _cache["at"] = 0.0
        return _state()

    def _base_url():
        return (os.environ.get("PUBLIC_BASE_URL") or request.url_root).rstrip("/")

    def _invite_state(conn, contact):
        """Everything the invite page needs to decide what is allowed. Never raises."""
        email = (contact["email"] or "").strip().lower()
        st = {"email": email, "staff": None, "blocked": False, "link": None}
        try:
            st["staff"] = conn.execute(
                "SELECT name, role, active FROM staff WHERE contact_id = ? OR (? <> '' AND LOWER(email) = ?) ORDER BY active DESC LIMIT 1",
                (contact["id"], email, email)).fetchone()
        except Exception:
            try: conn.rollback()
            except Exception: pass
        try:
            import do_not_contact
            st["blocked"] = bool(email) and bool(do_not_contact.email_blocked(conn, email))
        except Exception:
            try: conn.rollback()
            except Exception: pass
        st["link"] = conn.execute(
            "SELECT * FROM site_visit_links WHERE contact_id = ? AND active = 1 ORDER BY id DESC LIMIT 1", (contact["id"],)).fetchone()
        return st

    def _invite_page(contact_id, paste=None):
        conn = get_db()
        _ensure(conn)
        contact = conn.execute(f"SELECT *, {full_name_sql('contacts')} AS full_name FROM contacts WHERE id = ?", (contact_id,)).fetchone()
        if not contact:
            conn.close()
            abort(404)
        st = _invite_state(conn, contact)
        sent = conn.execute("SELECT subject, sent_at FROM contact_messages WHERE contact_id = ? AND kind = ? ORDER BY id DESC LIMIT 3",
                            (contact_id, "Website invitation")).fetchall() if _table_ok(conn, "contact_messages") else []
        conn.close()
        link_url = (_base_url() + "/v/" + st["link"]["token"]) if st["link"] else None
        try:
            import correspondence
            live = correspondence.live()
        except Exception:
            live = False
        return render_template("site_invite.html", contact=contact, st=st, link_url=link_url, sent=sent, live=live,
                               paste=paste, private_on=_state()["private"])

    def _table_ok(conn, name):
        try:
            conn.execute(f"SELECT 1 FROM {name} LIMIT 1")
            return True
        except Exception:
            try: conn.rollback()
            except Exception: pass
            return False

    @crm.route("/contacts/<int:contact_id>/site-invitation")
    @owner_view
    def site_invitation(contact_id):
        return _invite_page(contact_id)

    @crm.route("/contacts/<int:contact_id>/site-invitation/send", methods=["POST"])
    @owner_view
    def site_invitation_send(contact_id):
        from email_utils import send_email
        import email_templates as T
        conn = get_db()
        _ensure(conn)
        contact = conn.execute(f"SELECT *, {full_name_sql('contacts')} AS full_name FROM contacts WHERE id = ?", (contact_id,)).fetchone()
        if not contact:
            conn.close()
            abort(404)
        st = _invite_state(conn, contact)
        back = redirect(url_for(".site_invitation", contact_id=contact_id))
        if st["staff"]:
            conn.close()
            flash(f"{contact['full_name']} already has a Hub login, so no invitation is needed.")
            return back
        if not st["email"]:
            conn.close()
            flash("This contact has no email address on file.")
            return back
        if st["blocked"]:
            conn.close()
            flash("This person is marked do-not-email, so nothing was sent.")
            return back
        link = st["link"]
        if not link:
            token = secrets.token_urlsafe(6).replace("_", "x").replace("-", "y")
            conn.execute("INSERT INTO site_visit_links (token, label, contact_id, target_path, created_at) VALUES (?,?,?,?,?)",
                         (token, contact["full_name"], contact_id, "/", _now().strftime("%Y-%m-%d %H:%M:%S")))
            conn.commit()
        else:
            token = link["token"]
        conn.close()
        url = _base_url() + "/v/" + token
        subject, html, text = T.guide_letter_content("site_invitation", contact["first_name"] or "there", "", "", "", link=url)
        try:
            import correspondence
            live = correspondence.live()
        except Exception:
            live = False
        if not live:
            flash("Letter sending is switched off, so nothing was emailed. Copy the message below and send it yourself.")
            return _invite_page(contact_id, paste=dict(subject=subject, text=text, link=url))
        try:
            send_email(to_email=contact["email"], to_name=contact["first_name"], subject=subject, html_content=html, text_content=text)
            if log_message:
                log_message(contact_id, "Website invitation", subject, html, contact["email"])
            flash(f"Invitation emailed to {contact['first_name']} ({contact['email']}).")
        except Exception as e:
            flash(f"Couldn't send the email: {e}")
            return _invite_page(contact_id, paste=dict(subject=subject, text=text, link=url))
        return back

    @crm.route("/owner/site-visits")
    @owner_view
    def site_visits():
        days = request.args.get("days", "30")
        days = int(days) if days in ("7", "30", "90") else 30
        today = _now().date()
        start = (today - timedelta(days=days - 1)).isoformat()
        conn = get_db()
        _ensure(conn)
        tot = conn.execute(
            "SELECT COUNT(*) AS v, COUNT(DISTINCT visitor) AS u FROM site_visits WHERE seen_day >= ?", (start,)).fetchone()
        via = conn.execute(
            "SELECT COUNT(DISTINCT visitor) AS u FROM site_visits WHERE seen_day >= ? AND link_id IS NOT NULL", (start,)).fetchone()
        per_day = {r["day"]: (r["v"], r["u"]) for r in conn.execute(
            "SELECT seen_day AS day, COUNT(*) AS v, COUNT(DISTINCT visitor) AS u FROM site_visits WHERE seen_day >= ? GROUP BY seen_day", (start,)).fetchall()}
        daily, top_n = [], 1
        for i in range(days):
            d = (today - timedelta(days=days - 1 - i)).isoformat()
            v, u = per_day.get(d, (0, 0))
            daily.append(dict(day=d, views=v, visitors=u))
            top_n = max(top_n, v)
        def _pname(p):
            if p.startswith("blocked:"):
                return "Turned away (no invitation): " + _pname(p[8:])
            return PAGE_NAMES.get(p) or p.strip("/").replace("/", " / ").replace("-", " ").title() or "Home"
        pages = [dict(path=r["path"], name=_pname(r["path"]), views=r["v"], visitors=r["u"]) for r in conn.execute(
            "SELECT path, COUNT(*) AS v, COUNT(DISTINCT visitor) AS u FROM site_visits WHERE seen_day >= ? GROUP BY path ORDER BY v DESC LIMIT 15", (start,)).fetchall()]
        sources = [dict(name=r["ref_host"] or "Direct, email or text", visitors=r["u"]) for r in conn.execute(
            "SELECT COALESCE(ref_host, '') AS ref_host, COUNT(DISTINCT visitor) AS u FROM site_visits WHERE seen_day >= ? AND COALESCE(ref_host, '') <> '(internal)' "
            "GROUP BY COALESCE(ref_host, '') ORDER BY u DESC LIMIT 10", (start,)).fetchall()]
        devices = [dict(name=r["device"] or "Unknown", visitors=r["u"]) for r in conn.execute(
            "SELECT device, COUNT(DISTINCT visitor) AS u FROM site_visits WHERE seen_day >= ? GROUP BY device ORDER BY u DESC", (start,)).fetchall()]
        stats = {r["link_id"]: r for r in conn.execute(
            "SELECT link_id, SUM(entry) AS opens, COUNT(DISTINCT visitor) AS u, COUNT(*) AS v, MAX(seen_at) AS last_at "
            "FROM site_visits WHERE link_id IS NOT NULL GROUP BY link_id").fetchall()}
        links = []
        for l in conn.execute(f"SELECT l.*, {full_name_sql('c')} AS contact_name FROM site_visit_links l "
                              "LEFT JOIN contacts c ON c.id = l.contact_id ORDER BY l.id DESC").fetchall():
            s = stats.get(l["id"])
            pg = [dict(name=_pname(r["path"]), n=r["n"]) for r in conn.execute(
                "SELECT path, COUNT(*) AS n FROM site_visits WHERE link_id = ? GROUP BY path ORDER BY n DESC LIMIT 6", (l["id"],)).fetchall()]
            links.append(dict(row=l, opens=int(s["opens"] or 0) if s else 0, visitors=s["u"] if s else 0, views=s["v"] if s else 0,
                              last_at=s["last_at"] if s else None, pages=pg, url=f"{_base_url()}/v/{l['token']}",
                              target_name=PAGE_NAMES.get(l["target_path"]) or l["target_path"]))
        requests_ = [dict(r) for r in conn.execute(
            "SELECT id, first_name, last_name, email, cell_phone, notes FROM contacts WHERE notes LIKE ? ORDER BY id DESC LIMIT 12",
            ("%Private preview invitation request%",)).fetchall()]
        conn.close()
        return render_template("site_visits.html", invite_requests=requests_, private_on=_state_fresh()["private"], private_message=_cache["message"], days=days, views=tot["v"], visitors=tot["u"], link_visitors=via["u"], daily=daily,
                               top_n=top_n, pages=pages, sources=sources, devices=devices, links=links, targets=LINK_TARGETS)

    @crm.route("/owner/site-visits/link", methods=["POST"])
    @owner_view
    def site_visit_link_add():
        label = (request.form.get("label") or "").strip()[:80]
        target = request.form.get("target") or "/"
        if target not in PAGE_NAMES:
            target = "/"
        email = (request.form.get("contact_email") or "").strip().lower()
        if not label:
            flash("Give the link a name so you remember who it is for.")
            return redirect(url_for(".site_visits"))
        conn = get_db()
        _ensure(conn)
        cid = None
        if email:
            c = conn.execute("SELECT id FROM contacts WHERE LOWER(email) = ? ORDER BY id LIMIT 1", (email,)).fetchone()
            if c:
                cid = c["id"]
            else:
                flash("No contact has that email address, so the link was made without a contact attached.")
        conn.execute("INSERT INTO site_visit_links (token, label, contact_id, target_path, created_at) VALUES (?,?,?,?,?)",
                     (secrets.token_urlsafe(6).replace("_", "x").replace("-", "y"), label, cid, target, _now().strftime("%Y-%m-%d %H:%M:%S")))
        conn.commit()
        conn.close()
        flash(f"Link made for {label}. Copy it from the list below.")
        return redirect(url_for(".site_visits") + "#links")

    @crm.route("/owner/site-visits/link/<int:link_id>/toggle", methods=["POST"])
    @owner_view
    def site_visit_link_toggle(link_id):
        conn = get_db()
        _ensure(conn)
        conn.execute("UPDATE site_visit_links SET active = 1 - active WHERE id = ?", (link_id,))
        conn.commit()
        conn.close()
        _cache["at"] = 0.0
        return redirect(url_for(".site_visits") + "#links")

    @crm.route("/owner/site-visits/private", methods=["POST"])
    @owner_view
    def site_private_set():
        on = request.form.get("mode") == "on"
        conn = get_db()
        _ensure(conn)
        conn.execute("DELETE FROM site_settings WHERE skey = 'private_mode'")
        conn.execute("INSERT INTO site_settings (skey, svalue) VALUES ('private_mode', ?)", ("1" if on else "0",))
        conn.commit()
        conn.close()
        _cache["at"] = 0.0
        flash("Private preview is ON. Only people with your invitation links, and logged-in team members, can see the public pages."
              if on else "Private preview is OFF. The public website is open to everyone.")
        return redirect(url_for(".site_visits"))

    @crm.route("/owner/site-visits/message", methods=["POST"])
    @owner_view
    def site_private_message():
        msg = (request.form.get("message") or "").strip()[:600]
        conn = get_db()
        _ensure(conn)
        conn.execute("DELETE FROM site_settings WHERE skey = 'private_message'")
        conn.execute("INSERT INTO site_settings (skey, svalue) VALUES ('private_message', ?)", (msg,))
        conn.commit()
        conn.close()
        _cache["at"] = 0.0
        flash("Message saved.")
        return redirect(url_for(".site_visits"))
