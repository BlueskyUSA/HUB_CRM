"""Discovery Legacy fundraising site: a small public site that collects pledges (no card payments).

* Public pages live under /legacy/... . On the Discovery Legacy web address (discoverylegacy.org / .com, or any host named in
  the LEGACY_HOSTS setting on Render) the same pages answer at the plain addresses (/, /why, /pledge ...).
* The site stays hidden (a "coming soon" page) until the Owner switches it on from the Pledges page. Anyone signed in to the
  Hub can preview it at any time.
* A pledge is a statement of intent, not a payment. Each pledge is saved on the Pledges page (Owner only) and as a contact.
* Nothing here says gifts are tax-deductible. The exemption notice on every page is for the attorney to confirm.
"""
import os
import re
import secrets
import time
from datetime import datetime
from zoneinfo import ZoneInfo

from flask import abort, flash, make_response, redirect, render_template, request, session, url_for

CT = ZoneInfo("America/Chicago")
DEFAULT_HOSTS = {"discoverylegacy.org", "www.discoverylegacy.org", "discoverylegacy.com", "www.discoverylegacy.com"}
CONTACT_EMAIL = "kent@discoverylegacy.org"
EIN = "43-3125170"
FORMED = "11/20/2026"
STATUSES = ("Pledged", "Given", "Withdrawn")

_ready = False
_cache = {"at": 0.0, "live": False}


def _hosts():
    extra = {h.strip().lower() for h in (os.environ.get("LEGACY_HOSTS") or "").split(",") if h.strip()}
    return DEFAULT_HOSTS | extra


def _now():
    return datetime.now(CT)


def money(cents):
    cents = int(cents or 0)
    return f"${cents // 100:,}" if cents % 100 == 0 else f"${cents / 100:,.2f}"


def plan_text(kind, cents, months):
    if kind == "monthly":
        if months:
            return f"{money(cents)} a month for {months} month{'s' if months != 1 else ''}"
        return f"{money(cents)} a month, until I change it"
    return f"{money(cents)}, one time"


def _ensure(conn):
    global _ready
    if _ready:
        return
    conn.execute("""CREATE TABLE IF NOT EXISTS pledges (
        id SERIAL PRIMARY KEY, contact_id INTEGER, first_name TEXT NOT NULL, last_name TEXT, email TEXT NOT NULL, phone TEXT,
        kind TEXT NOT NULL, amount_cents INTEGER NOT NULL, months INTEGER, note TEXT, updates_ok INTEGER NOT NULL DEFAULT 0,
        status TEXT NOT NULL DEFAULT 'Pledged', created_at TEXT NOT NULL)""")
    conn.execute("""CREATE TABLE IF NOT EXISTS pledge_invites (
        id SERIAL PRIMARY KEY, token TEXT NOT NULL, contact_id INTEGER, first_name TEXT NOT NULL, email TEXT, note TEXT,
        how TEXT NOT NULL, created_at TEXT NOT NULL, opened_at TEXT, pledge_id INTEGER)""")
    conn.execute("CREATE TABLE IF NOT EXISTS site_settings (skey TEXT PRIMARY KEY, svalue TEXT)")
    conn.commit()
    _ready = True


