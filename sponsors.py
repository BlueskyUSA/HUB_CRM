"""Sponsors: a volunteer who wants to sponsor someone fills out a form on the website and gets a private page,
the same page an Ambassador uses (/call/<token>), to manage the person they sponsor.

Steps:  /sponsor            -> ONE short form: the volunteer's own details, the person they want to sponsor, and a permission box.
                               We then email the volunteer a letter (editable under Correspondence): complete your profile (and add a
                               photo), and here is the private web page you will get.
        /sponsor/thanks/<t> -> shows the private page link.
        The private page (/call/<token>) opens only after the volunteer's profile and photo are complete; until then it shows
        what is still needed.
        /sponsor-training   -> a short guide for Sponsors.
Behind the scenes a Sponsor is a row in call_volunteers with program_code 'SPONSOR' (never part of the Ambassador alert groups),
and the sponsored person is a call_requests row already claimed by that Sponsor, so checklist, letters, payment nudges and
milestone notices all work exactly as they do for Ambassadors."""
import secrets

from flask import render_template, request, redirect, url_for, abort

import call_flow as cf
import botguard

CODE = "SPONSOR"
SPONSOR_CONSENT = (
    "I give Sojourn permission to share my name, my cell phone number and my email address with the person I am "
    "sponsoring, so they can recognize and reach me. I have told this person that I am inviting them, and I believe "
    "they would welcome hearing from Sojourn. Sojourn will not sell or rent my information. I can withdraw this "
    "permission at any time by telling Sojourn.")


def profile_status(conn, contact, base_url):
    """Has this contact completed the profile (address, cell, emergency contact) and added a photo?"""
    need = (("street_address", "street address"), ("city", "city"), ("state", "state"), ("zip", "zip"),
            ("cell_phone", "cell phone"), ("emergency_contact_name", "emergency contact"),
            ("emergency_contact_cell", "emergency contact phone"))
    missing = [lab for col, lab in need if not (contact[col] or "").strip()]
    photo = bool(conn.execute("SELECT 1 FROM contact_photos WHERE contact_id = ?", (contact["id"],)).fetchone())
    if not photo:
        missing.append("photo")
    token = contact["profile_token"]
    if not token:
        token = secrets.token_urlsafe(16)
        conn.execute("UPDATE contacts SET profile_token = ? WHERE id = ?", (token, contact["id"]))
        conn.commit()
    return dict(complete=not missing, missing=missing, link=f"{base_url}/complete-profile/{token}", token=token)


