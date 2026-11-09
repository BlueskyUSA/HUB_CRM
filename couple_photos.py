"""Couple photos: each contact has a second photo slot for a photo of the couple (the individual photo stays as it is).
When the person is linked to a partner (as a couple in a training session, or by the partner email on their record),
saving the couple photo on one partner's page saves it on the partner's page too."""
from datetime import datetime
from flask import request, redirect, url_for, flash, abort, make_response, session


def ensure(conn):
    conn.execute("""CREATE TABLE IF NOT EXISTS couple_photos (contact_id INTEGER PRIMARY KEY REFERENCES contacts(id) ON DELETE CASCADE,
        data BYTEA NOT NULL, content_type TEXT NOT NULL, updated_at TEXT, updated_by TEXT)""")
    conn.commit()


def partner_contact_id(conn, contact_id):
    """The partner's contact id if clearly known, else None. Enrollment couple link first, then partner email."""
    try:
        r = conn.execute("""SELECT p.contact_id AS pid FROM enrollments e JOIN enrollments p ON p.id = e.partner_enrollment_id
                            WHERE e.contact_id = ? AND e.partner_enrollment_id IS NOT NULL ORDER BY e.id DESC LIMIT 1""", (contact_id,)).fetchone()
        if r and r["pid"] != contact_id:
            return r["pid"]
    except Exception:
        try: conn.rollback()
        except Exception: pass
    try:
        me = conn.execute("SELECT partner_email FROM contacts WHERE id = ?", (contact_id,)).fetchone()
        pe = ((me["partner_email"] if me else "") or "").strip().lower()
        if pe:
            hits = conn.execute("SELECT id FROM contacts WHERE LOWER(email) = ? AND id <> ?", (pe, contact_id)).fetchall()
            if len(hits) == 1:
                return hits[0]["id"]
    except Exception:
        try: conn.rollback()
        except Exception: pass
    return None


def save_couple_photo(conn, contact_id, data, ctype, staff_name):
    """Saves the couple photo on this contact and (if clearly linked) on the partner. Returns the partner's contact id or None."""
    ensure(conn)
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    pid = partner_contact_id(conn, contact_id)
    for cid in [contact_id] + ([pid] if pid else []):
        conn.execute("DELETE FROM couple_photos WHERE contact_id = ?", (cid,))
        conn.execute("INSERT INTO couple_photos (contact_id, data, content_type, updated_at, updated_by) VALUES (?,?,?,?,?)",
                     (cid, data, ctype, now, staff_name))
    conn.commit()
    return pid


def register(app, crm, area_contacts, get_db, process_photo):
    def couple_photo_ts(contact_id):
        try:
            conn = get_db()
            try:
                ensure(conn)
                r = conn.execute("SELECT updated_at FROM couple_photos WHERE contact_id = ?", (contact_id,)).fetchone()
            finally:
                conn.close()
            return (r["updated_at"] or "x") if r else None
        except Exception:
            return None
    app.jinja_env.globals["couple_photo_ts"] = couple_photo_ts

    @crm.route("/contacts/<int:contact_id>/couple-photo", methods=["POST"])
    @area_contacts
    def contact_couple_photo_upload(contact_id):
        res = process_photo(request.files.get("photo"))
        if not res:
            flash("No photo was saved. Choose a JPG, PNG, WEBP or HEIC file.")
            return redirect(url_for(".contact_detail", contact_id=contact_id) + "#couple-photo")
        data, ctype = res
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        conn = get_db()
        try:
            ensure(conn)
            pid = partner_contact_id(conn, contact_id)
            for cid in [contact_id] + ([pid] if pid else []):
                conn.execute("DELETE FROM couple_photos WHERE contact_id = ?", (cid,))
                conn.execute("INSERT INTO couple_photos (contact_id, data, content_type, updated_at, updated_by) VALUES (?,?,?,?,?)",
                             (cid, data, ctype, now, session.get("staff_name")))
            partner = None
            if pid:
                partner = conn.execute("SELECT first_name, last_name FROM contacts WHERE id = ?", (pid,)).fetchone()
            conn.commit()
        finally:
            conn.close()
        flash("Couple photo saved." + (f" It was also saved on {partner['first_name']} {partner['last_name'] or ''}'s page." if partner else
                                       " (No partner is linked yet, so it is saved on this page only.)"))
        return redirect(url_for(".contact_detail", contact_id=contact_id) + "#couple-photo")

    @crm.route("/contacts/<int:contact_id>/couple-photo-file")
    @area_contacts
    def contact_couple_photo_file(contact_id):
        conn = get_db()
        try:
            ensure(conn)
            row = conn.execute("SELECT data, content_type FROM couple_photos WHERE contact_id = ?", (contact_id,)).fetchone()
        finally:
            conn.close()
        if not row:
            abort(404)
        resp = make_response(bytes(row["data"]))
        resp.headers["Content-Type"] = row["content_type"] or "image/jpeg"
        resp.headers["Cache-Control"] = "private, max-age=86400"
        return resp

    @crm.route("/contacts/<int:contact_id>/couple-photo/remove", methods=["POST"])
    @area_contacts
    def contact_couple_photo_remove(contact_id):
        conn = get_db()
        try:
            conn.execute("DELETE FROM couple_photos WHERE contact_id = ?", (contact_id,))
            conn.commit()
        finally:
            conn.close()
        flash("Couple photo removed from this page. (Their partner's page keeps its copy.)")
        return redirect(url_for(".contact_detail", contact_id=contact_id) + "#couple-photo")
