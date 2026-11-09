"""Correspondence: one place for every letter.

  Trainee Correspondence       pick a session; the trainee letters for that session (the existing session letters).
  Team Correspondence          pick a session; the facilitator / TA letters; plus a note to Facilitators, TA's,
                               Support Team or Leadership.
  Accounting & Legal           a note to the Accounting & Legal logins.
  Marketing & Email Blasts     the existing page (/email-blasts), unchanged.

Notes (Team and Accounting & Legal) go out one email per person, from a preview/test first, and only when
SESSION_LETTERS_LIVE=1 is set. Nothing here touches the Marketing safeguards.
"""
import html as _html
import os
import re

from markupsafe import Markup, escape
from flask import abort, flash, redirect, render_template, request, session, url_for

import string

import email_templates as et
from email_utils import send_email, EmailSendError

# key -> (page title, who it goes to, picks people by session?)
GROUPS = {
    "facilitators": ("Facilitators", "Lead and Support Facilitators", True),
    "tas": ("TA's", "TA's and Back-up TA's", True),
    "support": ("Support Team", "Support Team", True),
    "leadership": ("Leadership", "Leadership and Owner logins", False),
    "accounting": ("Accounting & Legal", "Accounting & Legal logins", False),
}
TEAM_GROUPS = ["facilitators", "tas", "support", "leadership"]

_ready = False


def live():
    return (os.environ.get("SESSION_LETTERS_LIVE") or "").strip() == "1"


def switches():
    """The six safety switches, as (name, is_on, what it controls). Status only: they are changed in Render's Environment."""
    on = lambda n: (os.environ.get(n) or "").strip() == "1"
    return [
        ("SESSION_LETTERS_LIVE", on("SESSION_LETTERS_LIVE"), "Master switch: letters to trainees and the team (sent by hand or automatically). Off means nothing is sent."),
        ("AUTO_LETTERS_LIVE", on("AUTO_LETTERS_LIVE"), "Automatic letters: confirmation after reserving, \u201cThank you \u2013 We\u2019re so excited\u201d, and What to bring. Also needs the master switch."),
        ("CALL_ALERTS_LIVE", on("CALL_ALERTS_LIVE"), "Guide alerts, Guide-page emails, the 7-day payment nudges, and the reply to \u201cI\u2019m curious\u201d."),
        ("SPONSOR_LIVE", on("SPONSOR_LIVE"), "Sponsor letters: the Sponsor welcome letter and the help alert. Also needs the Guide alerts switch (CALL_ALERTS_LIVE)."),
        ("PUBLIC_REPLIES_LIVE", on("PUBLIC_REPLIES_LIVE"), "Automatic replies when someone uses a public website form: profile link, welcome letter, thank-you letter, \u201creach out to me\u201d confirmation, and the plan email."),
        ("BLASTS_LIVE", on("BLASTS_LIVE"), "Marketing & Email Blasts (excitement letters, volunteer and Guide emails)."),
    ]


def ensure_tables(get_db):
    global _ready
    if _ready:
        return
    conn = get_db()
    try:
        conn.execute("""CREATE TABLE IF NOT EXISTS team_notes (
            id SERIAL PRIMARY KEY,
            group_key TEXT NOT NULL,
            cohort_id INTEGER,
            subject TEXT,
            body TEXT,
            sent_by TEXT,
            sent_count INTEGER NOT NULL DEFAULT 0,
            skipped TEXT,
            sent_at TEXT NOT NULL DEFAULT to_char(now(), 'YYYY-MM-DD HH24:MI:SS'))""")
        conn.execute("""CREATE TABLE IF NOT EXISTS letter_suggestions (
            id SERIAL PRIMARY KEY,
            letter_name TEXT,
            name TEXT,
            email TEXT,
            message TEXT,
            source TEXT,
            status TEXT NOT NULL DEFAULT 'New',
            created_at TEXT NOT NULL DEFAULT to_char(now(), 'YYYY-MM-DD HH24:MI:SS'),
            handled_by TEXT,
            handled_at TEXT)""")
        conn.commit()
        _ready = True
    finally:
        conn.close()


def note_recipients(conn, group, cohort_id=None):
    """[(contact_id or None, first_name, name, email)] one per address. Unsubscribed contacts are left out."""
    roles = {"facilitators": ("Lead Facilitator", "Support Facilitator"),
             "tas": ("TA", "Back-up TA"), "support": ("Support Team",)}
    rows = []
    if group in roles:
        ph = ",".join("?" for _ in roles[group])
        sql = (f"SELECT DISTINCT ct.id, ct.first_name, ct.last_name, ct.email FROM cohort_staffing cs "
               f"JOIN contacts ct ON ct.id = cs.contact_id WHERE cs.role IN ({ph}) "
               f"AND ct.email IS NOT NULL AND ct.email <> '' AND COALESCE(ct.do_not_email, 0) = 0")
        args = list(roles[group])
        if cohort_id:
            sql += " AND cs.cohort_id = ?"
            args.append(cohort_id)
        for r in conn.execute(sql + " ORDER BY ct.last_name, ct.first_name", tuple(args)).fetchall():
            rows.append((r["id"], r["first_name"] or "", f"{r['first_name'] or ''} {r['last_name'] or ''}".strip(), r["email"]))
    elif group == "leadership":
        for r in conn.execute("SELECT id, name, email FROM staff WHERE active = 1 AND (role = 'Leadership' OR is_owner = 1) ORDER BY name").fetchall():
            rows.append((None, (r["name"] or "").split()[0] if r["name"] else "", r["name"], r["email"]))
    elif group == "accounting":
        for r in conn.execute("SELECT id, name, email FROM staff WHERE active = 1 AND role = 'Accounting' ORDER BY name").fetchall():
            rows.append((None, (r["name"] or "").split()[0] if r["name"] else "", r["name"], r["email"]))
    seen, out = set(), []
    for cid, first, name, email in rows:
        e = (email or "").strip()
        k = e.lower()
        if "@" not in e or k in seen:
            continue
        seen.add(k)
        out.append((cid, first, name, e))
    return out


def build_note(subject, body, first, sender, session_label=None):
    """(html, text) for one person. The body is plain paragraphs; [First name] becomes the person's first name."""
    greet = (first or "").strip() or "Friend"
    text_body = re.sub(r"(?i)\[\s*first\s*name\s*\]|\{\s*first\s*name\s*\}", greet, body or "").replace("\r\n", "\n").strip()
    paras = [p for p in text_body.split("\n\n") if p.strip()]
    parts = []
    for p in paras:
        esc = _html.escape(p.strip()).replace("\n", "<br>")
        esc = re.sub(r'(?<!["\'>=])(https?://[^\s<]+)', r'<a href="\1">\1</a>', esc)
        esc = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", esc)
        parts.append(f"<p>{esc}</p>")
    sig = f"<p>{_html.escape(sender)}</p>" if sender else ""
    html = ('<div style="font-family:Arial,Helvetica,sans-serif;font-size:15px;line-height:1.55;color:#222">'
            f"{''.join(parts)}{sig}</div>")
    return html, text_body + (f"\n\n{sender}" if sender else "")


