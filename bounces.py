"""Email bounces: Brevo tells the Hub when an email could not be delivered.
The Hub records it, shows it on a list, raises a Dashboard alert for important letters,
and stops future blasts to a dead address."""
import hmac, hashlib, os
from flask import request, render_template, redirect, url_for, flash, jsonify, abort

HARD = ("hard_bounce", "blocked", "invalid_email", "spam", "unsubscribed")
ALL_EVENTS = HARD + ("soft_bounce", "error")
NICE = {"hard_bounce": "Address does not exist", "blocked": "Blocked by their mail provider",
        "invalid_email": "Not a valid address", "spam": "Marked as spam", "soft_bounce": "Temporary problem (mailbox full or busy)",
        "error": "Could not be delivered", "unsubscribed": "Unsubscribed"}


def ensure(conn):
    conn.execute("""CREATE TABLE IF NOT EXISTS email_bounces (
        id SERIAL PRIMARY KEY, email TEXT NOT NULL, contact_id INTEGER, event TEXT, reason TEXT,
        message_id TEXT, subject TEXT, is_blast INTEGER NOT NULL DEFAULT 0, resolved INTEGER NOT NULL DEFAULT 0,
        happened_at TEXT, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)""")
    conn.commit()


def secret(app):
    s = os.environ.get("BREVO_WEBHOOK_SECRET")
    return s or hmac.new((app.secret_key or "x").encode(), b"brevo-bounces", hashlib.sha256).hexdigest()[:32]


def hard_bounced_addresses(conn):
    """Lower-case addresses that should not be emailed again (unfixed hard bounces). Safe if the table is missing."""
    try:
        ensure(conn)
        return {r["e"] for r in conn.execute(
            "SELECT DISTINCT LOWER(email) AS e FROM email_bounces WHERE (resolved = 0 AND event IN ('hard_bounce','blocked','invalid_email')) "
            "OR event IN ('spam','unsubscribed')").fetchall()}
    except Exception:
        try: conn.rollback()
        except Exception: pass
        return set()


def open_rows(conn, important_only=False):
    """Unresolved bounces whose address is still the contact's current address (fixing the address clears it)."""
    ensure(conn)
    q = """SELECT b.*, c.first_name, c.last_name FROM email_bounces b
           LEFT JOIN contacts c ON c.id = b.contact_id
           WHERE b.resolved = 0 AND (b.contact_id IS NULL OR LOWER(COALESCE(c.email,'')) = LOWER(b.email)
                 OR LOWER(COALESCE(c.email_2,'')) = LOWER(b.email) OR LOWER(COALESCE(c.email_3,'')) = LOWER(b.email))"""
    if important_only:
        q += " AND b.is_blast = 0 AND b.event <> 'soft_bounce'"
    return conn.execute(q + " ORDER BY b.id DESC LIMIT 500").fetchall()


def register(app, crm, alerts_required, get_db):
    @app.route("/webhooks/brevo/<key>", methods=["POST"])
    def brevo_webhook(key):
        if not hmac.compare_digest(key, secret(app)):
            abort(404)
        data = request.get_json(silent=True) or {}
        items = data if isinstance(data, list) else [data]
        conn = get_db()
        try:
            ensure(conn)
            for d in items:
                ev = (d.get("event") or "").lower()
                email = (d.get("email") or "").strip()
                if ev not in ALL_EVENTS or not email:
                    continue
                mid = d.get("message-id") or d.get("messageId") or ""
                c = None
                if mid:
                    c = conn.execute("SELECT id, contact_id FROM contact_messages WHERE brevo_id = ? ORDER BY id DESC LIMIT 1", (mid,)).fetchone()
                cid = c["contact_id"] if c else None
                if cid is None:
                    r = conn.execute("SELECT id FROM contacts WHERE LOWER(email) = LOWER(?) OR LOWER(email_2) = LOWER(?) OR LOWER(email_3) = LOWER(?) ORDER BY id LIMIT 1",
                                     (email, email, email)).fetchone()
                    cid = r["id"] if r else None
                blast = conn.execute("""SELECT 1 FROM blast_recipients WHERE LOWER(email) = LOWER(?) AND status = 'sent'
                                        AND sent_at >= to_char(now() - interval '5 days', 'YYYY-MM-DD') LIMIT 1""", (email,)).fetchone()
                reason = (d.get("reason") or "")[:300]
                conn.execute("""INSERT INTO email_bounces (email, contact_id, event, reason, message_id, subject, is_blast, happened_at)
                                VALUES (?,?,?,?,?,?,?,?)""",
                             (email, cid, ev, reason, mid, (d.get("subject") or "")[:200], 1 if blast else 0, str(d.get("date") or "")[:30]))
                if c:
                    conn.execute("UPDATE contact_messages SET status = ? WHERE id = ?", ("Bounced: " + NICE.get(ev, ev), c["id"]))
            conn.commit()
        except Exception as e:
            try: conn.rollback()
            except Exception: pass
            print(f"bounce webhook error: {e}", flush=True)
        finally:
            conn.close()
        return jsonify(ok=True)

    @crm.route("/email-bounces")
    @alerts_required
    def email_bounces():
        from flask import session
        conn = get_db()
        try:
            rows = open_rows(conn)
        finally:
            conn.close()
        hook = url_for("brevo_webhook", key=secret(app), _external=True) if session.get("is_owner") else None
        return render_template("email_bounces.html", rows=rows, nice=NICE, hook=hook)

    @crm.route("/email-bounces/<int:bounce_id>/resolve", methods=["POST"])
    @alerts_required
    def email_bounce_resolve(bounce_id):
        conn = get_db()
        try:
            ensure(conn)
            r = conn.execute("SELECT email FROM email_bounces WHERE id = ?", (bounce_id,)).fetchone()
            if r:
                conn.execute("UPDATE email_bounces SET resolved = 1 WHERE LOWER(email) = LOWER(?)", (r["email"],))
                conn.commit()
        finally:
            conn.close()
        flash("Cleared.")
        return redirect(url_for(".email_bounces"))
