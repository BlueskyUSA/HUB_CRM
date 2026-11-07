"""Unsubscribe and "do not contact" handling.
- Any person with Contacts access can mark someone Do not email / Do not call / Do not text (with a note). Only the Owner or an
  Administrator can clear a flag, because the person asked not to be contacted.
- Emails typed or sent one-to-one from a contact's page are refused for anyone who is blocked.
- An address can also be blocked with no contact record (someone writes "remove me" from an address that is not in the Hub).
- The Owner/Administrator page lists everyone who is blocked, when, how, and by whom, and exports the list."""
import csv
import io
from datetime import datetime
from flask import render_template, request, redirect, url_for, session, flash, Response

_ready = {"ok": False}
INDIVIDUAL_SENDS = ("crm.contact_send_excitement_email", "crm.contact_send_profile_request", "crm.contact_send_video_link",
                    "crm.contact_send_business_plan", "crm.contact_send_contract_request")


def ensure(conn):
    for col, typ in (("do_not_email", "INTEGER NOT NULL DEFAULT 0"), ("do_not_call", "INTEGER NOT NULL DEFAULT 0"),
                     ("do_not_text", "INTEGER NOT NULL DEFAULT 0"), ("dnc_note", "TEXT"), ("dnc_at", "TEXT"), ("dnc_by", "TEXT")):
        conn.execute(f"ALTER TABLE contacts ADD COLUMN IF NOT EXISTS {col} {typ}")
    conn.execute("""CREATE TABLE IF NOT EXISTS email_suppressions (id SERIAL PRIMARY KEY, email TEXT NOT NULL UNIQUE,
        reason TEXT, added_at TEXT, added_by TEXT)""")
    conn.commit()


def suppressed_addresses(conn):
    """Lower-case addresses blocked with no contact record. Safe if the table does not exist yet."""
    try:
        return {r["e"] for r in conn.execute("SELECT LOWER(email) AS e FROM email_suppressions").fetchall()}
    except Exception:
        try: conn.rollback()
        except Exception: pass
        return set()


def email_blocked(conn, email):
    """True if this address must not be emailed one-to-one: unsubscribed/do-not-email on any contact, Guide opt-out,
    spam complaint, or a typed-in block."""
    e = (email or "").strip().lower()
    if not e:
        return False
    try:
        if conn.execute("SELECT 1 FROM contacts WHERE LOWER(email) = ? AND COALESCE(do_not_email, 0) = 1 LIMIT 1", (e,)).fetchone():
            return True
        if conn.execute("SELECT 1 FROM email_suppressions WHERE LOWER(email) = ? LIMIT 1", (e,)).fetchone():
            return True
        if conn.execute("SELECT 1 FROM email_bounces WHERE LOWER(email) = ? AND event IN ('spam','unsubscribed') LIMIT 1", (e,)).fetchone():
            return True
    except Exception:
        try: conn.rollback()
        except Exception: pass
    return False


def note_unsubscribed(conn, where_sql, args, how="Clicked the unsubscribe link in an email"):
    """Called by the public unsubscribe page: records when and how, without overwriting an earlier note."""
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    conn.execute(f"UPDATE contacts SET dnc_at = COALESCE(dnc_at, ?), dnc_note = COALESCE(dnc_note, ?), "
                 f"dnc_by = COALESCE(dnc_by, 'The person themselves') WHERE {where_sql}", [now, how] + list(args))