def register(app, get_db, leadership_email=None):

    def _contact_by_email(conn, email):
        return conn.execute("SELECT * FROM contacts WHERE lower(email) = lower(?) OR lower(email_2) = lower(?) OR lower(email_3) = lower(?) "
                            "ORDER BY id LIMIT 1", (email, email, email)).fetchone()

    @app.route("/sponsor", methods=["GET", "POST"])
    def public_sponsor():
        cf.ensure_tables(get_db)
        error, form = None, request.form
        if request.method == "POST":
            my_first = (form.get("my_first") or "").strip()
            my_last = (form.get("my_last") or "").strip() or None
            my_email = (form.get("my_email") or "").strip()
            my_phone = (form.get("my_phone") or "").strip()
            first = (form.get("first_name") or "").strip()
            last = (form.get("last_name") or "").strip() or None
            email = (form.get("email") or "").strip()
            phone = (form.get("phone") or "").strip()
            program = (form.get("program_code") or "").strip().upper()
            note = (form.get("note") or "").strip()[:1500]
            typed = (form.get("full_name") or "").strip()
            ok_bot, bot_msg = botguard.check(get_db, "sponsor", form, email=my_email, ip_limit=4)
            if not ok_bot:
                if bot_msg is None:
                    return redirect(url_for("public_sponsor"))
                error = bot_msg
            elif not my_first or "@" not in my_email or len(cf._digits(my_phone)) < 10:
                error = "Please enter your first name, your email and your cell phone number."
            elif not first or "@" not in email:
                error = "Please enter the first name and email of the person you want to sponsor."
            elif not form.get("agree"):
                error = "Please tick the box to give your permission."
            elif len(typed) < 3:
                error = "Please type your full name to sign."
            else:
                conn = get_db()
                try:
                    ip = (request.headers.get("X-Forwarded-For", "") or request.remote_addr or "").split(",")[0].strip()
                    now = cf._ts(cf._utc_now())
                    me = _contact_by_email(conn, my_email)
                    if not me:
                        cid = cf._find_or_make_contact(conn, my_first, my_last, my_email, my_phone, "(Volunteer who filled out the Sponsor form)")
                        conn.commit()
                        me = conn.execute("SELECT * FROM contacts WHERE id = ?", (cid,)).fetchone()
                    elif not (me["cell_phone"] or "").strip():
                        conn.execute("UPDATE contacts SET cell_phone = ? WHERE id = ?", (my_phone, me["id"]))
                        conn.commit()
                        me = conn.execute("SELECT * FROM contacts WHERE id = ?", (me["id"],)).fetchone()
                    my_name = f"{me['first_name']} {me['last_name'] or ''}".strip()
                    v = conn.execute("SELECT * FROM call_volunteers WHERE active = 1 AND program_code = ? AND lower(email) = lower(?) ORDER BY id LIMIT 1",
                                     (CODE, my_email)).fetchone()
                    if not v:
                        conn.execute("INSERT INTO call_volunteers (program_code, name, cell_phone, email, consent_token) VALUES (?, ?, ?, ?, ?)",
                                     (CODE, my_name, me["cell_phone"] or my_phone, my_email, secrets.token_urlsafe(16)))
                        v = conn.execute("SELECT * FROM call_volunteers WHERE program_code = ? AND lower(email) = lower(?) ORDER BY id DESC LIMIT 1",
                                         (CODE, my_email)).fetchone()
                    conn.execute("UPDATE call_volunteers SET consent_at = ?, consent_name = ?, consent_ip = ?, consent_text = ? WHERE id = ?",
                                 (now, typed[:120], ip, SPONSOR_CONSENT, v["id"]))
                    pid = cf._find_or_make_contact(conn, first, last, email, phone, f"Sponsored by {my_name} (website Sponsor form)")
                    conn.execute("UPDATE contacts SET sponsor_name = COALESCE(NULLIF(sponsor_name, ''), ?), sponsor_email = COALESCE(NULLIF(sponsor_email, ''), ?), "
                                 "sponsor_phone = COALESCE(NULLIF(sponsor_phone, ''), ?) WHERE id = ?", (my_name, my_email, me["cell_phone"] or my_phone, pid))
                    req = conn.execute("SELECT id FROM call_requests WHERE contact_id = ? AND claimed_by = ? AND source = 'sponsor' ORDER BY id DESC LIMIT 1",
                                       (pid, v["id"])).fetchone()
                    if req:
                        rid, fresh = req["id"], False
                    else:
                        cur = conn.execute(
                            """INSERT INTO call_requests (contact_id, program_code, cell_phone, note, source, consent_text, consent_at, consent_ip,
                                   created_at, contact_pref, status, claimed_by, claimed_at, reminder_at)
                               VALUES (?, ?, ?, ?, 'sponsor', ?, ?, ?, ?, 'either', 'Claimed', ?, ?, ?)""",
                            (pid, program or None, phone or None, note or None, f"Sponsored by {my_name}", now, ip, now, v["id"], now, now))
                        rid, fresh = cur.lastrowid, True
                    tok = cf._notice_for(conn, rid, v["id"])
                    st = profile_status(conn, me, cf._base_url())
                    conn.commit()
                    page = f"{cf._base_url()}/call/{tok}"
                    who = f"{first} {last or ''}".strip()
                    if fresh and cf.sponsor_live():
                        try:
                            from email_templates import guide_letter_content
                            subject, html, text = guide_letter_content(
                                "sponsor_welcome", me["first_name"], cf._program_label(program) if program else "Sojourn", my_name,
                                cf.pretty_phone(me["cell_phone"] or my_phone), link=st["link"], client=who, page_link=page)
                            cf._send(my_email, subject, html, text, to_name=my_name)
                            cf._send(cf._leadership_email(), f"New Sponsor: {my_name} is sponsoring {who}",
                                     f"<p>{my_name} filled out the Sponsor form for {who}.</p>", f"{my_name} filled out the Sponsor form for {who}.")
                        except Exception as e:
                            print(f"Sponsor emails failed: {e}", flush=True)
                    return redirect(url_for("public_sponsor_thanks", token=tok))
                finally:
                    conn.close()
        return render_template("public_sponsor_start.html", error=error, form=form,
                               programs=[("D4", "The Art of Us"), ("D1", "The Beginning"), ("", "Not sure yet")],
                               consent=SPONSOR_CONSENT)

    @app.route("/sponsor/thanks/<token>")
    def public_sponsor_thanks(token):
        cf.ensure_tables(get_db)
        conn = get_db()
        try:
            n = conn.execute("SELECT * FROM call_notices WHERE token = ?", (token,)).fetchone()
            if not n:
                abort(404)
            req = conn.execute("SELECT r.*, c.first_name, c.last_name FROM call_requests r JOIN contacts c ON c.id = r.contact_id WHERE r.id = ?",
                               (n["request_id"],)).fetchone()
            vol = conn.execute("SELECT email FROM call_volunteers WHERE id = ?", (n["volunteer_id"],)).fetchone()
            me = _contact_by_email(conn, vol["email"]) if vol else None
            st = profile_status(conn, me, cf._base_url()) if me else None
            return render_template("public_sponsor_thanks.html", who=f"{req['first_name']} {req['last_name'] or ''}".strip(),
                                   page=cf._base_url() + "/call/" + token, emailed=cf.sponsor_live(), st=st)
        finally:
            conn.close()

    @app.route("/sponsor-training")
    def public_sponsor_training():
        return render_template("public_sponsor_training.html")