def register(app, crm, owner_view, get_db, log_message=None):
    # ---- the Discovery Legacy web address: answer at the plain paths -------------------------------------------------
    inner = app.wsgi_app

    def _host_rewrite(environ, start_response):
        host = (environ.get("HTTP_HOST") or "").split(":")[0].lower()
        if host in _hosts():
            path = environ.get("PATH_INFO") or "/"
            if not path.startswith(("/legacy", "/static", "/crm", "/healthz", "/favicon", "/robots")):
                environ["PATH_INFO"] = "/legacy" + ("" if path == "/" else path)
        return inner(environ, start_response)

    app.wsgi_app = _host_rewrite

    def _live():
        if time.time() - _cache["at"] < 5:
            return _cache["live"]
        try:
            conn = get_db()
            try:
                _ensure(conn)
                row = conn.execute("SELECT svalue FROM site_settings WHERE skey = 'legacy_live'").fetchone()
            finally:
                conn.close()
            _cache["live"] = bool(row) and row["svalue"] == "1"
        except Exception as e:
            print(f"Fundraising switch not read: {e!r}", flush=True)
            _cache["live"] = False
        _cache["at"] = time.time()
        return _cache["live"]

    def _page(name, **ctx):
        staff = bool(session.get("staff_id"))
        guest = bool(session.get("legacy_guest"))
        live = _live()
        if not live and not staff and not guest:
            resp = make_response(render_template("legacy_site.html", page="soon", contact_email=CONTACT_EMAIL, **ctx))
            resp.headers["X-Robots-Tag"] = "noindex, nofollow"
            return resp
        resp = make_response(render_template("legacy_site.html", page=name, preview=(staff and not live), guest_invite=(guest and not live and not staff),
                                             contact_email=CONTACT_EMAIL, ein=EIN, formed=FORMED, **ctx))
        if not live or guest:
            resp.headers["X-Robots-Tag"] = "noindex, nofollow"
        return resp

    @app.route("/legacy")
    @app.route("/legacy/")
    def legacy_home():
        return _page("home")

    @app.route("/legacy/why")
    def legacy_why():
        return _page("why")

    @app.route("/legacy/where-your-gift-goes")
    def legacy_where():
        return _page("where")

    @app.route("/legacy/about")
    def legacy_about():
        return _page("about")

    @app.route("/legacy/pledge/thanks")
    def legacy_thanks():
        return _page("thanks", plan=request.args.get("p", "")[:120])

    @app.route("/legacy/pledge", methods=["GET", "POST"])
    def legacy_pledge():
        if request.method == "GET":
            return _page("pledge", form=session.get("legacy_prefill") or {}, error=None, inv=session.get("legacy_inv", ""))
        f = request.form
        first = (f.get("first_name") or "").strip()[:80]
        last = (f.get("last_name") or "").strip()[:80] or None
        email = (f.get("email") or "").strip()[:200]
        phone = (f.get("phone") or "").strip()[:40]
        note = (f.get("note") or "").strip()[:1000]
        kind = "monthly" if f.get("kind") == "monthly" else "once"
        updates_ok = 1 if f.get("updates_ok") else 0

        def fail(msg):
            return _page("pledge", form=f, error=msg, inv=f.get("inv", ""))

        import botguard
        ok_bot, bot_msg = botguard.check(get_db, "pledge", f, email=email, ip_limit=6, email_limit=3)
        if not ok_bot:
            if bot_msg is None:       # the hidden spam-trap field was filled: pretend it worked
                return redirect(url_for("legacy_thanks"))
            return fail(bot_msg)
        if not first or not email or "@" not in email:
            return fail("Please enter your first name and a valid email address.")
        raw = re.sub(r"[^0-9.]", "", f.get("amount") or "")
        try:
            cents = int(round(float(raw) * 100)) if raw else 0
        except ValueError:
            cents = 0
        if cents < 100 or cents > 100_000_000:
            return fail("Please enter the amount you would like to pledge, in dollars.")
        months = 0
        if kind == "monthly":
            m = (f.get("months") or "").strip()
            months = int(m) if m.isdigit() and 1 <= int(m) <= 120 else 0
        if not f.get("understand"):
            return fail("Please check the box to confirm you understand this is a pledge of intent, not a payment.")

        plan = plan_text(kind, cents, months)
        conn = get_db()
        try:
            _ensure(conn)
            line = f"Pledged to Discovery Legacy: {plan}. (Submitted via the Discovery Legacy website on {_now():%m/%d/%Y}.)"
            if note:
                line += f" Note: {note}"
            existing = conn.execute("SELECT id, notes FROM contacts WHERE lower(email) = lower(?) ORDER BY id LIMIT 1", (email,)).fetchone()
            if existing:
                cid = existing["id"]
                conn.execute("UPDATE contacts SET notes = ?, cell_phone = COALESCE(NULLIF(cell_phone, ''), ?) WHERE id = ?",
                             (((existing["notes"] or "") + "\n" if existing["notes"] else "") + line, phone or None, cid))
            else:
                cur = conn.execute(
                    """INSERT INTO contacts (first_name, last_name, email, cell_phone, notes, marketing_source, status)
                       VALUES (?, ?, ?, ?, ?, ?, ?)""", (first, last, email, phone or None, line, "Pledge", "Interested Party"))
                cid = cur.lastrowid
            conn.execute(
                """INSERT INTO pledges (contact_id, first_name, last_name, email, phone, kind, amount_cents, months, note,
                                        updates_ok, status, created_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
                (cid, first, last, email, phone or None, kind, cents, months or None, note or None, updates_ok, "Pledged",
                 _now().strftime("%Y-%m-%d %H:%M:%S")))
            inv_token = (f.get("inv") or "").strip()
            if inv_token:
                pid = conn.execute("SELECT id FROM pledges WHERE contact_id = ? ORDER BY id DESC LIMIT 1", (cid,)).fetchone()
                conn.execute("UPDATE pledge_invites SET pledge_id = ? WHERE token = ?", (pid["id"] if pid else None, inv_token))
            conn.commit()
            blocked = False
            try:
                import do_not_contact
                blocked = bool(do_not_contact.email_blocked(conn, email.lower()))
            except Exception:
                try:
                    conn.rollback()
                except Exception:
                    pass
        except Exception as e:
            conn.rollback()
            print(f"Pledge failed: {e!r}", flush=True)
            conn.close()
            return fail("Sorry, something went wrong on our end. Please try again in a moment.")
        conn.close()
        # The thank-you letter (its wording is on the Correspondence page). Sent only when letters are switched on.
        try:
            import correspondence
            import email_templates as T
            from email_utils import send_email
            if correspondence.live() and not blocked:
                subject, html, text = T.guide_letter_content("pledge_thanks", first, "", "", "", amount_text=plan)
                send_email(to_email=email, to_name=first, subject=subject, html_content=html, text_content=text)
                if log_message:
                    log_message(cid, "Pledge thank-you", subject, html, email)
        except Exception as e:
            print(f"Pledge thank-you not sent: {e!r}", flush=True)
        session.pop("legacy_inv", None); session.pop("legacy_prefill", None)
        return redirect(url_for("legacy_thanks", p=plan))

    @app.route("/legacy/f/<token>")
    def legacy_friend(token):
        conn = get_db()
        try:
            _ensure(conn)
            row = conn.execute("SELECT * FROM pledge_invites WHERE token = ?", (token[:40],)).fetchone()
            if not row:
                conn.close()
                return redirect(url_for("legacy_home"))
            if not row["opened_at"] and not session.get("staff_id"):
                conn.execute("UPDATE pledge_invites SET opened_at = ? WHERE id = ?", (_now().strftime("%Y-%m-%d %H:%M:%S"), row["id"]))
                conn.commit()
            c = conn.execute("SELECT first_name, last_name, email FROM contacts WHERE id = ?", (row["contact_id"],)).fetchone() if row["contact_id"] else None
        finally:
            try:
                conn.close()
            except Exception:
                pass
        session["legacy_guest"] = True
        session["legacy_inv"] = token
        session["legacy_prefill"] = {"first_name": (c["first_name"] if c else row["first_name"]) or "", "last_name": (c["last_name"] if c else "") or "",
                                     "email": (c["email"] if c else row["email"]) or ""}
        return redirect(url_for("legacy_pledge"))

    @crm.route("/owner/pledges/invite", methods=["POST"])
    @owner_view
    def pledge_invite():
        first = (request.form.get("first_name") or "").strip()[:80]
        last = (request.form.get("last_name") or "").strip()[:80] or None
        email = (request.form.get("email") or "").strip()[:200]
        note = (request.form.get("note") or "").strip()[:1500]
        how = "email" if request.form.get("how") == "email" else "link"
        if not first or (how == "email" and "@" not in email):
            flash("Please enter a first name, and an email address if you want the Hub to send it.")
            return redirect(url_for(".pledges_page"))
        conn = get_db()
        _ensure(conn)
        cid = None
        if email:
            ex = conn.execute("SELECT id FROM contacts WHERE lower(email) = lower(?) ORDER BY id LIMIT 1", (email,)).fetchone()
            if ex:
                cid = ex["id"]
        if cid is None:
            cur = conn.execute("INSERT INTO contacts (first_name, last_name, email, notes, marketing_source, status) VALUES (?, ?, ?, ?, ?, ?)",
                               (first, last, email or None, f"Invited to pledge to Discovery Legacy on {_now():%m/%d/%Y}.", "Pledge invitation", "Interested Party"))
            cid = cur.lastrowid
        token = secrets.token_urlsafe(8).replace("_", "x").replace("-", "y")
        conn.execute("INSERT INTO pledge_invites (token, contact_id, first_name, email, note, how, created_at) VALUES (?,?,?,?,?,?,?)",
                     (token, cid, first, email or None, note or None, how, _now().strftime("%Y-%m-%d %H:%M:%S")))
        conn.commit()
        url = request.host_url.rstrip("/") + url_for("legacy_friend", token=token)
        blocked = False
        if email:
            try:
                import do_not_contact
                blocked = bool(do_not_contact.email_blocked(conn, email.lower()))
            except Exception:
                try:
                    conn.rollback()
                except Exception:
                    pass
        conn.close()
        if how == "email":
            try:
                import correspondence
                import email_templates as T
                from email_utils import send_email
                if blocked:
                    flash("That email address is on the do-not-contact list, so nothing was sent. The personal link is below if you want to give it another way.")
                elif not correspondence.live():
                    flash("Letters are switched off on the Correspondence page, so nothing was sent. The personal link is below; you can send it yourself.")
                else:
                    default = "I wanted you to be one of the first to hear about something that matters a great deal to me."
                    subject, html, text = T.guide_letter_content("pledge_invite", first, "", "", "", link=url, note_text=note or default)
                    send_email(to_email=email, to_name=first, subject=subject, html_content=html, text_content=text)
                    if log_message:
                        log_message(cid, "Pledge invitation", subject, html, email)
                    flash(f"Invitation sent to {first} at {email}.")
            except Exception as e:
                print(f"Pledge invitation not sent: {e!r}", flush=True)
                flash("The invitation could not be sent right now. The personal link is below.")
        else:
            flash(f"Personal link made for {first}.")
        session["last_invite_link"] = url
        session["last_invite_name"] = first
        return redirect(url_for(".pledges_page"))

    # ---- the Owner's Pledges page --------------------------------------------------------------------------------------
    @crm.route("/owner/pledges")
    @owner_view
    def pledges_page():
        conn = get_db()
        _ensure(conn)
        rows = conn.execute("SELECT * FROM pledges ORDER BY id DESC").fetchall()
        invites = conn.execute("SELECT * FROM pledge_invites ORDER BY id DESC").fetchall()
        conn.close()
        live = [r for r in rows if r["status"] != "Withdrawn"]
        once = sum(r["amount_cents"] for r in live if r["kind"] == "once")
        monthly = sum(r["amount_cents"] for r in live if r["kind"] == "monthly")
        year = once + sum(r["amount_cents"] * (r["months"] if r["months"] and r["months"] < 12 else 12) for r in live if r["kind"] == "monthly")
        _cache["at"] = 0.0
        return render_template("fundraising_pledges.html", rows=rows, plan_text=plan_text, money=money, statuses=STATUSES,
                               live=_live(), invites=invites, new_link=session.pop("last_invite_link", None), new_name=session.pop("last_invite_name", ""), count=len(live), once=once, monthly=monthly, year=year, hosts=sorted(_hosts()))

    @crm.route("/owner/pledges/live", methods=["POST"])
    @owner_view
    def pledges_live():
        on = "1" if request.form.get("live") == "1" else "0"
        conn = get_db()
        _ensure(conn)
        conn.execute("DELETE FROM site_settings WHERE skey = 'legacy_live'")
        conn.execute("INSERT INTO site_settings (skey, svalue) VALUES ('legacy_live', ?)", (on,))
        conn.commit()
        conn.close()
        _cache["at"] = 0.0
        flash("The Discovery Legacy fundraising site is now public." if on == "1" else "The Discovery Legacy fundraising site is hidden again (only people signed in to the Hub can see it).")
        return redirect(url_for(".pledges_page"))

    @crm.route("/owner/pledges/<int:pledge_id>/status", methods=["POST"])
    @owner_view
    def pledge_status(pledge_id):
        status = request.form.get("status")
        if status not in STATUSES:
            abort(400)
        conn = get_db()
        _ensure(conn)
        conn.execute("UPDATE pledges SET status = ? WHERE id = ?", (status, pledge_id))
        conn.commit()
        conn.close()
        return redirect(url_for(".pledges_page"))
