"""Testimonials: invite a contact to share their experience (typed, dictated or recorded), review it in the CRM,
and publish approved stories on the public Stories page.

Public:  /share/<token>   the private link a contact opens to share
         /stories         approved stories, grouped by program
         /stories/video/<id>   approved videos only
CRM:     Admin > Testimonials (review list), /testimonials/request (send a link), /testimonials/<id> (review)
"""
import io
import re
import secrets
from datetime import datetime
import html as _html

from email_utils import DEFAULT_FROM_EMAIL
from flask import render_template, request, redirect, url_for, flash, abort, session, send_file, make_response

# (code, label) in the order shown on the Stories page; "GEN" = general / more than one program
STORY_PROGRAMS = [("D4", "The Art of Us"), ("D1", "The Beginning"), ("D2", "Awakening"), ("D3", "Vision"),
                  ("D5", "Renew"), ("D6", "Spiritual"), ("GEN", "The program in general")]
PROGRAM_LABEL = dict(STORY_PROGRAMS)
MAX_VIDEO_BYTES = 70 * 1024 * 1024
NAME_CHOICES = [("full", "My full name"), ("initial", "My first name and last initial"), ("anon", "Anonymous")]
CONSENT_TEXT = ("I give Sojourn permission to publish what I have shared here (my words and/or my video) on its "
                "website and in its materials, using the name choice I picked. I understand I can ask to have it "
                "removed at any time.")

# Words that sound therapeutic or medical. Shown as a warning on the review page so they can be edited out
# (or the person asked) before anything is published. Matching is by word start, e.g. "heal" also catches "healing".
FLAG_WORDS = ["heal", "therap", "cure", "cured", "trauma", "depress", "anxiety", "anxious", "ptsd", "diagnos", "treatment",
              "medicat", "psychiatr", "psycholog", "counsel", "disorder", "addiction", "recovery", "abuse", "suicid",
              "mental health", "clinical", "symptom", "disease", "illness", "bipolar", "panic"]


def flagged_words(text):
    low = (text or "").lower()
    return sorted({w for w in FLAG_WORDS if re.search(r"\b" + re.escape(w), low)})


def _note_html(note, home_url="", stories_url=""):
    """Escaped note text with web addresses turned into clickable links (our own two pages get friendly names)."""
    esc = _html.escape(note)
    labels = {}
    if home_url:
        labels[_html.escape(home_url)] = "our website"
    if stories_url:
        labels[_html.escape(stories_url)] = "what others are saying"

    def link(m):
        url = m.group(1)
        trail = ""
        while url and url[-1] in ".,;:!?)":
            trail, url = url[-1] + trail, url[:-1]
        return f'<a href="{url}">{labels.get(url, url)}</a>{trail}'
    esc = re.sub(r"(https?://[^\s<]+)", link, esc)
    return esc.replace(chr(10), "<br>")


def letter_parts(include_links, site_on, home_url, stories_url):
    """The testimonial request letter (wording from the Correspondence page, or the original), as ready-to-show parts."""
    import email_templates as et
    spec = et.GUIDE_LETTERS["testimonial_request"]
    fill = {"first": "", "link": "\x00LINK\x00", "home_url": home_url, "stories_url": stories_url,
            "stories_sentence": (f" If you'd like ideas, see {stories_url}." if site_on else "")}

    def build(sp):
        paras = []
        for raw in sp["paras"]:
            text = raw.format(**fill).strip()
            if not text:
                continue
            if text == "\x00LINK\x00":
                paras.append(("button", ""))
            elif "{home_url}" in raw:
                if include_links:
                    paras.append(("links", _note_html(text, home_url, stories_url)))
            else:
                paras.append(("text", _note_html(text, home_url, stories_url)))
        return dict(subject=sp["subject"].format(**fill), greeting=sp.get("greeting", "Hi"), paras=paras,
                    signoff=sp["signoff"].format(**fill), signer=sp.get("signer", "Kent").format(**fill))
    edit = et.saved_edit("testimonial_request")
    if edit:
        try:
            return build(et.spec_with_edit("testimonial_request", edit))
        except Exception:
            pass
    return build(spec)


_ready = False