def sessions_with_counts(conn):
    return conn.execute(
        """SELECT co.*, p.code, p.name AS program_name,
                  (SELECT COUNT(*) FROM enrollments e WHERE e.cohort_id = co.id) AS n_trainees,
                  (SELECT COUNT(DISTINCT cs.contact_id) FROM cohort_staffing cs WHERE cs.cohort_id = co.id
                      AND cs.role IN ('Lead Facilitator','Support Facilitator','TA','Back-up TA','Support Team')) AS n_team,
                  (SELECT COUNT(*) FROM session_letters_sent s WHERE s.cohort_id = co.id) AS n_sent
           FROM cohorts co JOIN programs p ON p.id = co.program_id
           ORDER BY co.session_date DESC""").fetchall()


# ---------------------------------------------------------------- the catalog of every letter the program sends
# kind: "edit" (wording can be edited here), "view" (shown read-only; wording is in the program code), "code" (no preview),
# "link" (managed on another page). Each entry: name, when it is sent, who gets it.
def _prev(fn):
    return fn


def _preview_map():
    import email_templates as T
    import call_flow as C
    P = "[First name]"
    return {
        "venue": lambda: (lambda r: (r[0], r[1]))(C.letter_venue(P, "[partner's name]", "[Guide name]", "[Guide phone]")),
        "welcome": lambda: (T.INTERESTED_PARTY_WELCOME_SUBJECT, T.interested_party_welcome_content(P)[0]),
        "longform_followup": lambda: (T.LONGFORM_FOLLOWUP_SUBJECT, T.longform_followup_content(P, "#")[0]),
        "longform_thankyou": lambda: (T.LONGFORM_THANKYOU_SUBJECT, T.longform_thankyou_content(P, "#", "#")[0]),
        "connect": lambda: (T.CONNECT_REQUEST_SUBJECT, T.connect_request_confirmation_content(P, "call")[0]),
        "plan": lambda: (T.PRELIMINARY_PLAN_SUBJECT, T.preliminary_plan_content(P)[0]),
        "excitement": lambda: (T.EXCITEMENT_BLAST_SUBJECT, T.excitement_blast_content(P)[0]),
        "contract": lambda: (T.CONTRACT_REQUEST_SUBJECT, T.contract_request_content(P, "#")[0]),
        "completion": lambda: (lambda r: (r[0], r[1]))(T.completion_letter_content(P, "#", "D4", "The Art of Us")),
        "helper_welcome": lambda: (lambda r: (r[0], r[1]))(C.letter_helper_welcome(P, "#", "#")),
    }


# Plain-language note shown where the Guide letters appear, because most people don't know what a Guide is.
GUIDE_EXPLAINER = (
    "A Guide is a volunteer with a very important role. A Guide is a volunteer selected by leadership who is responsible for responding to the \u201cI\u2019m Curious to know more\u201d short form on the public website. "
    "If a Guide responds to this inquiry, the Guide becomes that person's personal contact for Discovery!, from their first question all the way into the training room. "
    "In short, a Guide is a salesperson who helps fill the seats. In years past only staff took on this job. We think it makes sense to invite qualified volunteers to help. "
    "Our goal is to select 12 volunteers to do this job: 6 for The Art of Us program, and 6 for The Beginning program.",
    "## How it works",
    "When someone fills out an \"I'm curious\" form, and let's say they are interested in The Art of Us, an alert is sent to all 6 of the Guides for that program. "
    "The first Guide to respond to the request is assigned to that contact, and a letter goes out right away to tell the person who their Guide is and that the Guide will be in touch. "
    "(If a person selects \"Not sure\" about which program, or if they ask about Awakening, Vision, Refocus, or Spiritual, the \"Everything else\" group is alerted.)",
    "From then on the same Guide is a salesperson, coach and counselor bundled together, and takes on the responsibility from cradle to grave to answer questions and guide that person into the training room. "
    "A Guide must be gifted, with breadth and depth in communication skill.",
    "When a Guide accepts the \"I'm curious\" request, that Guide is sent a link of their own with an alert that carries the name of the client so the Guide knows right away who it is about. "
    "The link opens an easy to use web page dedicated to that one client, which, by simply pressing buttons, makes it simple for the Guide to send pre-written correspondence to the contact. "
    "For example, when the client is ready to register, the Guide will press the button to send the registration link. After the client registers, the Guide is notified to send the questionnaire link, payment request link, and so on. "
    "If the client delays payment, the Guide will be automatically notified every seven days that payment is delayed, and at the Guide's discretion, a payment reminder may be sent. "
    "Once payment is made, a \"Thank you \u2013 We're so excited\" letter is automatically sent, followed by a \"What to bring\" letter seven days before the training begins.",
    "A dropdown menu gives the Guide options to tell us how the initial conversation went (spoke with them, left a voicemail, texted and waiting for a reply, no answer and will try again, not interested, or wrong number). "
    "The Guide may dictate a note about what the person is hoping for, their questions and the next step. This information is stored on the \u201cCall Requests\u201d page under the Admin menu.",
    "Before the trainee shows up at the door, the Guide makes sure the contact information is complete, including a photo, the questionnaire is complete, and payment has been received.",
)



def guides_by_group(conn):
    """Names of the active Guides, grouped the way the Guide team is organised. Empty if nothing is set up yet."""
    try:
        import call_flow as CF
        rows = conn.execute("SELECT program_code, name FROM call_volunteers WHERE active = 1 ORDER BY id").fetchall()
        out = []
        for code, label in CF.POOLS:
            names = [r["name"] for r in rows if r["program_code"] == code]
            if names:
                out.append((label, names))
        return out
    except Exception:
        try:
            conn.rollback()
        except Exception:
            pass
        return []


def delivery_of(when):
    """"Automated", "By hand" or "Automated and by hand", read from the 'when it is sent' text."""
    w = (when or "").lower()
    auto = "automatic" in w
    hand = ("by hand" in w) or ("by you" in w) or ("when you choose" in w) or ("written by you" in w)
    if auto and hand:
        return "Automated and by hand"
    return "Automated" if auto else "By hand"