def register(app, crm, area_contacts, owner_required, get_db):
    @app.before_request
    def _dnc_columns():
        if _ready["ok"] or request.path.startswith("/static/"):
            return
        try:
            c = get_db()
            try:
                ensure(c)
            finally:
                c.close()
            _ready["ok"] = True
        except Exception as e:
            print(f"Do-not-contact setup failed: {e}", flush=True)

    @crm.before_request
    def _refuse_blocked_one_to_one():
        if request.method != "POST" or request.endpoint not in INDIVIDUAL_SENDS:
            return
        cid = (request.view_args or {}).get("contact_id")
        try:
            conn = get_db()
            try:
                row = conn.execute("SELECT email FROM contacts WHERE id = ?", (cid,)).fetchone()
                blocked = bool(row and email_blocked(conn, row["email"]))
            finally:
                conn.close()
        except Exception:
            return
        if blocked:
            flash("Not sent. This person is on the Do not contact list (they unsubscribed or asked not to be emailed).")
            return redirect(url_for(".contact_detail", contact_id=cid))

    @crm.route("/contacts/<int:contact_id>/do-not-contact", methods=["POST"])
    @area_contacts
    def contact_do_not_contact(contact_id):
        back = url_for(".contact_detail", contact_id=contact_id) + "#dnc"
        want = {"do_not_email": 1 if request.form.get("do_not_email") else 0,
                "do_not_call": 1 if request.form.get("do_not_call") else 0,
                "do_not_text": 1 if request.form.get("do_not_text") else 0}
        note = (request.form.get("dnc_note") or "").strip()[:300]
        conn = get_db()
        try:
            ensure(conn)
            cur = conn.execute("SELECT do_not_email, do_not_call, do_not_text, dnc_note, dnc_at FROM contacts WHERE id = ?", (contact_id,)).fetchone()
            if not cur:
                flash("Contact not found.")
                return redirect(url_for(".contacts_list"))
            clearing = [k for k in want if cur[k] and not want[k]]
            if clearing and not session.get("is_owner"):
                flash("Only the Owner or an Administrator can turn a Do not contact flag back off, because the person asked not to be contacted. Nothing was changed.")
                return redirect(back)
            any_flag = any(want.values())
            now = datetime.now().strftime("%Y-%m-%d %H:%M")
            conn.execute("""UPDATE contacts SET do_not_email = ?, do_not_call = ?, do_not_text = ?, dnc_note = ?, dnc_at = ?, dnc_by = ?
                            WHERE id = ?""",
                         (want["do_not_email"], want["do_not_call"], want["do_not_text"],
                          (note or cur["dnc_note"]) if any_flag else None,
                          (cur["dnc_at"] or now) if any_flag else None,
                          session.get("staff_name") if any_flag else None, contact_id))
            # an address that is blocked on one record is blocked on any other record with the same address
            if want["do_not_email"] and not cur["do_not_email"]:
                conn.execute("""UPDATE contacts SET do_not_email = 1 WHERE email IS NOT NULL AND LOWER(email) =
                                (SELECT LOWER(email) FROM contacts WHERE id = ?)""", (contact_id,))
            conn.commit()
        finally:
            conn.close()
        flash("Saved. " + ("This person will not be emailed by blasts or one-to-one emails." if want["do_not_email"] else "")
              + (" Staff are told not to call." if want["do_not_call"] else "") + (" Staff are told not to text." if want["do_not_text"] else ""))
        return redirect(back)

    @crm.route("/do-not-contact")
    @owner_required
    def do_not_contact_list():
        conn = get_db()
        try:
            ensure(conn)
            people = conn.execute("""SELECT id, first_name, last_name, email, do_not_email, do_not_call, do_not_text, dnc_note, dnc_at, dnc_by
                                     FROM contacts WHERE COALESCE(do_not_email,0)=1 OR COALESCE(do_not_call,0)=1 OR COALESCE(do_not_text,0)=1
                                     ORDER BY COALESCE(dnc_at,'') DESC, last_name, first_name""").fetchall()
            sup = conn.execute("SELECT * FROM email_suppressions ORDER BY id DESC").fetchall()
            try:
                complaints = conn.execute("""SELECT DISTINCT ON (LOWER(email)) email, event, happened_at FROM email_bounces
                                             WHERE event IN ('spam','unsubscribed') ORDER BY LOWER(email), id DESC""").fetchall()
            except Exception:
                conn.rollback(); complaints = []
        finally:
            conn.close()
        return render_template("do_not_contact.html", people=people, sup=sup, complaints=complaints)

    @crm.route("/do-not-contact/add", methods=["POST"])
    @owner_required
    def do_not_contact_add():
        email = (request.form.get("email") or "").strip().lower()
        if "@" not in email or " " in email:
            flash("Please type a full email address. Nothing was added.")
            return redirect(url_for(".do_not_contact_list"))
        conn = get_db()
        try:
            ensure(conn)
            conn.execute("""INSERT INTO email_suppressions (email, reason, added_at, added_by) VALUES (?,?,?,?)
                            ON CONFLICT (email) DO NOTHING""",
                         (email, (request.form.get("reason") or "").strip()[:300], datetime.now().strftime("%Y-%m-%d %H:%M"), session.get("staff_name")))
            conn.execute("UPDATE contacts SET do_not_email = 1 WHERE LOWER(email) = ?", (email,))
            conn.commit()
        finally:
            conn.close()
        flash(f"{email} will never be emailed by blasts or one-to-one emails.")
        return redirect(url_for(".do_not_contact_list"))

    @crm.route("/do-not-contact/<int:sid>/remove", methods=["POST"])
    @owner_required
    def do_not_contact_remove(sid):
        conn = get_db()
        try:
            conn.execute("DELETE FROM email_suppressions WHERE id = ?", (sid,))
            conn.commit()
        finally:
            conn.close()
        flash("Removed from the blocked-address list.")
        return redirect(url_for(".do_not_contact_list"))

    @crm.route("/do-not-contact.csv")
    @owner_required
    def do_not_contact_csv():
        conn = get_db()
        try:
            ensure(conn)
            people = conn.execute("""SELECT id, first_name, last_name, email, do_not_email, do_not_call, do_not_text, dnc_note, dnc_at, dnc_by
                                     FROM contacts WHERE COALESCE(do_not_email,0)=1 OR COALESCE(do_not_call,0)=1 OR COALESCE(do_not_text,0)=1
                                     ORDER BY last_name, first_name""").fetchall()
            sup = conn.execute("SELECT * FROM email_suppressions ORDER BY email").fetchall()
        finally:
            conn.close()
        buf = io.StringIO(); w = csv.writer(buf)
        w.writerow(["Hub ID", "First", "Last", "Email", "Do not email", "Do not call", "Do not text", "Note", "When", "By"])
        for p in people:
            w.writerow([p["id"], p["first_name"], p["last_name"] or "", p["email"] or "", "Yes" if p["do_not_email"] else "",
                        "Yes" if p["do_not_call"] else "", "Yes" if p["do_not_text"] else "", p["dnc_note"] or "", p["dnc_at"] or "", p["dnc_by"] or ""])
        for s in sup:
            w.writerow(["", "", "", s["email"], "Yes", "", "", s["reason"] or "Typed in (no contact record)", s["added_at"] or "", s["added_by"] or ""])
        return Response(buf.getvalue(), mimetype="text/csv", headers={"Content-Disposition": "attachment; filename=do-not-contact.csv"})