def _ensure(get_db):
    global _ready
    if _ready:
        return
    conn = get_db()
    try:
        conn.execute("""CREATE TABLE IF NOT EXISTS testimonial_requests (
            id SERIAL PRIMARY KEY, token TEXT UNIQUE NOT NULL, contact_id INTEGER, program_code TEXT,
            note TEXT, created_at TEXT, sent_at TEXT, sent_by TEXT, submitted_at TEXT)""")
        conn.execute("""CREATE TABLE IF NOT EXISTS testimonials (
            id SERIAL PRIMARY KEY, request_id INTEGER, contact_id INTEGER, program_code TEXT,
            body TEXT, body_original TEXT, name_choice TEXT, display_name TEXT, attended TEXT,
            video_data BYTEA, video_type TEXT, status TEXT NOT NULL DEFAULT 'New', featured INTEGER NOT NULL DEFAULT 0,
            consent_at TEXT, created_at TEXT, approved_at TEXT)""")
        for col in ("confirm_token TEXT", "confirm_state TEXT", "confirm_note TEXT", "confirm_at TEXT",
                    "submitter_name TEXT", "submitter_email TEXT", "submitter_phone TEXT", "referred_by TEXT"):
            conn.execute(f"ALTER TABLE testimonials ADD COLUMN IF NOT EXISTS {col}")
        conn.commit()
        _ready = True
    except Exception as e:
        conn.rollback()
        print(f"Couldn't create testimonial tables: {e}", flush=True)
    finally:
        conn.close()


def _display_name(choice, first, last):
    first, last = (first or "").strip(), (last or "").strip()
    if choice == "anon":
        return "Anonymous"
    if choice == "initial":
        return (first + (" " + last[0] + "." if last else "")).strip() or "Anonymous"
    return (first + " " + last).strip() or "Anonymous"


def has_qualifying_role(notes):
    """True if the contact's notes (from the short /discovery form) list a real past role other than 'Other'.
    The short form writes a line like 'Roles: Facilitator (March 2018); TA'. 'Interested Party' is never listed."""
    for line in (notes or "").splitlines():
        if line.startswith("Roles:"):
            for part in line[len("Roles:"):].split(";"):
                role = re.sub(r"\s*\(.*\)\s*$", "", part).strip()
                if role and role.lower() != "other":
                    return True
    return False


def share_link_for_contact(get_db, contact_id, external_url_for):
    """Private testimonial link for a contact who said they attended, for the thank-you email. Reuses an open
    request; returns None if they already sent a story (so we never ask twice). external_url_for(token) -> full URL."""
    _ensure(get_db)
    conn = get_db()
    try:
        done = conn.execute("SELECT 1 FROM testimonial_requests WHERE contact_id = ? AND submitted_at IS NOT NULL", (contact_id,)).fetchone()
        if done:
            return None
        row = conn.execute("SELECT token FROM testimonial_requests WHERE contact_id = ? AND submitted_at IS NULL ORDER BY id DESC",
                           (contact_id,)).fetchone()
        if row:
            token = row["token"]
        else:
            token = secrets.token_urlsafe(16)
            conn.execute("""INSERT INTO testimonial_requests (token, contact_id, program_code, note, created_at, sent_at, sent_by)
                            VALUES (?, ?, 'GEN', NULL, ?, ?, ?)""",
                         (token, contact_id, datetime.now().strftime("%Y-%m-%d %H:%M"),
                          datetime.now().strftime("%Y-%m-%d %H:%M"), "thank-you email"))
            conn.commit()
        return external_url_for(token)
    except Exception as e:
        conn.rollback()
        print(f"share link failed: {e}", flush=True)
        return None
    finally:
        conn.close()


def pass_it_on(first, link):
    """The ready-made note a person can send to a friend who also attended."""
    who = (first or "").strip()
    greeting = f"Hey there, it's {who}!" if who else "Hey there!"
    return (greeting + "\n\n"
            "I just shared a short testimonial about my experience with the program, and I thought you might enjoy "
            "sharing yours, too.\n\n"
            "We'd love to hear what the program meant to you and what you took away from the experience. It only takes "
            "a few minutes, and you can share your story in writing or through a short video. "
            "Just enter your name, email, and cell number to get started.\n\n"
            "Here's the link to share your story:\n" + link)


_vis_cache = {"v": False, "at": 0.0}


def stories_on(get_db, fresh=False):
    """Whether testimonials are shown on the public website (off until Kent flips it on). Cached for 20 seconds."""
    import time
    now = time.time()
    if not fresh and now - _vis_cache["at"] < 20:
        return _vis_cache["v"]
    try:
        conn = get_db()
        conn.execute("CREATE TABLE IF NOT EXISTS app_settings (key TEXT PRIMARY KEY, value TEXT)")
        row = conn.execute("SELECT value FROM app_settings WHERE key = 'stories_visible'").fetchone()
        conn.commit()
        conn.close()
        _vis_cache["v"] = bool(row and row["value"] == "1")
    except Exception:
        pass
    _vis_cache["at"] = now
    return _vis_cache["v"]