def catalog():
    import email_templates as T
    sl = T.SESSION_LETTERS
    E = lambda key, name, when, who, sub="": dict(kind="edit", key=key, name=name, when=when, who=who, sub=sub)
    V = lambda slug, name, when, who, sub="": dict(kind="view", slug=slug, name=name, when=when, who=who, sub=sub)
    C = lambda name, when, who, note="", sub="", text=None: dict(kind="code", name=name, when=when, who=who, note=note, sub=sub, text=text)
    X = lambda name, when, who, url: dict(kind="ext", name=name, when=when, who=who, url=url)
    cats = [
        ("interested", "Interested people (before they register)",
         "What someone receives after they ask a question, ask to be called, or fill in a form on the website.", [
            V("welcome", "Welcome", "Automatically, when someone fills in the Discovery! form as an interested party.", "Interested parties"),
            V("longform_followup", "Profile follow-up", "Automatically, when someone fills in the Discovery! form and checks Volunteer.", "Past volunteers"),
            V("longform_thankyou", "Profile thank-you", "Automatically, when someone finishes their profile.", "People who completed the profile"),
            V("connect", "Connect-request confirmation", "Automatically, when someone asks us to reach out from their private link.", "People who asked to connect"),
            V("excitement", "Excitement email", "By hand, from a contact's record.", "Contacts"),
            V("plan", "Preliminary business plan", "When someone requests it, or by hand from their record.", "Interested parties"),
            V("venue", "Where we'll be and what's included", "By hand, from the Guide's page or a contact's record.", "Registered couples, or anyone asking about the venue"),
         ]),
        ("contacts", "Contacts (anyone in the Hub)",
         "Messages you send to any contact from their record.", [
            E("profile_request", "Profile update request (email, text and the profile page)", "By hand, from a contact's record: the Email request and Text request buttons. The same wording opens the contact's profile page.", "Any contact"),
            E("testimonial_request", "Testimonial request (email)", "By hand, from Testimonials \u2192 Request a testimonial: \"Send it by email now\". Your personal note goes just above the closing. The Hub keeps a record on the contact.", "Former trainees and volunteers"),
            E("needs_request", "Food and physical needs request (session team)", "By hand, from a session page: the \"Email the team members who haven't answered\" button. The Hub sends it and keeps a record.", "Team members on a session"),
            E("video_call", "Video call link (Google Meet)", "By hand, from a contact's record: \"Email the link\". The Hub sends it and keeps a record.", "Any contact"),
         ]),
        ("trainees", "Trainee Correspondence",
         "Letters and questionnaires for the people registered for a session. Each session's page shows who has received each letter. The questionnaires are the forms trainees fill in on their private link; their questions are fixed in the program code for now, and making them editable per program is the next piece.", [
            E("seminar_registration", sl["seminar_registration"]["title"] + " \u2013 The Art of Us", "By hand from the session's letters page.", "Trainees (The Art of Us)"),
            E("seminar_registration_other", sl["seminar_registration_other"]["title"], "By hand from the session's letters page.", "Trainees (The Beginning and every other training)"),
            E("trainee_confirm", sl["trainee_confirm"]["title"] + " \u2013 The Art of Us", "By hand from the session's letters page; also automatically to people who reserve through a Guide's link.", "Trainees (The Art of Us)"),
            E("trainee_confirm_other", sl["trainee_confirm_other"]["title"], "By hand from the session's letters page; also automatically to people who reserve through a Guide's link.", "Trainees (The Beginning and every other training)"),
            E("payment_reminder", sl["payment_reminder"]["title"] + " \u2013 The Art of Us", "By hand only. The Guide is nudged every 7 days while payment is late and decides whether to send a reminder.", "Trainees who have not paid (The Art of Us)"),
            E("payment_reminder_other", sl["payment_reminder_other"]["title"], "By hand only. The Guide is nudged every 7 days while payment is late and decides whether to send a reminder.", "Trainees who have not paid (The Beginning and every other training)"),
            E("payment_received", sl["payment_received"]["title"] + " \u2013 The Art of Us", "Automatically when payment is recorded (for people who reserved through a Guide); also by hand from the session's letters page.", "Trainees who have paid (The Art of Us)"),
            E("payment_received_other", sl["payment_received_other"]["title"], "Automatically when payment is recorded (for people who reserved through a Guide); also by hand from the session's letters page.", "Trainees who have paid (The Beginning and every other training)"),
            E("questionnaire_request", sl["questionnaire_request"]["title"] + " \u2013 The Art of Us", "By hand from the session's letters page.", "Trainees without a completed questionnaire (The Art of Us)"),
            E("questionnaire_request_other", sl["questionnaire_request_other"]["title"], "By hand from the session's letters page.", "Trainees without a completed questionnaire (The Beginning and every other training)"),
            E("questionnaire_reminder", sl["questionnaire_reminder"]["title"] + " \u2013 The Art of Us", "By hand from the session's letters page.", "Trainees without a completed questionnaire (The Art of Us)"),
            E("questionnaire_reminder_other", sl["questionnaire_reminder_other"]["title"], "By hand from the session's letters page.", "Trainees without a completed questionnaire (The Beginning and every other training)"),
            X("Questionnaire: The Art of Us (Relationship Training)", "Sent as a private link by the Guide's \"Email it\" or from the session page.", "Each partner of a couple, separately", "/cep-letters/q-rt"),
            X("Questionnaire: The Beginning", "Sent as a private link from the session page.", "Each person, separately. The Beginning's own questions are still to be written (shown as TBD).", "/cep-letters/q-d1"),
            C("Questionnaire: other programs", "Sent as a private link from the session page.", "Each person", "Awakening, Vision, Renew and Spiritual use a short standard set: first time attending, goals, food and access needs, injuries, anything else."),
            E("what_to_bring_aou", sl["what_to_bring_aou"]["title"], "Automatically 7 days before The Art of Us for people who have paid (reserved through a Guide); also by hand from the session's letters page.", "Trainees (The Art of Us)"),
            E("what_to_bring", "What to Bring \u2013 Other Trainings", "Automatically 7 days before the training for people who have paid (reserved through a Guide); also by hand.", "Trainees (The Beginning and every other training)"),
            V("completion", "After the training", "Automatically, a short time after the training ends.", "Trainees who completed"),
            V("contract", "Contract information request", "By hand, from a contact's record.", "Trainees who completed"),
         ]),
        ("team", "Team (Facilitators, TA's, Support Team, Leadership)",
         "Letters to the people who run a session.", [
            E("facilitator_confirm", sl["facilitator_confirm"]["title"], "By hand from the session's letters page.", "Facilitators"),
            E("ta_invitation", sl["ta_invitation"]["title"], "By hand from the session's letters page, to the people chosen as TAs. The button opens a private page where they answer Yes or No.", "People chosen as a TA"),
            E("ta_confirm", sl["ta_confirm"]["title"], "By hand from the session's letters page.", "TA's"),
            E("backup_confirm", sl["backup_confirm"]["title"], "By hand from the session's letters page.", "Back-up TA's"),
            dict(kind="link", name="Team notes", when="Written by you each time, to Facilitators, TA's, Support Team or Leadership.",
                 who="The group you choose", url="correspondence_team", label="Team Correspondence"),
            C("Welcome to a new login", "Automatically, when a login is created or a password is reset.", "New team members"),
         ]),
        ("guides", "Volunteers", "What the people who make the calls receive.", [
            E("guide_curious", "Reply to \"I'm curious\"", "Automatically, as soon as a Guide takes a call request.", "People who ask to be called", sub="Guides"),
            E("guide_register", "Registration link", "When the Guide taps \"Email it\" in the Ready to register box.", "People a Guide has talked with", sub="Guides"),
            E("guide_questionnaire", "Questionnaire link", "When the Guide taps \"Email it\" in the Send the questionnaire box.", "People who have reserved", sub="Guides"),
            E("guide_longform", "Complete your profile", "When the Guide taps \"Email it\" under Next step, after the person has reserved.", "People who have reserved", sub="Guides"),
            E("guide_payment", "Payment request", "When the Guide taps \"Email it\" for the payment request.", "People who have reserved", sub="Guides"),
            E("guide_payment_reminder", "Payment reminder (from the Guide)", "When the Guide chooses to remind someone who has not paid (the Guide is prompted every 7 days).", "People who have reserved but not paid", sub="Guides"),
            C("New call request", "Automatically, when someone asks to be called.", "The Guides for that program", sub="Guides", text=[
                ("Email", "Subject: Please reach out to [Name] within 2 hours \u2013 [Program]\n\nHi [Guide first name],\n\n[Name] asked to be reached about [Program]. They prefer: [Call or text].\n\nCan you [call or text] them within two hours? Tap here to say yes:\n[the Guide\u2019s personal link]\n\nIf another volunteer already took it, the page will tell you. Thank you for helping!"),
                ("Phone alert", "[Name] wants to hear from us\nCan you [call or text] [Name] within 2 hours? Tap to say yes. ([Program])"),
                ("Second round, 2 hours later", "Same email, with \u201c(second reminder: no one has claimed this yet)\u201d added after the program name."),
            ]),
            C("Unclaimed request and call reminders", "Automatically, if nobody claims a request in 2 hours, and to remind a Guide to log a call.", "Guides, and you", sub="Guides", text=[
                ("To you and the Guide Team Captain: unclaimed request", "Subject: Unclaimed call request: [Name] ([Program])\n\nNobody has claimed this request in 2 hours; the volunteers were alerted again.\n(Or: No volunteers are set up for this program. / No volunteer could be emailed.)\n\nOpen Call requests in the CRM to follow up: [link]"),
                ("To the Guide: please log your call (2 hours after taking a request)", "Subject: Please log your call\n\nHi [Guide first name],\n\nYou took a call request a couple of hours ago. When you\u2019ve called, please log how it went here:\n[the Guide\u2019s personal link]\n\nThank you!"),
            ]),
            C("Milestone emails", "Automatically, as a Guide reaches milestones.", "Guides", sub="Guides", text=[
                ("When the person registers", "Subject: [First name] has registered!\n\nHi [Guide first name],\n\nGood news: [Name] registered for [Program, dates], thanks to your conversation. Please open your page for them to send the questionnaire link and the payment request: [link] Payment is still pending. We will let you know when it comes in.\n\nWarmly,\nThe Discovery! Team"),
                ("When the person pays", "Subject: [First name] has registered and paid!\n\nHi [Guide first name],\n\n[Name] has paid for [Program, dates]. Their spot is secure. Thank you for helping them take this step!\n\nWarmly,\nThe Discovery! Team"),
                ("Every 7 days while payment is late", "Subject: [First name] has not paid yet\n\nHi [Guide first name],\n\n[First name] reserved a seat but payment has not arrived. A friendly reminder may help, and it is your call. Open your page for them and tap the payment reminder: [link]\n\nWarmly,\nThe Discovery! Team"),
            ]),
         
            dict(kind="page", name="Sponsor a Friend (the public form page)", when="A volunteer opens it from the public website to start sponsoring someone.", who="Volunteers who sponsor someone", url="/sponsor", label="View page", sub="Sponsors"),
            E("sponsor_welcome", "Sponsor welcome (complete your profile)", "Sent automatically when a volunteer submits the Sponsor form.", "Volunteers who sponsor someone", sub="Sponsors"),
            E("sponsor_page", "Sponsor thank-you and page (contact form complete)", "Automatically, once the Sponsor\u2019s contact form is complete (required items and a photo).", "Volunteers who sponsor someone", sub="Sponsors"),
            V("helper_welcome", "Volunteer welcome", "Automatically, when a volunteer joins the helper team.", "New volunteers", sub="Other Volunteers"),
         ]),
        ("testimonials", "Testimonials", "Inviting and checking what people say about the program.", [
            C("Share your Discovery! experience", "By hand, from the Testimonials page.", "Past trainees"),
            C("A new testimonial is ready to review", "Automatically, when a testimonial comes in.", "Leadership"),
            C("Please check your story before we share it", "By hand, once a story is ready.", "People who sent a testimonial"),
         ]),
        ("marketing", "Marketing & Email Blasts", "Announcements to your wider community, with the test, SEND and unsubscribe safeguards.", [
            dict(kind="link", name="Marketing & Email Blasts", when="By you, when you choose.", who="The audience you choose",
                 url="email_blasts", label="Open Marketing & Email Blasts", owner=True),
         ]),
        ("internal", "Internal (to you and Accounting & Legal)", "Notes that stay inside the organization.", [
            C("Budget emails and change requests", "By hand, from a budget page.", "The people named on that budget"),
            dict(kind="link", name="Accounting & Legal notes", when="Written by you each time.", who="Accounting & Legal logins",
                 url="correspondence_note", label="Write a note", owner=True, group="accounting"),
         ]),
    ]
    for _id, _t, _d, entries in cats:
        for e in entries:
            e.setdefault("sub", "")
            e["delivery"] = delivery_of(e.get("when"))
    return cats


