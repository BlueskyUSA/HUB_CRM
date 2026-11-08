"""Personal welcome links: give someone a Hub login WITHOUT the Hub emailing them, so the Owner can send a personal note.
The Hub makes a one-time link (good for 7 days). The person opens it and chooses their own password, so no password
is ever written in a message. The link is stored only as a fingerprint, so it cannot be read back from the database."""
import hashlib
import secrets
from datetime import datetime, timedelta
from flask import render_template, request, redirect, url_for, session, flash
from werkzeug.security import generate_password_hash

DAYS_GOOD = 7


def _fp(token):
    return hashlib.sha256(token.encode()).hexdigest()


def ensure(conn):
    conn.execute("""CREATE TABLE IF NOT EXISTS staff_invites (id SERIAL PRIMARY KEY, staff_id INTEGER NOT NULL,
        token_hash TEXT NOT NULL UNIQUE, created_at TEXT, created_by TEXT, expires_at TEXT, used_at TEXT)""")
    conn.commit()


def make_invite(conn, staff_id, created_by):
    """New link for this person; any earlier unused link stops working. Returns the raw token (shown once)."""
    ensure(conn)
    now = datetime.now()
    conn.execute("UPDATE staff_invites SET used_at = 'replaced' WHERE staff_id = ? AND used_at IS NULL", (staff_id,))
    token = secrets.token_urlsafe(32)
    conn.execute("INSERT INTO staff_invites (staff_id, token_hash, created_at, created_by, expires_at) VALUES (?,?,?,?,?)",
                 (staff_id, _fp(token), now.strftime("%Y-%m-%d %H:%M:%S"), created_by,
                  (now + timedelta(days=DAYS_GOOD)).strftime("%Y-%m-%d %H:%M:%S")))
    conn.commit()
    return token


def register(app, crm, get_db, leadership_required, area_assign_logins, role_label, role_blurbs, program_name, ensure_must_change):
    def _page(staff, contact_first, token, heading):
        link = url_for("public_welcome", token=token, _external=True)
        login_url = url_for("crm.login", _external=True)
        first = (contact_first or staff["name"] or "").split()[0] if (contact_first or staff["name"]) else "there"
        me = (session.get("staff_name") or "").split()[0] or ""
        note = (f"Hi {first},\n\n[Write your own words here: why you're inviting them and your vision for Discovery!]\n\n"
                f"I've set you up with a login to the {program_name} team site as {role_label(staff['role'] if staff['is_owner'] != 2 else 'Administrator')}. "
                f"{role_blurbs.get('Administrator' if staff['is_owner'] == 2 else staff['role'], '')}\n\n"
                f"Use this personal link to choose your own password. It works once and expires in {DAYS_GOOD} days:\n{link}\n\n"
                f"After that, log in any time at {login_url} with {staff['email']}.\n\n{me}")
        return render_template("staff_invite_done.html", heading=heading, staff=staff, link=link, note=note, days=DAYS_GOOD)

    def after_create(contact, choice_label_staff_id):
        conn = get_db()
        try:
            staff = conn.execute("SELECT * FROM staff WHERE id = ?", (choice_label_staff_id,)).fetchone()
            token = make_invite(conn, staff["id"], session.get("staff_name"))
        finally:
            conn.close()
        return _page(staff, contact["first_name"], token, f"{contact['full_name']}'s login is ready. Nothing was emailed.")

    app.config["PERSONAL_INVITE_AFTER_CREATE"] = after_create

    @crm.route("/contacts/<int:contact_id>/personal-link", methods=["POST"])
    @leadership_required
    @area_assign_logins
    def contact_personal_link(contact_id):
        back = redirect(url_for(".contact_detail", contact_id=contact_id) + "#hub-login")
        conn = get_db()
        try:
            c = conn.execute("SELECT first_name FROM contacts WHERE id = ?", (contact_id,)).fetchone()
            staff = conn.execute("SELECT * FROM staff WHERE contact_id = ? AND active = 1 LIMIT 1", (contact_id,)).fetchone()
            if not staff:
                flash("This person has no active Hub login yet.")
                return back
            true_owner = bool(session.get("is_owner")) and not session.get("is_admin")
            if staff["is_owner"] == 1 or (staff["is_owner"] == 2 and not true_owner) or (not session.get("is_owner") and staff["role"] != "Team"):
                flash("Only the Owner can make a welcome link for that kind of login.")
                return back
            token = make_invite(conn, staff["id"], session.get("staff_name"))
        finally:
            conn.close()
        return _page(staff, c["first_name"] if c else "", token, "New personal welcome link. Nothing was emailed.")

    @crm.route("/staff/<int:staff_id>/personal-link", methods=["POST"])
    @leadership_required
    @area_assign_logins
    def staff_personal_link(staff_id):
        back = redirect(url_for(".staff_list"))
        conn = get_db()
        try:
            staff = conn.execute("SELECT * FROM staff WHERE id = ? AND active = 1", (staff_id,)).fetchone()
            if not staff:
                flash("That login is not active.")
                return back
            true_owner = bool(session.get("is_owner")) and not session.get("is_admin")
            if staff["is_owner"] == 1 or (staff["is_owner"] == 2 and not true_owner) or (not session.get("is_owner") and staff["role"] != "Team"):
                flash("Only the Owner can make a welcome link for that kind of login.")
                return back
            first = (staff["name"] or "").split()[0] if staff["name"] else ""
            token = make_invite(conn, staff["id"], session.get("staff_name"))
        finally:
            conn.close()
        return _page(staff, first, token, f"New personal welcome link for {staff['name']}. Nothing was emailed.")

    def _lookup(conn, token):
        ensure(conn)
        inv = conn.execute("SELECT * FROM staff_invites WHERE token_hash = ?", (_fp(token),)).fetchone()
        if not inv or inv["used_at"] or inv["expires_at"] < datetime.now().strftime("%Y-%m-%d %H:%M:%S"):
            return None, None
        staff = conn.execute("SELECT * FROM staff WHERE id = ? AND active = 1", (inv["staff_id"],)).fetchone()
        return (inv, staff) if staff else (None, None)

    @app.route("/welcome/<token>", methods=["GET", "POST"])
    def public_welcome(token):
        conn = get_db()
        try:
            inv, staff = _lookup(conn, token)
            if not inv:
                return render_template("welcome_set_password.html", bad=True, program_name=program_name), 410
            label = role_label("Leadership" if staff["is_owner"] == 2 else staff["role"]) if staff["is_owner"] != 2 else "Administrator"
            error = ""
            if request.method == "POST":
                new, confirm = request.form.get("new_password", ""), request.form.get("confirm_password", "")
                if len(new) < 8:
                    error = "Please choose a password of at least 8 characters."
                elif new != confirm:
                    error = "The two passwords didn't match."
                else:
                    ensure_must_change()
                    conn.execute("UPDATE staff SET password_hash = ?, must_change_password = 0 WHERE id = ?", (generate_password_hash(new), staff["id"]))
                    conn.execute("UPDATE staff_invites SET used_at = ? WHERE id = ?", (datetime.now().strftime("%Y-%m-%d %H:%M:%S"), inv["id"]))
                    conn.commit()
                    flash("Your password is set. Please log in.")
                    return redirect(url_for("crm.login"))
            return render_template("welcome_set_password.html", bad=False, staff=staff, label=label, error=error, program_name=program_name)
        finally:
            conn.close()