def register(app, crm, leadership_required, get_db, send_email, full_name_sql, program_name):
    # ---------------- public: the private share link ----------------
    @app.route("/share/<token>", methods=["GET", "POST"])
    def public_share(token):
        _ensure(get_db)
        conn = get_db()
        req = conn.execute(
            f"""SELECT r.*, ct.first_name, ct.last_name FROM testimonial_requests r
                LEFT JOIN contacts ct ON ct.id = r.contact_id WHERE r.token = ?""", (token,)).fetchone()
        if not req:
            conn.close()
            return render_template("public_share.html", req=None), 404
        if req["submitted_at"]:
            conn.close()
            return render_template("public_share.html", req=req, already=True, done=False)
        if request.method == "POST":
            body = (request.form.get("body") or "").strip()[:8000]
            choice = request.form.get("name_choice") if request.form.get("name_choice") in dict(NAME_CHOICES) else "initial"
            f = request.files.get("video")
            vdata, vtype = None, None
            if f and f.filename:
                vdata = f.read(MAX_VIDEO_BYTES + 1)
                vtype = (f.mimetype or "video/mp4")[:60]
                if len(vdata) > MAX_VIDEO_BYTES:
                    flash("That video is too large. Please record a shorter one (up to 2 minutes) right on this page.")
                    conn.close()
                    return redirect(url_for("public_share", token=token))
                if not vdata:
                    vdata, vtype = None, None
            if not body and not vdata:
                flash("Please type, dictate or record something to share.")
                conn.close()
                return redirect(url_for("public_share", token=token))
            if not request.form.get("consent"):
                flash("Please tick the permission box so we may share your words.")
                conn.close()
                return redirect(url_for("public_share", token=token))
            program = req["program_code"] if req["program_code"] in PROGRAM_LABEL else "GEN"
            now = datetime.now().strftime("%Y-%m-%d %H:%M")
            conn.execute(
                """INSERT INTO testimonials (request_id, contact_id, program_code, body, body_original, name_choice,
                       display_name, attended, video_data, video_type, status, consent_at, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'New', ?, ?)""",
                (req["id"], req["contact_id"], program, body, body, choice,
                 _display_name(choice, req["first_name"], req["last_name"]),
                 (request.form.get("attended") or "").strip()[:60], vdata, vtype, now, now))
            conn.execute("UPDATE testimonial_requests SET submitted_at = ? WHERE id = ?", (now, req["id"]))
            owners = conn.execute("SELECT email, name FROM staff WHERE is_owner = 1 AND active = 1").fetchall()
            conn.commit()
            conn.close()
            link = url_for("crm.testimonials_review", _external=True)
            for o in owners:
                try:
                    send_email(to_email=o["email"], to_name=o["name"], subject="A new testimonial is ready to review",
                               html_content=f"<p>A new testimonial came in{' (with a video)' if vdata else ''}.</p>"
                                            f"<p><a href=\"{link}\">Open Testimonials to review it</a></p>")
                except Exception as e:
                    print(f"testimonial notice failed: {e}", flush=True)
            return render_template("public_share.html", req=req, done=True, already=False,
                                   pass_link=url_for("public_share_open", _external=True, **{"from": token}),
                                   pass_msg=pass_it_on(req["first_name"], url_for("public_share_open", _external=True, **{"from": token})))
        conn.close()
        return render_template("public_share.html", req=req, done=False, already=False, name_choices=NAME_CHOICES,
                               consent_text=CONSENT_TEXT, program_label=PROGRAM_LABEL.get(req["program_code"]),
                               max_mb=MAX_VIDEO_BYTES // (1024 * 1024))

    # ---------------- public: open link (not tied to one person; for passing along) ----------------
    @app.route("/share", methods=["GET", "POST"])
    def public_share_open():
        _ensure(get_db)
        ref_token = (request.args.get("from") or request.form.get("from") or "")[:60]
        if request.method == "POST":
            if request.form.get("website"):  # hidden trap field: real people leave it empty
                return render_template("public_share.html", req=dict(first_name=""), open_mode=True, done=True, already=False, pass_link="", pass_msg="")
            name = (request.form.get("name") or "").strip()[:100]
            email = (request.form.get("email") or "").strip()[:150]
            phone = (request.form.get("phone") or "").strip()[:40]
            body = (request.form.get("body") or "").strip()[:8000]
            choice = request.form.get("name_choice") if request.form.get("name_choice") in dict(NAME_CHOICES) else "initial"
            program = request.form.get("program") if request.form.get("program") in PROGRAM_LABEL else "GEN"
            f = request.files.get("video")
            vdata, vtype = None, None
            problem = None
            if not name or not (email or phone):
                problem = "Please add your name, and an email or cell number so we can reach you."
            elif f and f.filename:
                vdata = f.read(MAX_VIDEO_BYTES + 1)
                vtype = (f.mimetype or "video/mp4")[:60]
                if len(vdata) > MAX_VIDEO_BYTES:
                    problem = "That video is too large. Please record a shorter one (up to 2 minutes) right on this page."
                elif not vdata:
                    vdata, vtype = None, None
            if not problem and not body and not vdata:
                problem = "Please type, dictate or record something to share."
            if not problem and not request.form.get("consent"):
                problem = "Please tick the permission box so we may share your words."
            if problem:
                flash(problem)
                return redirect(url_for("public_share_open", **({"from": ref_token} if ref_token else {})))
            parts = name.split(None, 1)
            conn = get_db()
            referred = ""
            if ref_token:
                r = conn.execute(f"SELECT {full_name_sql('ct')} AS n FROM testimonial_requests r JOIN contacts ct ON ct.id = r.contact_id WHERE r.token = ?",
                                 (ref_token,)).fetchone()
                referred = r["n"] if r else ""
            now = datetime.now().strftime("%Y-%m-%d %H:%M")
            conn.execute(
                """INSERT INTO testimonials (request_id, contact_id, program_code, body, body_original, name_choice, display_name,
                       attended, video_data, video_type, status, consent_at, created_at,
                       submitter_name, submitter_email, submitter_phone, referred_by)
                   VALUES (NULL, NULL, ?, ?, ?, ?, ?, ?, ?, ?, 'New', ?, ?, ?, ?, ?, ?)""",
                (program, body, body, choice, _display_name(choice, parts[0], parts[1] if len(parts) > 1 else ""),
                 (request.form.get("attended") or "").strip()[:60], vdata, vtype, now, now, name, email, phone, referred))
            owners = conn.execute("SELECT email, name FROM staff WHERE is_owner = 1 AND active = 1").fetchall()
            conn.commit()
            conn.close()
            link = url_for("crm.testimonials_review", _external=True)
            for o in owners:
                try:
                    send_email(to_email=o["email"], to_name=o["name"], subject="A new testimonial is ready to review",
                               html_content=f"<p>{_html.escape(name)} sent a testimonial through the shared link"
                                            f"{' (referred by ' + _html.escape(referred) + ')' if referred else ''}"
                                            f"{' with a video' if vdata else ''}.</p><p><a href=\"{link}\">Open Testimonials to review it</a></p>")
                except Exception as e:
                    print(f"testimonial notice failed: {e}", flush=True)
            first = parts[0] if parts else ""
            pl = url_for("public_share_open", _external=True)
            return render_template("public_share.html", req=dict(first_name=first), open_mode=True, done=True, already=False,
                                   pass_link=pl, pass_msg=pass_it_on(first, pl))
        return render_template("public_share.html", req=dict(first_name=""), open_mode=True, done=False, already=False,
                               name_choices=NAME_CHOICES, consent_text=CONSENT_TEXT, program_label=None, programs=STORY_PROGRAMS,
                               max_mb=MAX_VIDEO_BYTES // (1024 * 1024), ref_token=ref_token)

    # ---------------- public: contributor confirms the edited version ----------------
    @app.route("/share/confirm/<token>", methods=["GET", "POST"])
    def public_share_confirm(token):
        _ensure(get_db)
        conn = get_db()
        t = conn.execute("""SELECT id, program_code, body, display_name, (video_data IS NOT NULL) AS has_video,
                                   confirm_state, confirm_token FROM testimonials WHERE confirm_token = ?""", (token,)).fetchone()
        if not t:
            conn.close()
            return render_template("public_share_confirm.html", t=None), 404
        if request.method == "POST" and t["confirm_state"] == "sent":
            yes = request.form.get("answer") == "yes"
            note = (request.form.get("note") or "").strip()[:2000]
            now = datetime.now().strftime("%Y-%m-%d %H:%M")
            conn.execute("UPDATE testimonials SET confirm_state = ?, confirm_note = ?, confirm_at = ? WHERE id = ?",
                         ("yes" if yes else "changes", note, now, t["id"]))
            owners = conn.execute("SELECT email, name FROM staff WHERE is_owner = 1 AND active = 1").fetchall()
            conn.commit()
            conn.close()
            link = url_for("crm.testimonial_detail", tid=t["id"], _external=True)
            for o in owners:
                try:
                    send_email(to_email=o["email"], to_name=o["name"],
                               subject="Testimonial: " + ("approved by the contributor" if yes else "changes requested"),
                               html_content=f"<p>{_html.escape(t['display_name'])} "
                                            + ("approved the edited version." if yes else "asked for changes.")
                                            + (f"</p><p>Their note: {_html.escape(note)}" if note else "")
                                            + f"</p><p><a href=\"{link}\">Open the testimonial</a></p>")
                except Exception as e:
                    print(f"confirm notice failed: {e}", flush=True)
            return render_template("public_share_confirm.html", t=t, answered="yes" if yes else "changes")
        answered = t["confirm_state"] if t["confirm_state"] in ("yes", "changes") else None
        conn.close()
        return render_template("public_share_confirm.html", t=t, answered=answered, label=PROGRAM_LABEL.get(t["program_code"], ""))

    @app.route("/share/confirm/<token>/video")
    def public_share_confirm_video(token):
        _ensure(get_db)
        conn = get_db()
        row = conn.execute("SELECT video_data, video_type FROM testimonials WHERE confirm_token = ?", (token,)).fetchone()
        conn.close()
        if not row or row["video_data"] is None:
            abort(404)
        return send_file(io.BytesIO(bytes(row["video_data"])), mimetype=row["video_type"] or "video/mp4", conditional=True)

    @app.context_processor
    def _inject_stories_flag():
        return {"stories_visible": stories_on(get_db)}

    # ---------------- public: Stories page ----------------
    @app.route("/stories")
    def public_stories():
        _ensure(get_db)
        if not stories_on(get_db) and not session.get("staff_id"):
            abort(404)
        conn = get_db()
        rows = conn.execute(
            """SELECT id, program_code, body, display_name, attended, (video_data IS NOT NULL) AS has_video
               FROM testimonials WHERE status = 'Approved' ORDER BY featured DESC, approved_at DESC, id DESC""").fetchall()
        conn.close()
        groups = []
        for code, label in STORY_PROGRAMS:
            items = [r for r in rows if r["program_code"] == code]
            if items:
                groups.append(dict(code=code, label=label, items=items))
        return render_template("public_stories.html", groups=groups, total=len(rows))

    @app.route("/stories/video/<int:tid>")
    def public_story_video(tid):
        _ensure(get_db)
        if not stories_on(get_db):
            abort(404)
        conn = get_db()
        row = conn.execute("SELECT video_data, video_type FROM testimonials WHERE id = ? AND status = 'Approved'", (tid,)).fetchone()
        conn.close()
        if not row or row["video_data"] is None:
            abort(404)
        return send_file(io.BytesIO(bytes(row["video_data"])), mimetype=row["video_type"] or "video/mp4", conditional=True)

    # ---------------- CRM ----------------
    @crm.route("/testimonials")
    @leadership_required
    def testimonials_review():
        _ensure(get_db)
        conn = get_db()
        rows = conn.execute(
            f"""SELECT r.id AS req_id, r.program_code AS req_program, r.created_at, r.sent_at, r.token,
                       {full_name_sql('ct')} AS full_name, ct.id AS contact_id, ct.email AS email,
                       t.id AS tid, t.status, t.confirm_state, t.display_name, t.body, (t.video_data IS NOT NULL) AS has_video
                FROM testimonial_requests r
                LEFT JOIN contacts ct ON ct.id = r.contact_id
                LEFT JOIN testimonials t ON t.request_id = r.id
                ORDER BY r.id DESC""").fetchall()
        text_only = conn.execute(
            f"""SELECT ct.id, {full_name_sql('ct')} AS full_name, ct.cell_phone, ct.home_phone FROM contacts ct
                WHERE ct.discovery_attendance = 'Yes' AND (ct.email IS NULL OR TRIM(ct.email) = '')
                  AND (COALESCE(ct.cell_phone, '') <> '' OR COALESCE(ct.home_phone, '') <> '')
                  AND NOT EXISTS (SELECT 1 FROM testimonial_requests r WHERE r.contact_id = ct.id)
                ORDER BY ct.last_name, ct.first_name LIMIT 100""").fetchall()
        open_rows = conn.execute(
            """SELECT id AS tid, program_code AS req_program, created_at, submitter_name AS full_name, status, confirm_state,
                      display_name, body, (video_data IS NOT NULL) AS has_video, referred_by
               FROM testimonials WHERE request_id IS NULL ORDER BY id DESC""").fetchall()
        conn.close()
        items = []
        order = {"review": 0, "changes": 1, "ready": 2, "waiting_ok": 3, "waiting": 4, "published": 5, "hidden": 6}
        all_rows = [dict(r) for r in rows] + [dict(r, req_id=None, sent_at=None, token=None, contact_id=None, email=None) for r in open_rows]
        for d in all_rows:
            if d["tid"] is None:
                d["stage"], d["label"], d["action"] = "waiting", "Waiting for their story", ""
            elif d["status"] == "Approved":
                d["stage"], d["label"], d["action"] = "published", "Published", "Open"
            elif d["status"] == "Hidden":
                d["stage"], d["label"], d["action"] = "hidden", "Hidden", "Open"
            elif d["confirm_state"] == "changes":
                d["stage"], d["label"], d["action"] = "changes", "They asked for changes", "Open"
            elif d["confirm_state"] == "yes":
                d["stage"], d["label"], d["action"] = "ready", "They approved: ready to publish", "Open"
            elif d["confirm_state"] == "sent":
                d["stage"], d["label"], d["action"] = "waiting_ok", "Sent back; waiting for their OK", "Open"
            else:
                d["stage"], d["label"], d["action"] = "review", "Received: needs your review", "Review"
            d["how"] = ("Shared link" + (" (from " + d["referred_by"] + ")" if d.get("referred_by") else "")) if d["req_id"] is None else ("Emailed " + d["sent_at"] if d["sent_at"] else "Link only")
            items.append(d)
        items.sort(key=lambda x: (order[x["stage"]], -(x["req_id"] or x["tid"] or 0)))
        counts = {k: sum(1 for i in items if i["stage"] == k) for k in order}
        return render_template("testimonials_review.html", items=items, counts=counts, labels=PROGRAM_LABEL, text_only=text_only, site_on=stories_on(get_db, fresh=True),
                               show=request.args.get("show") or "")

    @crm.route("/testimonials/site-switch", methods=["POST"])
    @leadership_required
    def testimonials_site_switch():
        want = "1" if request.form.get("on") == "1" else "0"
        conn = get_db()
        conn.execute("CREATE TABLE IF NOT EXISTS app_settings (key TEXT PRIMARY KEY, value TEXT)")
        conn.execute("DELETE FROM app_settings WHERE key = 'stories_visible'")
        conn.execute("INSERT INTO app_settings (key, value) VALUES ('stories_visible', ?)", (want,))
        conn.commit()
        conn.close()
        stories_on(get_db, fresh=True)
        flash("Testimonials are now SHOWING on the website." if want == "1" else "Testimonials are now HIDDEN from the website.")
        return redirect(url_for(".testimonials_review"))

    @crm.route("/testimonials/request/<int:req_id>/delete", methods=["POST"])
    @leadership_required
    def testimonial_request_delete(req_id):
        _ensure(get_db)
        conn = get_db()
        conn.execute("DELETE FROM testimonials WHERE request_id = ?", (req_id,))
        conn.execute("DELETE FROM testimonial_requests WHERE id = ?", (req_id,))
        conn.commit()
        conn.close()
        if request.form.get("next") == "new":
            flash("Request cancelled. The link no longer works. You can start over with a new contact.")
            return redirect(url_for(".testimonial_request"))
        flash("Deleted. The link no longer works.")
        return redirect(url_for(".testimonials_review"))

    @crm.route("/testimonials/request", methods=["GET", "POST"])
    @leadership_required
    def testimonial_request():
        _ensure(get_db)
        conn = get_db()
        result = None
        if request.method == "POST":
            m = re.fullmatch(r"\d+", (request.form.get("contact_id") or "").strip())
            program = request.form.get("program") if request.form.get("program") in PROGRAM_LABEL else "GEN"
            note = (request.form.get("note") or "").strip()[:1000]
            include_links = bool(request.form.get("include_links"))
            home_url, stories_url = url_for("public_home", _external=True), url_for("public_stories", _external=True)
            ct = conn.execute(f"SELECT id, first_name, email, {full_name_sql()} AS full_name FROM contacts WHERE id = ?",
                              (int(m.group(0)),)).fetchone() if m else None
            if not ct:
                flash("Pick a contact from the list (start typing their name).")
            else:
                token = secrets.token_urlsafe(16)
                now = datetime.now().strftime("%Y-%m-%d %H:%M")
                conn.execute("""INSERT INTO testimonial_requests (token, contact_id, program_code, note, created_at)
                                VALUES (?, ?, ?, ?, ?)""", (token, ct["id"], program, note, now))
                conn.commit()
                req_row_id = conn.execute("SELECT id FROM testimonial_requests WHERE token = ?", (token,)).fetchone()["id"]
                link = url_for("public_share", token=token, _external=True)
                first = (ct["first_name"] or ct["full_name"] or "there").strip()
                what = PROGRAM_LABEL[program] if program != "GEN" else "the program"
                sms = (f"Hi {first}, it's Kent. We're inviting former trainees & volunteers to share how the program has touched "
                       f"their lives. We'd love to hear about your experience with the training. You can speak it, type it or record it "
                       f"here: {link}"
                       + (f"\n\n{note}" if note else "")
                       + ((f"\n\nNeed ideas? Take a look at our website: {home_url}\nSee what others have been saying: {stories_url}"
                           if stories_on(get_db) else f"\n\nTake a look at our website: {home_url}") if include_links else "")
                       + "\n\nYour story will not be published without your approval.")
                emailed, err = False, ""
                if request.form.get("action") == "email":
                    if not ct["email"]:
                        err = "This contact has no email address, so use the text message below instead."
                    else:
                        site_on = stories_on(get_db)
                        lp = letter_parts(include_links, site_on, home_url, stories_url)
                        parts = [f"<p>{_html.escape(lp['greeting'])} {_html.escape(first)},</p>"]
                        for kind, txt in lp["paras"]:
                            if kind == "button":
                                parts.append(f"<p style=\"margin:22px 0\"><a href=\"{link}\" style=\"background:#0c4561;color:#fff;padding:14px 28px;"
                                             f"border-radius:6px;text-decoration:none;display:inline-block;font-weight:bold\">Share your experience</a></p>")
                            else:
                                parts.append(f"<p>{txt}</p>")
                        if note:
                            parts.append(f"<p>{_note_html(note)}</p>")
                        parts.append(f"<p>{_html.escape(lp['signoff'])}<br>{_html.escape(lp['signer'])}</p>")
                        body = "".join(parts)
                        try:
                            send_email(to_email=ct["email"], to_name=ct["full_name"],
                                       subject=lp["subject"], html_content=body,
                                       bcc=DEFAULT_FROM_EMAIL)
                            emailed = True
                            conn.execute("UPDATE testimonial_requests SET sent_at = ?, sent_by = ? WHERE token = ?",
                                         (now, session.get("staff_name") or "", token))
                            conn.commit()
                        except Exception as e:
                            err = f"The email could not be sent ({e}). You can text the link below instead."
                result = dict(req_id=req_row_id, name=ct["full_name"], link=link, sms=sms, emailed=emailed, err=err)
        contacts = conn.execute(f"SELECT id, first_name, {full_name_sql()} AS full_name, email, cell_phone, home_phone FROM contacts ORDER BY last_name, first_name").fetchall()
        conn.close()
        # Pick-list text shows name and email (no database numbers). Duplicates get the phone, then a counter.
        seen, picks = {}, []
        for c in contacts:
            key = c["full_name"] + (" \u2014 " + c["email"] if c["email"] else "")
            if key in seen:
                key += " \u2014 " + (c["cell_phone"] or c["home_phone"] or "no phone")
            if key in seen:
                seen[key] += 1
                key += f" ({seen[key]})"
            else:
                seen[key] = 1
            picks.append(dict(key=key, id=c["id"], first=(c["first_name"] or c["full_name"] or "").strip(), email=c["email"] or "", phone=c["cell_phone"] or c["home_phone"] or ""))
        want = request.args.get("c", "")
        prefill = next((p_ for p_ in picks if str(p_["id"]) == want), None) if want.isdigit() else None
        return render_template("testimonial_request.html", picks=picks, programs=STORY_PROGRAMS, result=result, prefill=prefill, site_on=stories_on(get_db),
                               ltr=letter_parts(True, stories_on(get_db), url_for("public_home", _external=True), url_for("public_stories", _external=True)),
                               home_url=url_for("public_home", _external=True), stories_url=url_for("public_stories", _external=True))

    @crm.route("/testimonials/<int:tid>", methods=["GET", "POST"])
    @leadership_required
    def testimonial_detail(tid):
        _ensure(get_db)
        conn = get_db()
        t = conn.execute("""SELECT id, program_code, body, body_original, name_choice, display_name, attended, video_type,
                                   (video_data IS NOT NULL) AS has_video, status, featured, consent_at, created_at, contact_id,
                                   confirm_state, confirm_note, confirm_at,
                                   submitter_name, submitter_email, submitter_phone, referred_by
                            FROM testimonials WHERE id = ?""", (tid,)).fetchone()
        if not t:
            conn.close()
            abort(404)
        if request.method == "POST":
            action = request.form.get("action")
            if action == "delete":
                req = conn.execute("SELECT request_id FROM testimonials WHERE id = ?", (tid,)).fetchone()
                conn.execute("DELETE FROM testimonials WHERE id = ?", (tid,))
                if req and req["request_id"]:
                    conn.execute("DELETE FROM testimonial_requests WHERE id = ?", (req["request_id"],))
                conn.commit()
                conn.close()
                flash("Testimonial deleted.")
                return redirect(url_for(".testimonials_review"))
            program = request.form.get("program") if request.form.get("program") in PROGRAM_LABEL else t["program_code"]
            vf = request.files.get("video")
            if vf and vf.filename:
                vd = vf.read(MAX_VIDEO_BYTES + 1)
                if vd and len(vd) <= MAX_VIDEO_BYTES:
                    conn.execute("UPDATE testimonials SET video_data = ?, video_type = ?, confirm_state = NULL WHERE id = ?",
                                 (vd, (vf.mimetype or "video/mp4")[:60], tid))
                else:
                    flash("That video file is empty or larger than %d MB, so it was not replaced." % (MAX_VIDEO_BYTES // (1024 * 1024)))
            status = {"approve": "Approved", "hide": "Hidden", "new": "New"}.get(action, t["status"])
            send_back = action == "send_back"
            now = datetime.now().strftime("%Y-%m-%d %H:%M")
            conn.execute(
                """UPDATE testimonials SET body = ?, display_name = ?, attended = ?, program_code = ?, featured = ?, status = ?,
                          approved_at = CASE WHEN ? = 'Approved' THEN ? ELSE approved_at END WHERE id = ?""",
                ((request.form.get("body") or "").strip()[:8000], (request.form.get("display_name") or "").strip()[:80] or "Anonymous",
                 (request.form.get("attended") or "").strip()[:60], program, 1 if request.form.get("featured") else 0,
                 status, status, now, tid))
            msg = {"approve": "Approved and published on the Stories page.", "hide": "Hidden from the website."}.get(action, "Saved.")
            if send_back:
                ct = conn.execute(f"SELECT first_name, email, {full_name_sql()} AS full_name FROM contacts WHERE id = ?",
                                  (t["contact_id"],)).fetchone() if t["contact_id"] else None
                if not ct and t["submitter_email"]:
                    ct = {"first_name": (t["submitter_name"] or "").split(" ")[0], "email": t["submitter_email"],
                          "full_name": t["submitter_name"] or ""}
                if not ct or not ct["email"]:
                    msg = "Saved, but this contact has no email address, so it could not be sent back."
                else:
                    token = secrets.token_urlsafe(16)
                    conn.execute("UPDATE testimonials SET confirm_token = ?, confirm_state = 'sent', confirm_note = NULL, confirm_at = NULL WHERE id = ?",
                                 (token, tid))
                    conn.commit()
                    link = url_for("public_share_confirm", token=token, _external=True)
                    first = (ct["first_name"] or ct["full_name"] or "there").strip()
                    try:
                        send_email(to_email=ct["email"], to_name=ct["full_name"], subject="Please check your story before we share it", bcc=DEFAULT_FROM_EMAIL,
                                   html_content=(f"<p>Hi {_html.escape(first)},</p><p>Thank you for sharing your experience. We made a few "
                                                 f"small edits for length and clarity. Before anything is published, please look at it and "
                                                 f"tell us it is right, or ask for changes.</p>"
                                                 f"<p><a href=\"{link}\" style=\"background:#0c4561;color:#fff;padding:12px 22px;"
                                                 f"border-radius:6px;text-decoration:none;display:inline-block\">Review my story</a></p>"
                                                 f"<p>Nothing goes on the website until you say yes.</p><p>Thank you,<br>Kent</p>"))
                        msg = "Saved and sent back to " + ct["full_name"] + " for their approval."
                    except Exception as e:
                        msg = f"Saved, but the email could not be sent ({e})."
            conn.commit()
            conn.close()
            flash(msg)
            return redirect(url_for(".testimonial_detail", tid=tid))
        conn.close()
        return render_template("testimonial_detail.html", t=t, programs=STORY_PROGRAMS, flags=flagged_words(t["body"]))

    @crm.route("/testimonials/<int:tid>/video")
    @leadership_required
    def testimonial_video(tid):
        _ensure(get_db)
        conn = get_db()
        row = conn.execute("SELECT video_data, video_type FROM testimonials WHERE id = ?", (tid,)).fetchone()
        conn.close()
        if not row or row["video_data"] is None:
            abort(404)
        ext = "webm" if "webm" in (row["video_type"] or "") else "mp4"
        dl = bool(request.args.get("dl"))
        return send_file(io.BytesIO(bytes(row["video_data"])), mimetype=row["video_type"] or "video/mp4", conditional=True,
                         as_attachment=dl, download_name=f"testimonial_{tid}.{ext}")