SUGGEST_MAX = 2000
SUGGEST_DAILY_CAP = 30


def save_suggestion(get_db, letter_name, name, email, message, source):
    """Store a suggested change and tell the Owner by email (best effort). Returns (ok, error_text)."""
    ensure_tables(get_db)
    letter_name = (letter_name or "").strip()[:200]
    name = (name or "").strip()[:120]
    email = (email or "").strip()[:200]
    message = (message or "").strip()[:SUGGEST_MAX]
    if not name:
        return False, "Please tell us your name so we know who to thank."
    if len(message) < 5:
        return False, "Please type your suggestion."
    conn = get_db()
    try:
        today = conn.execute("SELECT COUNT(*) AS n FROM letter_suggestions WHERE created_at >= to_char(now() - interval '1 day', 'YYYY-MM-DD HH24:MI:SS')").fetchone()["n"]
        if today >= SUGGEST_DAILY_CAP:
            return False, "We have received a lot of suggestions today. Please try again tomorrow."
        conn.execute("INSERT INTO letter_suggestions (letter_name, name, email, message, source) VALUES (?, ?, ?, ?, ?)",
                     (letter_name, name, email or None, message, source))
        conn.commit()
    finally:
        conn.close()
    try:
        to = (os.environ.get("EMAIL_FROM_ADDRESS") or "kent@blueskyusa.net").strip()
        body = (f"{name}{' (' + email + ')' if email else ''} suggested a change to: {letter_name or 'a letter'}\n\n{message}\n\n"
                "You can see and mark off suggestions under Correspondence > All Letters.")
        send_email(to_email=to, subject=f"Suggested letter change: {letter_name or 'a letter'}",
                   html_content="<p>" + _html.escape(body).replace("\n\n", "</p><p>").replace("\n", "<br>") + "</p>", text_content=body)
    except Exception as e:
        print(f"Couldn't email the letter suggestion: {e}", flush=True)
    return True, None


def register(app, crm, get_db, h):
    """h: dict of helpers from app.py: leadership_required, correspondence_access, area_required, staff_email,
    ensure_letters_table, program_label (code -> display name)."""
    leadership_required = h["leadership_required"]
    correspondence_access = h["correspondence_access"]

    def _staff_name():
        return session.get("staff_name") or ""

    def _is_leader():
        return bool(session.get("is_owner")) or session.get("staff_role") == "Leadership"

    @crm.route("/correspondence/suggest", methods=["POST"])
    def correspondence_suggest():
        ok, err = save_suggestion(get_db, request.form.get("letter_name"), _staff_name() or request.form.get("name"),
                                  h["staff_email"](), request.form.get("message"), "Correspondence page")
        flash("Thank you. Your suggestion was sent to the Owner." if ok else err)
        return redirect(url_for(".correspondence_all") + "#suggest")

    @crm.route("/correspondence/suggestions/<int:sid>/done", methods=["POST"])
    def correspondence_suggestion_done(sid):
        if not session.get("is_owner"):
            flash("Only the Owner can do that.")
            return redirect(url_for(".dashboard"))
        ensure_tables(get_db)
        conn = get_db()
        try:
            conn.execute("UPDATE letter_suggestions SET status = ?, handled_by = ?, handled_at = to_char(now(), 'YYYY-MM-DD HH24:MI:SS') WHERE id = ?",
                         ("New" if request.form.get("action") == "reopen" else "Handled", _staff_name(), sid))
            conn.commit()
        finally:
            conn.close()
        return redirect(url_for(".correspondence_all") + "#suggestions")

    @app.route("/cep-letters/suggest", methods=["POST"])
    def public_letter_suggest():
        """Guides and volunteers (no login) can suggest a change to a letter. Only the Owner changes letters."""
        back = request.form.get("back") or url_for("public_cep_letters")
        if not back.startswith("/"):
            back = url_for("public_cep_letters")
        if request.form.get("website"):          # a hidden field only a robot fills in
            return redirect(back)
        ok, err = save_suggestion(get_db, request.form.get("letter_name"), request.form.get("name"),
                                  request.form.get("email"), request.form.get("message"), "Guide letters page")
        flash("Thank you. Your suggestion was sent to the Owner." if ok else err)
        return redirect(back + "#suggest")

    @crm.route("/correspondence/go-live")
    @leadership_required
    def correspondence_golive():
        return render_template("correspondence_golive.html", live=live(), switches=switches())

    @crm.route("/correspondence/all-letters")
    def correspondence_all():
        ensure_tables(get_db)
        conn = get_db()
        try:
            h["ensure_letters_table"](conn)
            edits = {r["letter_key"]: r for r in conn.execute("SELECT letter_key, updated_by, updated_at FROM session_letter_text").fetchall()}
            nvers = {r["letter_key"]: r["n"] for r in conn.execute("SELECT letter_key, COUNT(*) AS n FROM letter_versions GROUP BY letter_key").fetchall()}
            sent = {r["letter_key"]: r["n"] for r in conn.execute("SELECT letter_key, COUNT(*) AS n FROM session_letters_sent GROUP BY letter_key").fetchall()}
            ensure_tables(get_db)
            is_owner = bool(session.get("is_owner"))
            sugg_new, sugg_done = [], []
            if is_owner:
                sugg_new = conn.execute("SELECT * FROM letter_suggestions WHERE status = 'New' ORDER BY id DESC").fetchall()
                sugg_done = conn.execute("SELECT * FROM letter_suggestions WHERE status <> 'New' ORDER BY id DESC LIMIT 30").fetchall()
            letter_names = [e["name"] for _i, _t, _d, es in catalog() for e in es if e.get("kind") in ("edit", "view", "code", "ext", "page")]
            return render_template("correspondence_all.html", is_owner=is_owner, sugg_new=sugg_new, sugg_done=sugg_done,
                                   letter_names=letter_names, cats=catalog(), guide_note=GUIDE_EXPLAINER, guides=guides_by_group(conn), edits=edits, nvers=nvers, sent=sent,
                                   can_marketing=h["has_correspondence_access"](), live=live(), switches=switches())
        finally:
            conn.close()

    @crm.route("/correspondence/search")
    def correspondence_search():
        """Search the current wording of every letter. Everyone with a login may read, so everyone may search."""
        q = (request.args.get("q") or "").strip()
        results, checked = [], 0
        if q:
            import html as _html
            ql = q.lower()
            conn = get_db()
            try:
                h["ensure_letters_table"](conn)
                saved = {r["letter_key"]: r for r in conn.execute("SELECT * FROM session_letter_text").fetchall()}
            finally:
                conn.close()
            can_mkt = h["has_correspondence_access"]()

            def plain(t):
                t = re.sub(r"<(br|/p|/li|/h\d|/div|/tr)\s*/?>", "\n", t or "", flags=re.I)
                t = re.sub(r"<[^>]+>", " ", t)
                return re.sub(r"[ \t]+", " ", _html.unescape(t)).strip()

            for _cid, ctitle, _intro, entries in catalog():
                for e in entries:
                    if e.get("owner") and not can_mkt:
                        continue
                    kind, text, link = e.get("kind"), "", None
                    try:
                        if kind == "edit" and e["key"] in et.ALL_LETTERS:
                            sv = saved.get(e["key"])
                            if sv:
                                text = " \n".join([sv["subject"] or "", sv["body"] or "", sv["signoff"] or ""])
                            else:
                                o = et.ALL_LETTERS[e["key"]]
                                text = " \n".join([o.get("subject", ""), et.original_body(e["key"]), o.get("signoff", "")])
                            link = url_for(".correspondence_letter_edit", key=e["key"], view=1)
                        elif kind == "view":
                            fn = _preview_map().get(e["slug"])
                            if fn:
                                subj, body = fn()
                                text = (subj or "") + " \n" + plain(body)
                            link = url_for(".correspondence_letter_view", slug=e["slug"])
                        elif kind == "code":
                            text = (e.get("text") or "") + " " + (e.get("note") or "")
                    except Exception:
                        continue
                    if not text.strip():
                        continue
                    checked += 1
                    text = plain(text) if "<" in text else text
                    low, hits, start = text.lower(), [], 0
                    n = low.count(ql)
                    if not n:
                        continue
                    while len(hits) < 4:
                        i = low.find(ql, start)
                        if i < 0:
                            break
                        a, b = max(0, i - 70), min(len(text), i + len(q) + 70)
                        seg = ("\u2026" if a else "") + text[a:b].replace("\n", " ") + ("\u2026" if b < len(text) else "")
                        seg = str(escape(seg))
                        seg = re.sub(re.escape(str(escape(q))), lambda m: "<mark>" + m.group(0) + "</mark>", seg, flags=re.I)
                        hits.append(Markup(seg))
                        start = i + len(q)
                    results.append(dict(name=e["name"], category=ctitle, link=link, count=n, hits=hits))
        return render_template("correspondence_search.html", q=q, results=results, checked=checked)

    @crm.route("/correspondence/letters/view/<slug>")
    def correspondence_letter_view(slug):
        fn = _preview_map().get(slug)
        if not fn:
            abort(404)
        entry = next((e for _i, _t, _d, es in catalog() for e in es if e.get("slug") == slug), {})
        name = entry.get("name", slug)
        try:
            subject, html = fn()
        except Exception:
            subject, html = None, None
        return render_template("correspondence_letter_view.html", name=name, subject=subject, letter_html=html, delivery=entry.get("delivery"), when=entry.get("when"),
                               short_note=(slug in ("welcome", "longform_followup")),
                               long_note=(slug in ("longform_followup", "longform_thankyou")))

    @crm.route("/correspondence")
    @leadership_required
    def correspondence_home():
        return render_template("correspondence_home.html", groups=GROUPS, team_groups=TEAM_GROUPS,
                               can_marketing=h["has_correspondence_access"]())

    def _sessions_page(kind):
        ensure_tables(get_db)
        conn = get_db()
        try:
            h["ensure_letters_table"](conn)
            sessions = sessions_with_counts(conn)
            counts = {}
            for r in conn.execute("SELECT cohort_id, SUBSTR(sent_at, 1, 4) AS yr, COUNT(*) AS n FROM session_letters_sent "
                                  "GROUP BY cohort_id, SUBSTR(sent_at, 1, 4)").fetchall():
                counts.setdefault(r["cohort_id"], {})[r["yr"]] = r["n"]
            years = sorted({y for c in counts.values() for y in c}, reverse=True)
            edits = {r["letter_key"]: r for r in conn.execute("SELECT letter_key, updated_by, updated_at FROM session_letter_text").fetchall()}
            keys = [k for k in et.SESSION_LETTER_ORDER if (k in et.SESSION_TRAINEE_LETTERS) == (kind == "trainees")]
            if kind == "trainees":
                expanded = []
                for k in keys:
                    expanded.append(k)
                    if k in et.OTHER_VARIANTS:
                        expanded.append(et.OTHER_VARIANTS[k])
                    if k == "what_to_bring":
                        expanded.append("what_to_bring_aou")
                keys = expanded
            conn.commit()  # let go of the table locks before the letters are rendered (rendering opens its own connection)
            letter_rows = []
            for k in keys:
                try:
                    subj, body_html, _t = et.session_letter_content(
                        k, "[First name]", "[the training]", "[session dates]", "[place]", role="Lead Facilitator", duties=[],
                        link="[their private link]", partner=None, amount="$1,299 per couple", friday_end="[Friday end time]")
                except Exception:
                    subj, body_html = None, None
                entry = next((e for _i, _t, _d, es in catalog() for e in es if e.get("key") == k), {})
                letter_rows.append(dict(key=k, title=et.SESSION_LETTERS[k]["title"], audience=et.SESSION_LETTERS[k]["audience"],
                                        when=entry.get("when") or "By hand from the session's letters page.", who=entry.get("who") or et.SESSION_LETTERS[k]["audience"],
                                        edit=edits.get(k), subject=subj, html=body_html))
            from datetime import date as _date
            this_year = _date.today().year
            with_sessions = {int(x["session_date"][:4]) for x in sessions if x["session_date"]}
            session_years = sorted({2026, this_year} | with_sessions)
            ahead = sorted(y for y in with_sessions if y >= this_year)
            default_syear = this_year if this_year in with_sessions else (ahead[0] if ahead else (max(with_sessions) if with_sessions else this_year))
            return render_template("correspondence_sessions.html", kind=kind, sessions=sessions, years=years, counts=counts,
                                   session_years=session_years, default_syear=default_syear,
                                   by_year={y: [x for x in sessions if (x["session_date"] or "").startswith(str(y))] for y in session_years},
                                   letter_rows=letter_rows,
                                   labels=h["program_labels"], groups=GROUPS, team_groups=TEAM_GROUPS, live=live())
        finally:
            conn.close()

    @crm.route("/correspondence/trainees")
    def correspondence_trainees():
        return _sessions_page("trainees")

    @crm.route("/correspondence/team")
    def correspondence_team():
        return _sessions_page("team")

    @crm.route("/correspondence/note/<group>", methods=["GET", "POST"])
    def correspondence_note(group):
        if group not in GROUPS:
            abort(404)
        # Team groups: Leadership or Owner. Accounting & Legal: the Owner, or anyone the Owner gave Correspondence.
        if group == "accounting":
            if not h["has_correspondence_access"]():
                flash("Correspondence is restricted. Ask the Owner to give you access.")
                return redirect(url_for(".dashboard"))
        elif not _is_leader():
            flash("That page is restricted to Leadership accounts.")
            return redirect(url_for(".dashboard"))
        ensure_tables(get_db)
        title, who, by_session = GROUPS[group]
        conn = get_db()
        try:
            cohort_id = request.values.get("cohort_id", type=int) if by_session else None
            subject = (request.form.get("subject") or "").strip()
            body = request.form.get("body") or ""
            people = note_recipients(conn, group, cohort_id)
            if request.method == "POST":
                action = request.form.get("action")
                if not subject or not body.strip():
                    flash("Please write a subject and a message first.")
                elif action == "test":
                    me = h["staff_email"]()
                    html, text = build_note(subject, body, (_staff_name() or "").split(" ")[0], _staff_name())
                    try:
                        send_email(to_email=me, subject="[TEST] " + subject, html_content=html, text_content=text)
                        flash(f"Test copy sent to you at {me}. Nothing was sent to the {title} group.")
                    except EmailSendError as e:
                        flash(f"Couldn't send the test copy: {e}")
                elif action == "send":
                    if not live():
                        flash("Sending to people is switched off for now. You can send yourself a test copy.")
                    elif (request.form.get("confirm") or "").strip() != "SEND":
                        flash("Nothing was sent. Type SEND in the box to confirm.")
                    elif not people:
                        flash("There is no one to send to.")
                    else:
                        n, bad = 0, []
                        for cid, first, name, email in people:
                            html, text = build_note(subject, body, first, _staff_name())
                            try:
                                send_email(to_email=email, to_name=first or None, subject=subject,
                                           html_content=html, text_content=text)
                                n += 1
                            except EmailSendError as e:
                                bad.append(f"{name or email} ({e})")
                        conn.execute("INSERT INTO team_notes (group_key, cohort_id, subject, body, sent_by, sent_count, skipped) VALUES (?,?,?,?,?,?,?)",
                                     (group, cohort_id, subject, body, _staff_name(), n, "; ".join(bad) or None))
                        conn.commit()
                        print(f"SENT team note to {group} cohort {cohort_id}: {n} sent by {_staff_name()}", flush=True)
                        msg = f"Sent to {n} {'person' if n == 1 else 'people'}."
                        if bad:
                            msg += " Not sent: " + "; ".join(bad) + "."
                        flash(msg)
                        return redirect(url_for(".correspondence_note", group=group, cohort_id=cohort_id or ""))
            history = conn.execute(
                "SELECT t.*, co.session_number, p.code FROM team_notes t LEFT JOIN cohorts co ON co.id = t.cohort_id "
                "LEFT JOIN programs p ON p.id = co.program_id WHERE t.group_key = ? ORDER BY t.id DESC LIMIT 25", (group,)).fetchall()
            sessions = conn.execute("SELECT co.*, p.code, p.name AS program_name FROM cohorts co JOIN programs p ON p.id = co.program_id "
                                    "ORDER BY co.session_date DESC").fetchall() if by_session else []
            return render_template("correspondence_note.html", group=group, title=title, who=who, by_session=by_session,
                                   people=people, cohort_id=cohort_id, sessions=sessions, labels=h["program_labels"],
                                   subject=subject, body=body, history=history, live=live(),
                                   years=sorted({(x["sent_at"] or "")[:4] for x in history if x["sent_at"]}, reverse=True),
                                   back=("correspondence_team" if group in TEAM_GROUPS else "correspondence_home"))
        finally:
            conn.close()


    # ---------------------------------------------------------------- editing the wording of a letter (with history)
    SESSION_SAMPLE = dict(first_name="Alex", training="The Art of Us", dates="Feb. 12, 2027 to Feb. 14, 2027",
                          location="the hotel", role="Lead Facilitator", duties=["Sound Equipment"], link="https://example.org/your-link",
                          partner="Jordan", amount="$1,299 per couple")
    GUIDE_SAMPLE = dict(first="Alex", label="Relationship Training", vol_name="Pat Smith", vfirst="Pat", vphone="469-555-0100",
                        link="https://example.org/your-link", pw="call or text", client="Jordan Lee", page_link="https://example.org/your-page", when_text=" on Thursday at 2:00 pm")
    FIELD_HELP = {
        "First Name": "the person's first name",
        "when_text": "\" on [day and time]\" when you type one, otherwise nothing",
        "name": "the person's first name, wherever you put it in the letter",
        "Name": "the person's first name, wherever you put it in the letter",
        "First name": "the person's first name (the letter already opens with \"Dear [first name],\" by itself)",
        "training": "the name of the training", "dates": "the session dates", "where": "\" at\" and the place, when there is one",
        "link": "the person's private link (must stay)", "role": "Lead Facilitator or Support Facilitator",
        "duties": "the person's assignment", "amount_sentence": "the fee sentence", "partner_sentence": "the partner sentence",
        "friday_end": "the Friday end time for that program (blank if none is set)",
        "label": "the name of the training", "vol_name": "the Guide's full name", "vfirst": "the Guide's first name",
        "vphone": "the Guide's phone number", "pw": "\"call\", \"text\" or \"call or text\"",
    }

    def _problem(key, subject, body, signoff="", signer=""):
        """A plain-English reason the wording cannot be saved, or None."""
        if not subject.strip() or not body.strip():
            return "Please write a subject and a message."
        names = set()
        try:
            for text in [subject, signoff or "", signer or ""] + [x for x in body.replace("\r\n", "\n").split("\n\n")]:
                for _lit, name, _spec, _conv in string.Formatter().parse(text):
                    if name:
                        names.add(name)
        except ValueError:
            return "A curly bracket { or } is not closed. Words in curly brackets, like {training}, must be spelled exactly as listed."
        bad = sorted(names - set(et.allowed_fields(key)))
        if bad:
            return "These are not recognized: " + ", ".join("{" + b + "}" for b in bad) + ". Use only the words listed on the right."
        if "{link}" in et.original_body(key) and "link" not in names:
            return "This letter must keep {link}, the person's private link."
        return None

    def _record_version(conn, key, subject, body, signoff, signer, note):
        n = conn.execute("SELECT COALESCE(MAX(version), 0) + 1 AS n FROM letter_versions WHERE letter_key = ?", (key,)).fetchone()["n"]
        conn.execute("INSERT INTO letter_versions (letter_key, version, subject, body, signoff, signer, changed_by, note, changed_at) "
                     "VALUES (?,?,?,?,?,?,?,?, to_char(now(), 'YYYY-MM-DD HH24:MI:SS'))",
                     (key, n, subject, body, signoff, signer, session.get("staff_name"), note))
        return n

    def _store_current(conn, key, subject, body, signoff, signer):
        conn.execute(
            """INSERT INTO session_letter_text (letter_key, subject, body, signoff, signer, updated_by, updated_at)
               VALUES (?,?,?,?,?,?, to_char(now(), 'YYYY-MM-DD HH24:MI:SS'))
               ON CONFLICT (letter_key) DO UPDATE SET subject = EXCLUDED.subject, body = EXCLUDED.body,
                 signoff = EXCLUDED.signoff, signer = EXCLUDED.signer, updated_by = EXCLUDED.updated_by,
                 updated_at = EXCLUDED.updated_at""",
            (key, subject, body, signoff, signer, session.get("staff_name")))

    def _can_view_letter(key):
        # Every login (volunteers included) can read any letter; only the Owner changes one.
        return bool(session.get("staff_id"))

    def _can_edit_letter(key):
        # Only the Owner changes the wording of correspondence. Everyone else can read it and suggest changes.
        return bool(session.get("is_owner"))

    @crm.route("/correspondence/letters/<key>/edit", methods=["GET", "POST"])
    def correspondence_letter_edit(key):
        if key not in et.ALL_LETTERS:
            abort(404)
        if not _can_view_letter(key):
            flash("That page is restricted.")
            return redirect(url_for(".dashboard"))
        can_edit = _can_edit_letter(key) and not request.args.get("view")
        if request.method == "POST" and not can_edit:
            flash("Only the Owner can change a letter. You can use \"Suggest a change\" below.")
            return redirect(url_for(".correspondence_letter_edit", key=key))
        conn = get_db()
        try:
            h["ensure_letters_table"](conn)
            orig = et.ALL_LETTERS[key]
            saved = conn.execute("SELECT * FROM session_letter_text WHERE letter_key = ?", (key,)).fetchone()
            orig_vals = dict(subject=orig["subject"], body=et.original_body(key), signoff=orig["signoff"], signer=orig.get("signer", "Kent Hafemann"))
            cur = dict(subject=saved["subject"], body=saved["body"], signoff=saved["signoff"], signer=saved["signer"]) if saved else dict(orig_vals)
            form, error, note = dict(cur), None, ""

            def seed_original():
                """First time a letter is saved: keep the original wording as version 1 so it is never lost."""
                if not conn.execute("SELECT 1 FROM letter_versions WHERE letter_key = ?", (key,)).fetchone():
                    _record_version(conn, key, orig_vals["subject"], orig_vals["body"], orig_vals["signoff"], orig_vals["signer"], "Original wording")

            if request.method == "POST":
                action = request.form.get("action")
                note = (request.form.get("note") or "").strip()[:200]
                form = dict(subject=(request.form.get("subject") or "").strip(), body=(request.form.get("body") or "").strip(),
                            signoff=(request.form.get("signoff") or "").strip(), signer=(request.form.get("signer") or "").strip())
                if action == "reset":
                    seed_original()
                    _record_version(conn, key, orig_vals["subject"], orig_vals["body"], orig_vals["signoff"], orig_vals["signer"], "Returned to the original wording")
                    conn.execute("DELETE FROM session_letter_text WHERE letter_key = ?", (key,))
                    conn.commit()
                    flash("Back to the original wording.")
                    return redirect(url_for(".correspondence_letter_edit", key=key))
                if action == "restore":
                    v = conn.execute("SELECT * FROM letter_versions WHERE id = ? AND letter_key = ?",
                                     (request.form.get("version_id", type=int), key)).fetchone()
                    if v:
                        seed_original()
                        _store_current(conn, key, v["subject"], v["body"], v["signoff"], v["signer"])
                        _record_version(conn, key, v["subject"], v["body"], v["signoff"], v["signer"], f"Restored version {v['version']}")
                        conn.commit()
                        flash(f"Restored version {v['version']}. Letters sent from now on use it.")
                    return redirect(url_for(".correspondence_letter_edit", key=key))
                error = _problem(key, form["subject"], form["body"], form["signoff"], form["signer"])
                if not error and action == "save":
                    if form == cur and not saved:
                        flash("Nothing was changed.")
                        return redirect(url_for(".correspondence_letter_edit", key=key))
                    seed_original()
                    _store_current(conn, key, form["subject"], form["body"], form["signoff"], form["signer"])
                    _record_version(conn, key, form["subject"], form["body"], form["signoff"], form["signer"], note or None)
                    conn.commit()
                    flash("Saved. Letters sent from now on use this wording. Letters already sent keep the wording they went out with.")
                    return redirect(url_for(".correspondence_letter_edit", key=key))
            subject = html = None
            if not error:
                try:
                    if key in et.GUIDE_LETTERS:
                        fill = dict(GUIDE_SAMPLE)
                    else:
                        S = SESSION_SAMPLE
                        fill = et.fill_for(S["first_name"], S["training"], S["dates"], S["location"], S["role"], S["duties"],
                                           S["link"], S["partner"], S["amount"], "The Friday session ends by 11:00 pm at the latest.")
                    subject, html, text = et.render_spec(et.spec_with_edit(key, form), fill, GUIDE_SAMPLE["link"] if key in et.GUIDE_LETTERS else SESSION_SAMPLE["link"])
                    if request.method == "POST" and request.form.get("action") == "test":
                        me = h["staff_email"]()
                        try:
                            send_email(to_email=me, subject="[TEST] " + subject, html_content=html, text_content=text)
                            flash(f"Test copy sent to you at {me}. Nothing was sent to anyone else.")
                        except EmailSendError as e:
                            flash(f"Couldn't send the test copy: {e}")
                except Exception:
                    error = "This wording can't be used. Check the curly-bracket words."
            fields = et.allowed_fields(key)
            blob = orig["subject"] + " ".join(orig["paras"]) + orig.get("signer", "")
            _own_greeting = (not et.ALL_LETTERS.get(key, {}).get("greeting", "x"))
            used = [f for f in fields if "{" + f + "}" in blob and f not in (("first",) if _own_greeting else ("first", "First name"))]
            versions = conn.execute("SELECT * FROM letter_versions WHERE letter_key = ? ORDER BY version DESC", (key,)).fetchall()
            return render_template("correspondence_letter_edit.html", key=key, can_edit=can_edit, is_owner=bool(session.get("is_owner")),
                                   entry=next((e for _i, _t, _d, es in catalog() for e in es if e.get("key") == key), {}), guide_note=(GUIDE_EXPLAINER if key in et.GUIDE_LETTERS and key not in ("sponsor_welcome", "sponsor_page", "profile_request", "video_call", "needs_request", "testimonial_request") else None), guides=(guides_by_group(conn) if key in et.GUIDE_LETTERS else []), orig=orig, form=form, error=error,
                                   saved=saved, preview_subject=subject, preview_html=html, used=used, help=FIELD_HELP,
                                   versions=versions, note=note, current_version=(versions[0]["version"] if versions and saved else None),
                                   back=("correspondence_all" if key in et.GUIDE_LETTERS else
                                         ("correspondence_trainees" if (key in et.SESSION_TRAINEE_LETTERS or key in et.OTHER_VARIANTS.values() or key == "what_to_bring_aou") else "correspondence_team")))
        finally:
            conn.close()
