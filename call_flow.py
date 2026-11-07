"""
"Have a Discovery! team member call you" -- the interested-party call flow.

How it works
  1. Someone fills in the short form (front page, program pages, or the Reserve form) and answers Yes/No to
     "Do we have permission to call and text you on your cell phone?"
  2. On Yes, a call request is saved and the volunteers for that program (set up on the Call volunteers page,
     up to six per program, plus a Guide Team Captain) are alerted. Each alert has a personal link.
  3. The first volunteer to open their link and tap "I'll call within 2 hours" gets the request. The others see
     "already claimed". The interested person is then told the volunteer's name and number.
  4. After calling, the volunteer logs the outcome on the same link.
  5. If nobody claims it in 2 hours, the volunteers are alerted again and Kent is emailed. If a volunteer claims it
     but hasn't logged the call after 2 hours, they get a reminder.

Safety switches (nothing is sent to real people until you turn this on)
  CALL_ALERTS_LIVE=1   in Render's Environment turns the emails on. Until then requests are only saved and shown
                       on the Call requests page.
  Alerts only go out between 8 am and 8 pm Central; anything that comes in overnight goes out at 8 am.

Texting is not built yet (it needs a texting service and registration). The messages are emails for now; the
consent answer and wording are saved so texting can be added later.
"""
import os
import re
import secrets
import time
from datetime import datetime, timedelta

from flask import render_template, request, redirect, url_for, flash, abort

try:
    from zoneinfo import ZoneInfo
    CHI = ZoneInfo("America/Chicago")
except Exception:  # pragma: no cover
    CHI = None

POOLS = [
    ("CAPTAIN", "Guide Team Captain (oversees the team)"),
    ("D1", "D1 – The Beginning"),
    ("D4", "Relationship Training"),
    ("ALL", "Everything else (also the back-up if a program has no volunteers)"),
]
MAX_PER_POOL = 6


def max_for(code):
    return 1 if code == "CAPTAIN" else MAX_PER_POOL
PAGES = {"home": "Front page", "programs": "Programs page", "relationship": "Relationship Training page", "reserve": "Reserve your spot form", "other": "Other"}
WINDOW_HOURS = 2
SEND_FROM_HOUR, SEND_TO_HOUR = 8, 20   # Central time
MAX_ALERT_ROUNDS = 4
OUTCOMES = ["Spoke with them", "Left a voicemail", "Texted \u2013 waiting for a reply", "No answer – will try again", "Not interested", "Wrong number"]

CONSENT_QUESTION = "Do we have permission to text or call you?"
CONSENT_OPTIONS = [("either", "Yes, call or text is fine"), ("text", "Yes, but text only"),
                   ("call", "Yes, but call only"), ("email", "Yes, but please email me")]
PREF_WORD = {"either": "call or text", "text": "text", "call": "call"}
PREF_SHORT = {"either": "Call or text", "text": "Text only", "call": "Call only", "email": "Email only"}
LEGACY = {"yes": "either", "no": "email"}
CONSENT_FINE = ("We call between 8 am and 8 pm Central, usually within a few hours. "
                "Message and data rates may apply. Reply STOP to stop texts.")
CONSENT_WORDING = CONSENT_QUESTION + " (" + CONSENT_FINE + ")"

VOLUNTEER_CONSENT = (
    "I give Discovery! permission to share my name, my cell phone number and my email address with the people "
    "who ask to hear from the Guides, and with the Guide Team Captain and other Guides. This may happen in a "
    "message, an email, a letter or on a web page. I am a volunteer, and I understand that the people I speak with will "
    "be given my name and cell phone number so they can recognize and reach me. Discovery! will not sell or rent "
    "my information. I can withdraw this permission at any time by telling my Guide Team Captain, and Discovery! will "
    "then stop sharing my information with new people.")

_ready = False
_programs_cache = {"at": 0, "rows": []}


# ---------------------------------------------------------------- helpers
def _utc_now():
    return datetime.utcnow()


def _ts(dt):
    return dt.strftime("%Y-%m-%d %H:%M:%S")


def _parse(s):
    return datetime.strptime(str(s)[:19], "%Y-%m-%d %H:%M:%S")


def local_text(s):
    """UTC timestamp text -> 'Oct 15, 4:08 pm' in Central time."""
    if not s:
        return ""
    try:
        d = _parse(s)
        if CHI:
            from datetime import timezone
            d = d.replace(tzinfo=timezone.utc).astimezone(CHI)
        return d.strftime("%b %-d, %-I:%M %p").replace("AM", "am").replace("PM", "pm")
    except Exception:
        return str(s)


def alerts_live():
    return (os.environ.get("CALL_ALERTS_LIVE") or "").strip() == "1"


def sponsor_live():
    """Sponsor letters need the Guide-alerts switch AND SPONSOR_LIVE=1."""
    return alerts_live() and (os.environ.get("SPONSOR_LIVE") or "").strip() == "1"


def in_send_hours(now_utc=None):
    now_utc = now_utc or _utc_now()
    if CHI:
        from datetime import timezone
        local = now_utc.replace(tzinfo=timezone.utc).astimezone(CHI)
    else:
        local = now_utc - timedelta(hours=5)
    return SEND_FROM_HOUR <= local.hour < SEND_TO_HOUR


def _digits(s):
    return "".join(ch for ch in (s or "") if ch.isdigit())


RESPONDED_LIST = "Responded to the Excitement blast"
DISCOVERY_LIST = "Discovery Contact list"
OLD_DISCOVERY_LISTS = ("Entire Discovery database", "Discovery database")


def list_id_for(conn, name):
    """Id of the contact list with this name, creating the list if it doesn't exist yet."""
    row = conn.execute("SELECT id FROM contact_lists WHERE LOWER(name) = LOWER(?)", (name,)).fetchone()
    if not row:
        conn.execute("INSERT INTO contact_lists (name, created_at) VALUES (?, ?)", (name, _ts(_utc_now())[:10]))
        row = conn.execute("SELECT id FROM contact_lists WHERE LOWER(name) = LOWER(?)", (name,)).fetchone()
    return row["id"]


def add_to_list(conn, contact_id, list_name, note=None):
    """Puts a contact on a list (once). Returns True if they were newly added. Never raises."""
    try:
        lid = list_id_for(conn, list_name)
        if conn.execute("SELECT 1 FROM contact_list_members WHERE contact_id = ? AND list_id = ?", (contact_id, lid)).fetchone():
            return False
        conn.execute("INSERT INTO contact_list_members (contact_id, list_id, added_at) VALUES (?, ?, ?)", (contact_id, lid, _ts(_utc_now())[:10]))
        if note:
            _add_note(conn, contact_id, f"{note} ({_ts(_utc_now())[:10]})")
        return True
    except Exception as e:
        print(f"Couldn't add contact {contact_id} to list {list_name}: {e}", flush=True)
        return False


HELPER_DAILY_LIMIT = 20          # people one volunteer's link can bring in per day


def _same_first(a, b):
    """Loose first-name match: same name, or one begins with the other (Bob / Bobby); names under 3 letters must match exactly."""
    a, b = (a or "").strip().lower(), (b or "").strip().lower()
    if not a or not b:
        return False
    if a == b:
        return True
    return min(len(a), len(b)) >= 3 and (a.startswith(b[:3]) and b.startswith(a[:3]))


def pretty_phone(s):
    d = _digits(s)
    if len(d) == 11 and d.startswith("1"):
        d = d[1:]
    return f"{d[0:3]}-{d[3:6]}-{d[6:]}" if len(d) == 10 else (s or "")


def _base_url():
    return (os.environ.get("PUBLIC_BASE_URL") or request.url_root).rstrip("/")


def _program_label(code):
    for c, label in POOLS:
        if c == code:
            return label
    return {"D2": "D2 \u2013 Awakening", "D3": "D3 \u2013 Vision"}.get(code) or code or "Discovery!"


def ensure_tables(get_db):
    global _ready
    if _ready:
        return
    conn = get_db()
    try:
        conn.execute("""CREATE TABLE IF NOT EXISTS call_volunteers (
            id SERIAL PRIMARY KEY,
            program_code TEXT NOT NULL,
            name TEXT NOT NULL,
            cell_phone TEXT NOT NULL,
            email TEXT NOT NULL,
            active INTEGER NOT NULL DEFAULT 1,
            created_at TEXT NOT NULL DEFAULT to_char(now(), 'YYYY-MM-DD HH24:MI:SS'))""")
        conn.execute("""CREATE TABLE IF NOT EXISTS call_requests (
            id SERIAL PRIMARY KEY,
            contact_id INTEGER NOT NULL,
            program_code TEXT,
            cell_phone TEXT,
            note TEXT,
            source TEXT,
            contact_pref TEXT,
            consent_text TEXT,
            consent_at TEXT,
            consent_ip TEXT,
            created_at TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'New',
            first_alert_at TEXT,
            last_alert_at TEXT,
            alert_rounds INTEGER NOT NULL DEFAULT 0,
            claimed_by INTEGER,
            claimed_at TEXT,
            reminder_at TEXT,
            prospect_notified_at TEXT,
            outcome TEXT,
            outcome_note TEXT,
            closed_at TEXT)""")
        conn.execute("ALTER TABLE call_requests ADD COLUMN IF NOT EXISTS contact_pref TEXT")
        for col in ("reserve_token TEXT", "link_sent_at TEXT", "link_sent_via TEXT", "reserved_at TEXT",
                    "reserve_result TEXT", "reserve_cohort_id INTEGER", "partner_name TEXT", "partner_email TEXT",
                    "questionnaire_sent_at TEXT", "questionnaire_sent_via TEXT",
                    "reserved_notified_at TEXT", "paid_notified_at TEXT",
                    "longform_sent_at TEXT", "payment_sent_at TEXT", "payment_reminder_at TEXT", "pay_nudge_at TEXT", "sponsor_page_sent_at TEXT"):
            conn.execute("ALTER TABLE call_requests ADD COLUMN IF NOT EXISTS " + col)
        conn.execute("ALTER TABLE call_volunteers ADD COLUMN IF NOT EXISTS push_topic TEXT")
        conn.execute("ALTER TABLE call_volunteers ADD COLUMN IF NOT EXISTS push_user_key TEXT")
        for col in ("consent_token TEXT", "consent_at TEXT", "consent_name TEXT", "consent_ip TEXT", "consent_text TEXT"):
            conn.execute("ALTER TABLE call_volunteers ADD COLUMN IF NOT EXISTS " + col)
        conn.execute("ALTER TABLE cohorts ADD COLUMN IF NOT EXISTS capacity INTEGER")
        conn.execute("ALTER TABLE enrollments ADD COLUMN IF NOT EXISTS partner_enrollment_id INTEGER")
        conn.execute("ALTER TABLE enrollments ADD COLUMN IF NOT EXISTS questionnaire_token TEXT")
        conn.execute("""CREATE TABLE IF NOT EXISTS call_notices (
            id SERIAL PRIMARY KEY,
            request_id INTEGER NOT NULL,
            volunteer_id INTEGER NOT NULL,
            token TEXT NOT NULL UNIQUE,
            sent_at TEXT,
            send_error TEXT)""")
        conn.execute("""CREATE TABLE IF NOT EXISTS interest_log (
            id SERIAL PRIMARY KEY,
            contact_id INTEGER NOT NULL,
            program_code TEXT,
            page TEXT,
            call_ok TEXT,
            created_at TEXT NOT NULL)""")
        conn.execute("""CREATE TABLE IF NOT EXISTS volunteer_helpers (
            id SERIAL PRIMARY KEY,
            contact_id INTEGER NOT NULL,
            token TEXT NOT NULL UNIQUE,
            referred_by INTEGER,
            matched_by TEXT,
            created_at TEXT NOT NULL,
            welcome_sent_at TEXT,
            last_seen_at TEXT)""")
        conn.commit()
        _ready = True
    except Exception as e:
        conn.rollback()
        print(f"Couldn't set up the call-request tables: {e}", flush=True)
    finally:
        conn.close()



# ---------------------------------------------------------------- the letters people receive (one place, so the Guides can read exactly what is sent)
def letter_curious(first, label, vol_name, vphone, pw):
    from email_templates import guide_letter_content
    return guide_letter_content("guide_curious", first, label, vol_name, vphone, pw=pw)


def letter_helper_welcome(first, page_link, profile_link=None, returning=False):
    subject = "Thank you for being a Discovery! volunteer"
    if returning:
        lead = (f"<p>Hi {first},</p><p>Thank you for being a Discovery! volunteer. We already have you in our records, "
                f"so there is no need to start over.</p>")
        tlead = f"Hi {first},\n\nThank you for being a Discovery! volunteer. We already have you in our records, so there is no need to start over.\n\n"
    else:
        lead = f"<p>Hi {first},</p><p>Thank you for being a Discovery! volunteer, and welcome!</p>"
        tlead = f"Hi {first},\n\nThank you for being a Discovery! volunteer, and welcome!\n\n"
    prof_h = (f"<p>Please take a few minutes to update and complete your contact information here:<br>"
              f"<a href=\"{profile_link}\">{profile_link}</a></p>") if profile_link else ""
    prof_t = f"Please take a few minutes to update and complete your contact information here:\n{profile_link}\n\n" if profile_link else ""
    html = (lead + f"<p>Here is your personal volunteer page. It is private to you, so please keep the link to yourself. "
            f"Come back to it any time:</p><p><a href=\"{page_link}\">{page_link}</a></p>" + prof_h +
            "<p>On your page you will find a link you can text or email to another Discovery! volunteer who would like to help. "
            "Every volunteer gets their own page.</p><p>Thank you for all that you do.</p><p>Warmly,<br>The Discovery! Team</p>")
    text = (tlead + f"Here is your personal volunteer page. It is private to you, so please keep the link to yourself. Come back to it any time:\n{page_link}\n\n"
            + prof_t + "On your page you will find a link you can text or email to another Discovery! volunteer who would like to help. "
            "Every volunteer gets their own page.\n\nThank you for all that you do.\n\nWarmly,\nThe Discovery! Team")
    return subject, html, text


def letter_reserve_link(first, label, link, vol_name, vphone):
    from email_templates import guide_letter_content
    return guide_letter_content("guide_register", first, label, vol_name, vphone, link=link)


def letter_questionnaire(first, label, link, vol_name, vphone):
    from email_templates import guide_letter_content
    return guide_letter_content("guide_questionnaire", first, label, vol_name, vphone, link=link)


CLIENT_LETTERS = [
    ("curious", "Reply to \"I'm curious\"", "Sent automatically as soon as a Guide takes the request."),
    ("register", "Registration link", "Sent when the volunteer taps \"Email it\" in the Ready to register box. (If they tap \"Text it\", the same link goes by text from the volunteer's own phone.)"),
    ("confirm", "Trainee Registration Confirmation", "Sent automatically to both partners soon after they reserve a date."),
    ("questionnaire", "Questionnaire", "Sent when the volunteer taps \"Email it\" in the Send the questionnaire box. Each partner gets their own private link to the form shown below. Relationship Training and D1 use the same questionnaire for now."),
    ("venue", "Where we'll be and what's included", "The venue letter: hotel, what the $1,299 per couple includes, shuttle and check-out. Can be sent to registered couples or used when someone asks about the venue."),
    ("payment", "Payment reminder", "No longer automatic. The Guide is nudged every 7 days while payment is late and sends the reminder if and when they choose."),
]


def letter_venue(first, partner, vol_name, vphone, photo_url=None, room_url=None, dates="[session dates]"):
    subject = "Your weekend at the Four Points by Sheraton \u2013 everything you need to know"
    html = f"""<p>Hi {first},</p>
<p><strong>Welcome to a Fantastic and Adventure Filled Weekend!</strong> We are delighted to confirm your registration for the Discovery! Relationship Training, {dates}.</p>
<p>We\u2019re so glad you and {partner} are joining us for Relationship Training. Here is where we\u2019ll be, what\u2019s included, and how to get there, so there are no surprises and you can simply arrive ready to enjoy the weekend.</p>
<h3>When</h3>
<p><strong>Friday, [date], 7:00 pm</strong> through <strong>Sunday, [date], 1:30 pm</strong>. (Hotel check-in opens at 3:00 pm.)</p>
<p><strong>Arrival:</strong> If possible, please come rested. It is best to arrive around <strong>5:30 pm</strong> to register at the hotel, find your room, get settled, relax, grab a bite to eat, and register at the Discovery! Relationship table situated in front of the training room. The training begins promptly at <strong>7:00 pm</strong>.</p>
<p><strong>Sunday check-out:</strong> hotel check-out is 12:00 noon, before we finish at 1:30 pm. Please check out Sunday morning and bring your bags with you; we will have a secure place to keep them during the final sessions.</p>
<p><strong>Food, access and comfort needs:</strong> please tell us about any food allergies, dietary needs (such as vegetarian, vegan or gluten-free), accessibility needs (for example a wheelchair-accessible room), or injuries that limit everyday activities (such as sitting on the floor) as soon as you can. You can add them in your questionnaire, or simply reply to this email.</p>
<h3>Where</h3>
{('<p><img src="' + photo_url + '" alt="Four Points by Sheraton Dallas Fort Worth Airport North" width="393" style="max-width:100%;height:auto;border-radius:8px"></p>') if photo_url else ''}
<p><strong>Four Points by Sheraton Dallas Fort Worth Airport North Hotel &amp; Convention Center</strong><br>1580 Point West Boulevard, Coppell, Texas 75019<br>Hotel phone: 469-702-6311</p>
<p>The hotel is a comfortable, modern property just north of DFW Airport, about six miles from the terminals. Rooms have free Wi-Fi, plush bedding and a workspace, and the hotel offers a complimentary outdoor pool and a 24-hour fitness center if you\u2019d like to unwind between sessions. Free coffee and tea are always available in the lobby, and the hotel\u2019s Point West Restaurant and Bar serves American favorites and local craft beers if you want something extra. Parking at the hotel is free while you are staying with us.</p>
<h3>What\u2019s included in your $1,299 per couple</h3>
{('<p><img src="' + room_url + '" alt="A guest room at the hotel" width="389" style="max-width:100%;height:auto;border-radius:8px"></p>') if room_url else ''}
<ul><li><strong>Two nights in the hotel</strong> (Friday and Saturday) in a room for the two of you</li>
<li><strong>Saturday night dinner and dance</strong>, a celebration you will remember</li>
<li><strong>All training sessions and materials</strong></li></ul>
<h3>Getting there</h3>
<ul><li><strong>From DFW Airport:</strong> the hotel\u2019s complimentary shuttle runs 24 hours a day, every hour on the hour. Ask at the hotel\u2019s front desk or call 469-702-6311 to arrange your ride.</li>
<li><strong>From Love Field:</strong> the hotel shuttle does not serve Love Field, so you will need an Uber or taxi.</li>
<li><strong>Driving:</strong> follow the address above; parking is free.</li></ul>
<h3>A few reminders</h3>
<ul><li>Please wear something comfortable during the day. Saturday evening is a dance, so bring something you feel great in.</li>
<li>Meals other than those listed above are on your own. The hotel restaurant is on site, and there is a convenience store in the lobby.</li>
<li>Questions? Reply to this email or contact {vol_name} at {vphone}.</li></ul>
<p>We can\u2019t wait to see you both.</p>
<p>Warmly,<br>The Discovery! Team</p>"""
    return subject, html


def welcome_video():
    """Optional 'Welcome to the Guides' video. Set CEP_WELCOME_VIDEO to a YouTube/Vimeo/.mp4 link,
    or upload static/cep-welcome.mp4. Returns {kind, src} or None."""
    import os, re as _re
    u = (os.environ.get("CEP_WELCOME_VIDEO") or "").strip()
    if not u:
        if os.path.exists(os.path.join(os.path.dirname(os.path.abspath(__file__)), "static", "cep-welcome.mp4")):
            return {"kind": "file", "src": "/static/cep-welcome.mp4"}
        return None
    m = _re.search(r"(?:youtu\.be/|youtube\.com/(?:watch\?v=|embed/|shorts/))([\w-]{6,})", u)
    if m:
        return {"kind": "frame", "src": "https://www.youtube.com/embed/" + m.group(1)}
    m = _re.search(r"vimeo\.com/(?:video/)?(\d+)", u)
    if m:
        return {"kind": "frame", "src": "https://player.vimeo.com/video/" + m.group(1)}
    return {"kind": "file", "src": u}


def sample_letter(key):
    """(title, when, subject, html) for the Guides to read, with placeholders in [brackets]."""
    title, when = next(((t, w) for k, t, w in CLIENT_LETTERS if k == key), (None, None))
    if key == "questionnaire-d1":
        title, when = "Questionnaire \u2013 D1", next(w for k, t, w in CLIENT_LETTERS if k == "questionnaire")
    if not title:
        return None
    if key == "curious":
        subject, html, _t = letter_curious("[First name]", "[the training]", "[Volunteer name]", "[volunteer phone]", "call or text")
    elif key == "register":
        subject, html, _t = letter_reserve_link("[First name]", "[the training]", "#", "[Volunteer name]", "[volunteer phone]")
    elif key in ("questionnaire", "questionnaire-d1"):
        subject, html, _t = letter_questionnaire("[First name]", ("D1 \u2013 The Beginning" if key == "questionnaire-d1" else "Relationship Training"), _base_url() + "/cep-letters/" + ("q-d1" if key == "questionnaire-d1" else "q-rt"), "[Volunteer name]", "[volunteer phone]")
    elif key == "venue":
        subject, html = letter_venue("[First name]", "[partner's name]", "[Volunteer name]", "[volunteer phone]", photo_url=_base_url() + "/static/hotel-exterior.png", room_url=_base_url() + "/static/hotel-room.png")
    else:
        from email_templates import session_letter_content
        sl_key = "trainee_confirm" if key == "confirm" else "payment_reminder"
        subject, html, _t = session_letter_content(sl_key, "[First name]", "Relationship Training", "[session dates]",
                                                   partner="[partner's name]", amount="$1,299 per couple")
    return title, when, subject, html


# ---------------------------------------------------------------- seats, dates, the personal reservation link
DEFAULT_CAPACITY = {"D4": 40}     # Relationship Training: 40 COUPLES unless the session says otherwise
COUPLE_PROGRAMS = ("D4",)


def capacity_of(cohort, code):
    """Seats for a session (couples for D4, people otherwise), or None for no limit."""
    try:
        cap = cohort["capacity"]
    except (KeyError, IndexError):
        cap = None
    if cap:
        return int(cap)
    return DEFAULT_CAPACITY.get(code)


def _loc(c):
    try:
        return c["location"]
    except (KeyError, IndexError):
        return None


def seats_used(conn, cohort_id, code):
    rows = conn.execute("SELECT id, partner_enrollment_id AS pe FROM enrollments WHERE cohort_id = ?",
                        (cohort_id,)).fetchall()
    if code in COUPLE_PROGRAMS:
        return sum(1 for r in rows if not r["pe"] or r["id"] < r["pe"])
    return len(rows)


def ensure_capacity_column(get_db):
    """Called by the session form so the 'seats' box works the first time it is used."""
    conn = get_db()
    try:
        conn.execute("ALTER TABLE cohorts ADD COLUMN IF NOT EXISTS capacity INTEGER")
        conn.commit()
    except Exception as e:
        conn.rollback()
        print(f"Couldn't add cohorts.capacity: {e}", flush=True)
    finally:
        conn.close()


def span_text(c):
    def one(d):
        try:
            return datetime.strptime(str(d)[:10], "%Y-%m-%d")
        except ValueError:
            return None
    a, b = one(c["session_date"]), one(c["end_date"]) if c["end_date"] else None
    if not a:
        return str(c["session_date"])
    if not b or b == a:
        return a.strftime("%B ") + str(a.day) + a.strftime(", %Y")
    if a.month == b.month and a.year == b.year:
        return a.strftime("%B ") + f"{a.day}\u2013{b.day}" + a.strftime(", %Y")
    return a.strftime("%B ") + str(a.day) + " \u2013 " + b.strftime("%B ") + str(b.day) + b.strftime(", %Y")


def reserve_link(conn, req, base_url):
    """The person's personal Reserve link (made the first time it is needed)."""
    tok = req["reserve_token"]
    if not tok:
        tok = secrets.token_urlsafe(16)
        conn.execute("UPDATE call_requests SET reserve_token = ? WHERE id = ?", (tok, req["id"]))
        conn.commit()
    return f"{base_url}/reserve/{tok}"


def _find_or_make_contact(conn, first, last, email, phone, note):
    row = conn.execute("SELECT id FROM contacts WHERE lower(email) = lower(?) ORDER BY id LIMIT 1", (email,)).fetchone()
    if row:
        conn.execute("UPDATE contacts SET cell_phone = COALESCE(NULLIF(cell_phone, ''), ?) WHERE id = ?", (phone or None, row["id"]))
        return row["id"]
    cur = conn.execute(
        """INSERT INTO contacts (first_name, last_name, email, cell_phone, notes, marketing_source, status)
           VALUES (?, ?, ?, ?, ?, ?, ?)""", (first, last or None, email, phone or None, note, "Website", "Interested Party"))
    return cur.lastrowid


def _add_note(conn, contact_id, line):
    cur = conn.execute("SELECT notes FROM contacts WHERE id = ?", (contact_id,)).fetchone()
    merged = ((cur["notes"] + "\n") if cur and cur["notes"] else "") + line
    conn.execute("UPDATE contacts SET notes = ? WHERE id = ?", (merged, contact_id))


def reserve_seat(get_db, req_id, cohort_id, person, partner):
    """Enrolls the person (and partner, for couples) or puts them on the waitlist when the date is full.
    Returns ("Enrolled" | "Waitlist" | "Already", cohort_row, message)."""
    conn = get_db()
    try:
        req = conn.execute("SELECT * FROM call_requests WHERE id = ?", (req_id,)).fetchone()
        coh = conn.execute("""SELECT c.*, p.code, p.name AS pname FROM cohorts c JOIN programs p ON p.id = c.program_id
                              WHERE c.id = ?""", (cohort_id,)).fetchone()
        if not coh or coh["code"] != (req["program_code"] or coh["code"]):
            return "Error", None, "Please choose one of the dates in the list."
        code = coh["code"]
        couple = code in COUPLE_PROGRAMS
        label = f"{code} #{coh['session_number']}, {span_text(coh)}"
        cid = req["contact_id"]
        conn.execute("UPDATE contacts SET first_name = ?, last_name = ?, email = ?, cell_phone = ? WHERE id = ?",
                     (person["first"], person["last"] or None, person["email"], person["phone"] or None, cid))
        pid = None
        if couple:
            pid = _find_or_make_contact(conn, partner["first"], partner["last"], partner["email"], "",
                                        f"Partner of {person['first']} {person['last']} (reserved {label} by personal link)")
            if pid == cid:
                conn.rollback()
                return "Error", None, "Your partner needs their own name and email address."
        have = conn.execute("SELECT id FROM enrollments WHERE contact_id = ? AND cohort_id = ?", (cid, cohort_id)).fetchone()
        if have:
            conn.rollback()
            return "Already", coh, ""
        cap = capacity_of(coh, code)
        used = seats_used(conn, cohort_id, code)
        result = "Enrolled"
        if cap is not None and used + 1 > cap:
            result = "Waitlist"
        else:
            e1 = conn.execute("INSERT INTO enrollments (contact_id, cohort_id) VALUES (?, ?)", (cid, cohort_id)).lastrowid
            e2 = None
            if couple:
                row = conn.execute("SELECT id FROM enrollments WHERE contact_id = ? AND cohort_id = ?", (pid, cohort_id)).fetchone()
                e2 = row["id"] if row else conn.execute(
                    "INSERT INTO enrollments (contact_id, cohort_id) VALUES (?, ?)", (pid, cohort_id)).lastrowid
                conn.execute("UPDATE enrollments SET partner_enrollment_id = ? WHERE id = ?", (e2, e1))
                conn.execute("UPDATE enrollments SET partner_enrollment_id = ? WHERE id = ?", (e1, e2))
            # two people finishing at the same moment: recount, and if we went over, step back to the waitlist
            if cap is not None and seats_used(conn, cohort_id, code) > cap:
                for e in (e1, e2):
                    if e:
                        conn.execute("DELETE FROM enrollments WHERE id = ?", (e,))
                result = "Waitlist"
        now = _ts(_utc_now())
        conn.execute("""UPDATE call_requests SET reserved_at = ?, reserve_result = ?, reserve_cohort_id = ?,
                        partner_name = ?, partner_email = ? WHERE id = ?""",
                     (now, result, cohort_id, (f"{partner['first']} {partner['last']}".strip() if couple else None),
                      (partner["email"] if couple else None), req_id))
        _add_note(conn, cid, f"{'Reserved' if result == 'Enrolled' else 'WAITLIST for'} {label} by personal link, "
                             f"{local_text(now)}" + (f" (with {partner['first']} {partner['last']})" if couple else "")
                  + ("; payment pending" if result == "Enrolled" else ""))
        conn.commit()
        if result == "Waitlist":
            _tell_waitlist(conn, req, person, partner if couple else None, label)
        return result, coh, ""
    except Exception as e:
        conn.rollback()
        print(f"Reservation failed for request {req_id}: {e}", flush=True)
        return "Error", None, "Sorry, something went wrong on our end. Please try again in a moment."
    finally:
        conn.close()


def _tell_waitlist(conn, req, person, partner, label):
    if not alerts_live():
        return
    who = f"{person['first']} {person['last']}".strip() + (f" and {partner['first']} {partner['last']}".rstrip() if partner else "")
    subject = f"Full date \u2013 {who} need another date"
    html = (f"<p><strong>{who}</strong> tried to reserve <strong>{label}</strong>, but that date is full.</p>"
            f"<p>Cell: {pretty_phone(person['phone'])} &middot; {person['email']}</p>"
            f"<p>Please reach out to find them another date. They were told a team member would.</p>")
    text = (f"{who} tried to reserve {label}, but that date is full.\nCell: {pretty_phone(person['phone'])}  {person['email']}\n"
            f"Please reach out to find them another date. They were told a team member would.")
    to = [_leadership_email()]
    if req["claimed_by"]:
        v = conn.execute("SELECT email FROM call_volunteers WHERE id = ?", (req["claimed_by"],)).fetchone()
        if v and v["email"]:
            to.append(v["email"])
    for addr in to:
        try:
            _send(addr, subject, html, text)
        except Exception as e:
            print(f"Couldn't send waitlist note to {addr}: {e}", flush=True)

def questionnaire_links(conn, req, base_url):
    """Questionnaire links for the person (and partner) once they are enrolled.
    Returns {"person": link or None, "partner": {"name", "email", "link"} or None}."""
    out = {"person": None, "partner": None}
    if req["reserve_result"] != "Enrolled" or not req["reserve_cohort_id"]:
        return out

    def link_for(enrollment_id):
        row = conn.execute("SELECT questionnaire_token FROM enrollments WHERE id = ?", (enrollment_id,)).fetchone()
        if not row:
            return None
        tok = row["questionnaire_token"]
        if not tok:
            tok = secrets.token_urlsafe(24)
            conn.execute("UPDATE enrollments SET questionnaire_token = ? WHERE id = ?", (tok, enrollment_id))
            conn.commit()
        return f"{base_url}/questionnaire/{tok}"

    me = conn.execute("SELECT id, partner_enrollment_id AS pe FROM enrollments WHERE contact_id = ? AND cohort_id = ?",
                      (req["contact_id"], req["reserve_cohort_id"])).fetchone()
    if not me:
        return out
    out["person"] = link_for(me["id"])
    if me["pe"]:
        pc = conn.execute("""SELECT ct.first_name, ct.last_name, ct.email FROM enrollments e JOIN contacts ct ON ct.id = e.contact_id
                             WHERE e.id = ?""", (me["pe"],)).fetchone()
        if pc:
            out["partner"] = {"name": f"{pc['first_name']} {pc['last_name'] or ''}".strip(), "first": pc["first_name"],
                              "email": pc["email"], "link": link_for(me["pe"])}
    return out


def client_progress(conn, req, base_url):
    """What the Guide sees for one client: a checklist filled in from the data, and the single best next step."""
    steps = []
    talked = bool(req["outcome"])
    steps.append(("Talked with them", talked))
    reserved = req["reserve_result"] == "Enrolled" and bool(req["reserve_cohort_id"])
    steps.append(("Reserved a seat", reserved))
    prof = {"complete": False, "photo": False, "link": None, "missing": []}
    q_done = paid = False
    cohort_start = None
    if reserved:
        c = conn.execute("SELECT * FROM contacts WHERE id = ?", (req["contact_id"],)).fetchone()
        need = (("street_address", "street address"), ("city", "city"), ("state", "state"), ("zip", "zip"),
                ("cell_phone", "cell phone"), ("emergency_contact_name", "emergency contact"),
                ("emergency_contact_cell", "emergency contact phone"))
        prof["missing"] = [lab for col, lab in need if c is None or not (c[col] or "").strip()]
        prof["complete"] = not prof["missing"]
        ph = conn.execute("SELECT 1 FROM contact_photos WHERE contact_id = ?", (req["contact_id"],)).fetchone()
        prof["photo"] = bool(ph)
        if c is not None and c["profile_token"]:
            prof["link"] = f"{base_url}/complete-profile/{c['profile_token']}"
        enr = conn.execute("SELECT questionnaire_completed_at AS q, payment_completed_at AS p FROM enrollments "
                           "WHERE contact_id = ? AND cohort_id = ?", (req["contact_id"], req["reserve_cohort_id"])).fetchone()
        q_done = bool(enr and enr["q"])
        paid = bool(enr and enr["p"])
        co = conn.execute("SELECT session_date FROM cohorts WHERE id = ?", (req["reserve_cohort_id"],)).fetchone()
        cohort_start = co["session_date"] if co else None
    steps.append(("Contact information complete" + (f" (still needed: {', '.join(prof['missing'])})" if reserved and prof["missing"] else ""),
                  reserved and prof["complete"]))
    steps.append(("Photo added", reserved and prof["photo"]))
    steps.append(("Questionnaire complete", q_done))
    steps.append(("Payment received", paid))
    # the single best next step
    if not talked:
        nxt = ("Reach out", "Call or text them, then tell us how it went (below).", None)
    elif not reserved:
        nxt = ("Send the registration link", "When they are ready, send their personal link to reserve a seat.", "register")
    elif not q_done and not req["questionnaire_sent_at"]:
        nxt = ("Send the questionnaire", "They have reserved. Send the questionnaire link.", "questionnaire")
    elif not paid and not req["payment_sent_at"]:
        nxt = ("Send the payment request", "Their seat is held until payment arrives.", "payment")
    elif not prof["complete"] or not prof["photo"]:
        nxt = ("Ask for the profile and a photo", "Their contact information (and a photo) is not finished yet.", "longform")
    elif not q_done:
        nxt = ("Check in on the questionnaire", "It has been sent but is not finished.", "questionnaire")
    elif not paid:
        nxt = ("Follow up on payment", "Payment has not arrived. A friendly reminder is your call.", "payment_reminder")
    else:
        nxt = ("All done!", "Everything is complete. We will send the what-to-bring letter a week before the training.", None)
    done_n = sum(1 for _, ok in steps if ok)
    return {"steps": steps, "done": done_n, "total": len(steps), "next_title": nxt[0], "next_text": nxt[1], "next_kind": nxt[2],
            "profile_link": prof["link"], "reserved": reserved, "paid": paid, "start": cohort_start}


GUIDE_LIST = "Guides"
LEAD_GUIDE_LIST = "Guide Team Captain"


def sync_guide_lists(conn):
    """Keeps two contact lists up to date from the Guides page: 'Guides' and 'Guide Team Captain' (matched by email).
    Use the Lists filter on Contacts to see them. Never raises."""
    try:
        conn.execute("UPDATE contact_lists SET name = ? WHERE name = 'Lead Guide' AND NOT EXISTS (SELECT 1 FROM contact_lists WHERE name = ?)",
                     (LEAD_GUIDE_LIST, LEAD_GUIDE_LIST))
        g, l = list_id_for(conn, GUIDE_LIST), list_id_for(conn, LEAD_GUIDE_LIST)
        want = {g: set(), l: set()}
        for v in conn.execute("SELECT program_code, email FROM call_volunteers WHERE active = 1 AND program_code <> 'SPONSOR'").fetchall():
            c = conn.execute("SELECT id FROM contacts WHERE LOWER(email) = LOWER(?) ORDER BY id LIMIT 1", (v["email"] or "",)).fetchone()
            if c:
                want[l if v["program_code"] == "CAPTAIN" else g].add(c["id"])
        now = _ts(_utc_now())[:10]
        for lid, ids in want.items():
            have = {r["contact_id"] for r in conn.execute("SELECT contact_id FROM contact_list_members WHERE list_id = ?", (lid,)).fetchall()}
            for cid in ids - have:
                conn.execute("INSERT INTO contact_list_members (contact_id, list_id, added_at) VALUES (?, ?, ?)", (cid, lid, now))
            for cid in have - ids:
                conn.execute("DELETE FROM contact_list_members WHERE contact_id = ? AND list_id = ?", (cid, lid))
        conn.commit()
    except Exception as e:
        try:
            conn.rollback()
        except Exception:
            pass
        print(f"Couldn't update the Guide lists: {e}", flush=True)


def guide_for_email(conn, email):
    """The active Guide whose email matches this contact's email, with a plain role label, or None."""
    if not (email or "").strip():
        return None
    v = conn.execute("SELECT id, name, program_code FROM call_volunteers WHERE active = 1 AND LOWER(email) = LOWER(?) ORDER BY id LIMIT 1",
                     (email.strip(),)).fetchone()
    if not v:
        return None
    return dict(id=v["id"], name=v["name"], role=("Sponsor" if v["program_code"] == "SPONSOR" else "Guide Team Captain" if v["program_code"] == "CAPTAIN" else "Guide"),
                group=dict(POOLS).get(v["program_code"], v["program_code"]))


# ---------------------------------------------------------------- creating a request
def create_interest(get_db, form, source):
    """Saves a person from one of the public forms. Returns (ok, how_they_want_to_be_reached, error_message)."""
    first = (form.get("first_name") or "").strip()
    last = (form.get("last_name") or "").strip() or None
    email = (form.get("email") or "").strip()
    phone = (form.get("phone") or "").strip()
    program = (form.get("program_code") or "").strip().upper()
    message = (form.get("message") or "").strip()
    consent = (form.get("call_ok") or "").strip().lower()
    consent = LEGACY.get(consent, consent)
    if consent not in PREF_SHORT:
        consent = ""
    import botguard
    ok_bot, bot_msg = botguard.check(get_db, "curious", form, email=email, ip_limit=6, email_limit=3)
    if not ok_bot:
        if bot_msg is None:          # hidden spam-trap field was filled: pretend it worked
            return True, False, None
        return False, False, bot_msg
    if not first or not email:
        return False, False, "Please enter your first name and email."
    if consent in PREF_WORD and len(_digits(phone)) < 10:
        return False, False, "To have someone call or text you, please enter your cell phone number."

    ensure_tables(get_db)
    conn = get_db()
    try:
        notes = []
        if program:
            notes.append(f"Interested in: {program}")
        if message:
            notes.append(message)
        notes.append(f"(Submitted via website: {source})")
        existing = conn.execute("SELECT id, cell_phone, notes FROM contacts WHERE lower(email) = lower(?) ORDER BY id LIMIT 1",
                                (email,)).fetchone()
        if existing:
            cid = existing["id"]
            new_notes = ((existing["notes"] or "") + "\n" if existing["notes"] else "") + "\n".join(notes)
            conn.execute("UPDATE contacts SET notes = ?, cell_phone = COALESCE(NULLIF(cell_phone, ''), ?) WHERE id = ?",
                         (new_notes, phone or None, cid))
        else:
            cur = conn.execute(
                """INSERT INTO contacts (first_name, last_name, email, cell_phone, notes, marketing_source, status)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (first, last, email, phone or None, "\n".join(notes), "Website", "Interested Party"))
            cid = cur.lastrowid
        page = (form.get("page") or "").strip().lower()
        if page not in PAGES:
            page = "other"
        conn.execute("INSERT INTO interest_log (contact_id, program_code, page, call_ok, created_at) VALUES (?, ?, ?, ?, ?)",
                     (cid, program or None, page, consent or None, _ts(_utc_now())))
        req_id = None
        if consent in PREF_WORD:
            recent = conn.execute(
                """SELECT id FROM call_requests WHERE contact_id = ? AND status IN ('New', 'Claimed') AND created_at >= ?""",
                (cid, _ts(_utc_now() - timedelta(hours=24)))).fetchone()
            if not recent:
                ip = (request.headers.get("X-Forwarded-For", "") or request.remote_addr or "").split(",")[0].strip()
                now = _ts(_utc_now())
                cur = conn.execute(
                    """INSERT INTO call_requests (contact_id, program_code, cell_phone, note, source, consent_text,
                                                  consent_at, consent_ip, created_at, contact_pref)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (cid, program or None, phone, message or None, source,
                     f"{CONSENT_WORDING} Answer: {dict(CONSENT_OPTIONS).get(consent, consent)}", now, ip, now, consent))
                req_id = cur.lastrowid
        conn.commit()
    except Exception as e:
        conn.rollback()
        print(f"Interest form failed: {e}", flush=True)
        return False, False, "Sorry, something went wrong on our end. Please try again in a moment."
    finally:
        conn.close()
    if req_id:
        try:
            dispatch(get_db, req_id, _base_url())
        except Exception as e:
            print(f"Call alert dispatch failed: {e}", flush=True)
    return True, consent, None


# ---------------------------------------------------------------- phone alerts (Pushover)
def pushover_ready():
    """True when Kent has put the Pushover application token in Render's Environment (PUSHOVER_APP_TOKEN)."""
    return bool((os.environ.get("PUSHOVER_APP_TOKEN") or "").strip())


def valid_user_key(key):
    return bool(re.fullmatch(r"[A-Za-z0-9]{30}", (key or "").strip()))


def push(user_key, title, message, click=None, high=True):
    """Send a phone notification through Pushover. Never raises: the email is the back-up."""
    token = (os.environ.get("PUSHOVER_APP_TOKEN") or "").strip()
    if not token or not valid_user_key(user_key):
        return False
    try:
        import urllib.request, urllib.parse
        data = {"token": token, "user": user_key.strip(), "title": title[:240], "message": message[:1000],
                "priority": "1" if high else "0"}
        if click:
            data["url"] = click
            data["url_title"] = "Open"
        req = urllib.request.Request("https://api.pushover.net/1/messages.json",
                                     data=urllib.parse.urlencode(data).encode("utf-8"), method="POST")
        with urllib.request.urlopen(req, timeout=8) as r:
            return 200 <= r.status < 300
    except Exception as e:
        print(f"Phone alert failed: {e}", flush=True)
        return False


# ---------------------------------------------------------------- alerts
def _pool(conn, program_code):
    rows = conn.execute("SELECT * FROM call_volunteers WHERE active = 1 AND program_code = ? ORDER BY id",
                        (program_code or "",)).fetchall()
    if not rows:
        rows = conn.execute("SELECT * FROM call_volunteers WHERE active = 1 AND program_code = 'ALL' ORDER BY id").fetchall()
    return rows


def _send(to_email, subject, html, text, to_name=None, headers=None):
    from email_utils import send_email
    return send_email(to_email, subject, html, to_name=to_name, text_content=text, headers=headers)


def _leadership_email():
    return os.environ.get("EMAIL_FROM_ADDRESS", "kent@blueskyusa.net")


def _notice_for(conn, request_id, volunteer_id):
    row = conn.execute("SELECT token FROM call_notices WHERE request_id = ? AND volunteer_id = ?",
                       (request_id, volunteer_id)).fetchone()
    if row:
        return row["token"]
    token = secrets.token_urlsafe(16)
    conn.execute("INSERT INTO call_notices (request_id, volunteer_id, token) VALUES (?, ?, ?)",
                 (request_id, volunteer_id, token))
    return token


def dispatch(get_db, request_id, base_url, force=False):
    """Alert the volunteers for a still-unclaimed request. Returns a short status word."""
    ensure_tables(get_db)
    if not alerts_live():
        return "held (sending is off)"
    if not in_send_hours():
        return "waiting for 8 am"
    conn = get_db()
    try:
        req = conn.execute("SELECT r.*, c.first_name, c.last_name FROM call_requests r JOIN contacts c ON c.id = r.contact_id "
                           "WHERE r.id = ?", (request_id,)).fetchone()
        if not req or req["status"] != "New":
            return "not needed"
        now = _utc_now()
        first_round = req["first_alert_at"] is None
        if not first_round and not force:
            if _parse(req["last_alert_at"]) > now - timedelta(hours=WINDOW_HOURS):
                return "not due yet"
            if req["alert_rounds"] >= MAX_ALERT_ROUNDS:
                return "gave up re-alerting"
        # take the round atomically so two workers don't both send it
        claimed = conn.execute(
            "UPDATE call_requests SET last_alert_at = ?, alert_rounds = alert_rounds + 1, "
            "first_alert_at = COALESCE(first_alert_at, ?) WHERE id = ? AND status = 'New' AND alert_rounds = ?",
            (_ts(now), _ts(now), request_id, req["alert_rounds"]))
        conn.commit()
        if claimed.rowcount != 1:
            return "someone else is sending"
        vols = _pool(conn, req["program_code"])
        label = _program_label(req["program_code"])
        who = f"{req['first_name']} {(req['last_name'] or '')[:1]}.".replace(" .", "")
        sent_to = 0
        for v in vols:
            token = _notice_for(conn, request_id, v["id"])
            url = f"{base_url}/call/{token}"
            again = "" if first_round else " (second reminder: no one has claimed this yet)"
            pw = PREF_WORD.get(req["contact_pref"] or "either", "call or text")
            subject = f"Please reach out to {who} within 2 hours – {label}"
            html = (f"<p>Hi {v['name'].split()[0]},</p>"
                    f"<p><strong>{who}</strong> asked to be reached about <strong>{label}</strong>{again}. "
                    f"They prefer: <strong>{PREF_SHORT.get(req['contact_pref'] or 'either')}</strong>.</p>"
                    f"<p>Can you {pw} them within two hours? Tap here to say yes:<br>"
                    f"<a href=\"{url}\">{url}</a></p>"
                    f"<p>If another volunteer already took it, the page will tell you. Thank you for helping!</p>")
            text = (f"Hi {v['name'].split()[0]},\n\n{who} asked to be reached about {label}{again}. "
                    f"They prefer: {PREF_SHORT.get(req['contact_pref'] or 'either')}.\n\n"
                    f"Can you {pw} them within two hours? Tap here to say yes:\n{url}\n\n"
                    f"If another volunteer already took it, the page will tell you. Thank you for helping!")
            try:
                push(v["push_user_key"], f"{who} wants to hear from us",
                     f"Can you {pw} {who} within 2 hours? Tap to say yes. ({label})", click=url)
            except Exception as e:
                print(f"Phone alert skipped: {e}", flush=True)
            try:
                _send(v["email"], subject, html, text, to_name=v["name"])
                conn.execute("UPDATE call_notices SET sent_at = ?, send_error = NULL WHERE request_id = ? AND volunteer_id = ?",
                             (_ts(_utc_now()), request_id, v["id"]))
                sent_to += 1
            except Exception as e:
                conn.execute("UPDATE call_notices SET send_error = ? WHERE request_id = ? AND volunteer_id = ?",
                             (str(e)[:200], request_id, v["id"]))
        conn.commit()
        if not first_round or not vols or sent_to == 0:
            why = ("No volunteers are set up for this program." if not vols
                   else "No volunteer could be emailed." if sent_to == 0
                   else "Nobody has claimed this request in 2 hours; the volunteers were alerted again.")
            to_list = [_leadership_email()]
            cap = conn.execute("SELECT email FROM call_volunteers WHERE active = 1 AND program_code = 'CAPTAIN' ORDER BY id LIMIT 1").fetchone()
            if cap and cap["email"] and cap["email"].lower() not in [x.lower() for x in to_list]:
                to_list.append(cap["email"])
            for addr in to_list:
                try:
                    _send(addr, f"Unclaimed call request: {who} ({label})",
                          f"<p>{why}</p><p>Open Call requests in the CRM to follow up: "
                          f"<a href=\"{base_url}/crm/call-requests\">{base_url}/crm/call-requests</a></p>",
                          f"{why}\n\nOpen Call requests in the CRM: {base_url}/crm/call-requests")
                except Exception as e:
                    print(f"Couldn't email {addr} about call request {request_id}: {e}", flush=True)
        return f"alerted {sent_to}"
    finally:
        conn.close()


def _tell_prospect(conn, req, vol, base_url):
    if not alerts_live():
        return
    contact = conn.execute("SELECT first_name, email FROM contacts WHERE id = ?", (req["contact_id"],)).fetchone()
    if not contact or not contact["email"]:
        return
    label = _program_label(req["program_code"])
    vphone = pretty_phone(vol["cell_phone"])
    pw = PREF_WORD.get(req["contact_pref"] or "either", "call or text")
    subject, html, text = letter_curious(contact["first_name"], label, vol["name"], vphone, pw)
    try:
        _send(contact["email"], subject, html, text, to_name=contact["first_name"])
        conn.execute("UPDATE call_requests SET prospect_notified_at = ? WHERE id = ?", (_ts(_utc_now()), req["id"]))
    except Exception as e:
        print(f"Couldn't email the interested person for request {req['id']}: {e}", flush=True)


def _sponsor_pages(get_db):
    """When a Sponsor's own contact form is complete (required items and a photo), email their page once."""
    if not sponsor_live():
        return
    import sponsors
    from email_templates import guide_letter_content
    conn = get_db()
    try:
        rows = conn.execute(
            """SELECT r.id, r.claimed_by, r.program_code, c.first_name, c.last_name
               FROM call_requests r JOIN contacts c ON c.id = r.contact_id
               WHERE r.source = 'sponsor' AND r.claimed_by IS NOT NULL AND r.sponsor_page_sent_at IS NULL""").fetchall()
        for r in rows:
            vol = conn.execute("SELECT id, name, email, cell_phone FROM call_volunteers WHERE id = ?", (r["claimed_by"],)).fetchone()
            if not vol or not vol["email"]:
                continue
            me = conn.execute("SELECT * FROM contacts WHERE lower(email) = lower(?) OR lower(email_2) = lower(?) OR lower(email_3) = lower(?) ORDER BY id LIMIT 1",
                              (vol["email"], vol["email"], vol["email"])).fetchone()
            if not me:
                continue
            st = sponsors.profile_status(conn, me, _base_url())
            if not st["complete"]:
                continue
            got = conn.execute("UPDATE call_requests SET sponsor_page_sent_at = ? WHERE id = ? AND sponsor_page_sent_at IS NULL",
                               (_ts(_utc_now()), r["id"]))
            conn.commit()
            if got.rowcount != 1:
                continue
            who = f"{r['first_name']} {r['last_name'] or ''}".strip()
            try:
                subject, html, text = guide_letter_content(
                    "sponsor_page", me["first_name"], _program_label(r["program_code"]) if r["program_code"] else "Discovery!", vol["name"],
                    pretty_phone(me["cell_phone"] or vol["cell_phone"]), client=who, page_link=_page_link(conn, r["id"], vol["id"]))
                _send(vol["email"], subject, html, text, to_name=vol["name"])
            except Exception as e:
                conn.execute("UPDATE call_requests SET sponsor_page_sent_at = NULL WHERE id = ?", (r["id"],))
                conn.commit()
                print(f"Sponsor page email failed: {e}", flush=True)
    finally:
        conn.close()


def sweep(get_db, base_url):
    """Run every few minutes: first alerts held overnight, 2-hour re-alerts, and 'please log your call' reminders."""
    ensure_tables(get_db)
    if not alerts_live():
        return
    conn = get_db()
    try:
        open_new = [r["id"] for r in conn.execute("SELECT id FROM call_requests WHERE status = 'New' ORDER BY id").fetchall()]
        stale = conn.execute(
            "SELECT r.id, r.claimed_by, r.contact_id, r.program_code FROM call_requests r WHERE r.status = 'Claimed' "
            "AND r.reminder_at IS NULL AND r.claimed_at <= ?", (_ts(_utc_now() - timedelta(hours=WINDOW_HOURS)),)).fetchall()
    finally:
        conn.close()
    for rid in open_new:
        dispatch(get_db, rid, base_url)
    if stale and in_send_hours():
        conn = get_db()
        try:
            for r in stale:
                vol = conn.execute("SELECT * FROM call_volunteers WHERE id = ?", (r["claimed_by"],)).fetchone()
                tok = conn.execute("SELECT token FROM call_notices WHERE request_id = ? AND volunteer_id = ?",
                                   (r["id"], r["claimed_by"])).fetchone()
                done = conn.execute("UPDATE call_requests SET reminder_at = ? WHERE id = ? AND reminder_at IS NULL",
                                    (_ts(_utc_now()), r["id"]))
                conn.commit()
                if done.rowcount == 1 and vol and tok:
                    url = f"{base_url}/call/{tok['token']}"
                    try:
                        _send(vol["email"], "Please log your call",
                              f"<p>Hi {vol['name'].split()[0]},</p><p>You took a call request a couple of hours ago. "
                              f"When you&rsquo;ve called, please log how it went here:<br><a href=\"{url}\">{url}</a></p>"
                              f"<p>Thank you!</p>",
                              f"Hi {vol['name'].split()[0]},\n\nYou took a call request a couple of hours ago. When you've "
                              f"called, please log how it went here:\n{url}\n\nThank you!", to_name=vol["name"])
                    except Exception as e:
                        print(f"Reminder failed: {e}", flush=True)
        finally:
            conn.close()
    if in_send_hours():
        try:
            _sponsor_pages(get_db)
        except Exception as e:
            print(f"Sponsor pages failed: {e}", flush=True)
        try:
            _notify_milestones(get_db)
        except Exception as e:
            print(f"Milestone notes failed: {e}", flush=True)


def _notify_milestones(get_db):
    """Tell the Guide when the person they helped has registered, and again when they have paid."""
    conn = get_db()
    try:
        rows = conn.execute(
            """SELECT r.id, r.contact_id, r.program_code, r.claimed_by, r.reserve_cohort_id, r.partner_name,
                      r.reserved_notified_at, r.paid_notified_at, c.first_name, c.last_name
               FROM call_requests r JOIN contacts c ON c.id = r.contact_id
               WHERE r.reserve_result = 'Enrolled' AND r.claimed_by IS NOT NULL AND r.reserve_cohort_id IS NOT NULL
                 AND (r.reserved_notified_at IS NULL OR r.paid_notified_at IS NULL)""").fetchall()
        for r in rows:
            vol = conn.execute("SELECT id, name, email, push_user_key FROM call_volunteers WHERE id = ?", (r["claimed_by"],)).fetchone()
            coh = conn.execute("SELECT c.*, p.code FROM cohorts c JOIN programs p ON p.id = c.program_id WHERE c.id = ?",
                               (r["reserve_cohort_id"],)).fetchone()
            enr = conn.execute("SELECT payment_completed_at AS p FROM enrollments WHERE contact_id = ? AND cohort_id = ?",
                               (r["contact_id"], r["reserve_cohort_id"])).fetchone()
            if not vol or not vol["email"] or not coh:
                continue
            who = f"{r['first_name']} {r['last_name'] or ''}".strip() + (f" and {r['partner_name']}" if r["partner_name"] else "")
            what = f"{_program_label(r['program_code'])}, {span_text(coh)}"
            first = vol["name"].split()[0]
            if not r["reserved_notified_at"]:
                claim = conn.execute("UPDATE call_requests SET reserved_notified_at = ? WHERE id = ? AND reserved_notified_at IS NULL",
                                     (_ts(_utc_now()), r["id"]))
                conn.commit()
                if claim.rowcount == 1:
                    _milestone_mail(vol, f"{r['first_name']} has registered!",
                                    f"Hi {first},", f"Good news: <strong>{who}</strong> registered for {what}, thanks to your conversation. "
                                    f"Please open your page for them to send the questionnaire link and the payment request: {_page_link(conn, r['id'], r['claimed_by'])} "
                                    f"Payment is still pending. We will let you know when it comes in.")
            if enr and enr["p"] and not r["paid_notified_at"]:
                claim = conn.execute("UPDATE call_requests SET paid_notified_at = ? WHERE id = ? AND paid_notified_at IS NULL",
                                     (_ts(_utc_now()), r["id"]))
                conn.commit()
                if claim.rowcount == 1:
                    _milestone_mail(vol, f"{r['first_name']} has registered and paid!",
                                    f"Hi {first},", f"<strong>{who}</strong> has paid for {what}. Their spot is secure. "
                                    f"Thank you for helping them take this step!")
        _payment_nudges(conn)
    finally:
        conn.close()


def _page_link(conn, request_id, volunteer_id):
    t = conn.execute("SELECT token FROM call_notices WHERE request_id = ? AND volunteer_id = ?", (request_id, volunteer_id)).fetchone()
    return f"{_base_url()}/call/{t['token']}" if t else ""


def _payment_nudges(conn):
    """Every 7 days a registered client has not paid, the Guide gets a nudge. Sending the reminder is the Guide's choice."""
    rows = conn.execute(
        """SELECT r.id, r.claimed_by, r.reserved_at, r.pay_nudge_at, r.contact_id, r.reserve_cohort_id, c.first_name
           FROM call_requests r JOIN contacts c ON c.id = r.contact_id
           WHERE r.reserve_result = 'Enrolled' AND r.claimed_by IS NOT NULL AND r.reserve_cohort_id IS NOT NULL""").fetchall()
    week_ago = _ts(_utc_now() - timedelta(days=7))
    for r in rows:
        last = r["pay_nudge_at"] or r["reserved_at"]
        if not last or last > week_ago:
            continue
        enr = conn.execute("SELECT payment_completed_at AS p FROM enrollments WHERE contact_id = ? AND cohort_id = ?",
                           (r["contact_id"], r["reserve_cohort_id"])).fetchone()
        if not enr or enr["p"]:
            continue
        vol = conn.execute("SELECT id, name, email, push_user_key FROM call_volunteers WHERE id = ?", (r["claimed_by"],)).fetchone()
        if not vol or not vol["email"]:
            continue
        got = conn.execute("UPDATE call_requests SET pay_nudge_at = ? WHERE id = ? AND COALESCE(pay_nudge_at, '') = COALESCE(?, '')",
                           (_ts(_utc_now()), r["id"], r["pay_nudge_at"]))
        conn.commit()
        if got.rowcount == 1:
            _milestone_mail(vol, f"{r['first_name']} has not paid yet",
                            f"Hi {vol['name'].split()[0]},",
                            f"{r['first_name']} reserved a seat but payment has not arrived. A friendly reminder may help, and it is your call. "
                            f"Open your page for them and tap the payment reminder: {_page_link(conn, r['id'], vol['id'])}")


def _milestone_mail(vol, subject, hello, body_html):
    plain = body_html.replace("<strong>", "").replace("</strong>", "")
    try:
        push(vol["push_user_key"], subject, plain, high=False)
    except Exception:
        pass
    try:
        _send(vol["email"], subject, f"<p>{hello}</p><p>{body_html}</p><p>Warmly,<br>The Discovery! Team</p>",
              f"{hello}\n\n{plain}\n\nWarmly,\nThe Discovery! Team", to_name=vol["name"])
    except Exception as e:
        print(f"Couldn't send a milestone note to {vol['email']}: {e}", flush=True)


# ---------------------------------------------------------------- routes
def register(app, crm, leadership_required, get_db, guides_required=None):
    guides_required = guides_required or leadership_required
    @app.context_processor
    def _inject():
        now = time.time()
        if now - _programs_cache["at"] > 300:
            try:
                conn = get_db()
                _programs_cache["rows"] = [dict(code=r["code"], name=r["name"]) for r in
                                           conn.execute("SELECT code, name FROM programs ORDER BY id").fetchall()]
                conn.close()
                _programs_cache["at"] = now
            except Exception:
                pass
        return {"call_form_programs": _programs_cache["rows"], "call_consent_question": CONSENT_QUESTION, "call_consent_fine": CONSENT_FINE, "call_consent_options": CONSENT_OPTIONS}

    @app.route("/talk-to-us", methods=["POST"])
    def public_talk_to_us():
        ok, yes, err = create_interest(get_db, request.form, "Have someone call you")
        if not ok:
            flash(err)
            return redirect(request.referrer or url_for("public_home"))
        return redirect(url_for("public_talk_thanks", c=yes or "email"))

    @app.route("/talk-to-us/thanks")
    def public_talk_thanks():
        c = request.args.get("c", "")
        c = LEGACY.get(c, c)
        return render_template("public_talk_thanks.html", pref=c if c in PREF_SHORT else "either",
                               yes=(c in PREF_WORD), pw=PREF_WORD.get(c, "call or text"))

    @app.route("/cep-letters")
    def public_cep_letters():
        return render_template("public_cep_letters.html", letters=CLIENT_LETTERS, current=None)

    @app.route("/cep-letters/<key>")
    def public_cep_letter(key):
        if key in ("q-rt", "q-d1"):
            fake = {"first_name": "[First name]", "program_name": ("D1 – The Beginning" if key == "q-d1" else "Relationship Training"), "session_date": None,
                    "questionnaire_completed_at": None, "code": ("D1" if key == "q-d1" else "D4"), "first_name": "[First name]"}
            return render_template("public_questionnaire.html", enr=fake, profile=None, is_couples=True, done=False,
                                   saved=False, preview=True, letters=CLIENT_LETTERS, key=key)
        got = sample_letter(key)
        if not got:
            abort(404)
        title, when, subject, html = got
        return render_template("public_cep_letters.html", letters=CLIENT_LETTERS, current=key, title=title, when=when,
                               subject=subject, letter_html=html)

    @app.route("/cep-training")
    def public_cep_training():
        """The Guides' how-to guide. Not linked from the public site; the team reaches it from their call page."""
        return render_template("public_cep_training.html")

    @app.route("/cep-permission/<token>", methods=["GET", "POST"])
    def public_cep_permission(token):
        """A volunteer's one-time permission to share their name, cell phone and email."""
        ensure_tables(get_db)
        conn = get_db()
        try:
            vol = conn.execute("SELECT * FROM call_volunteers WHERE consent_token = ? AND active = 1", (token or "",)).fetchone()
            if not vol:
                abort(404)
            error = None
            if request.method == "POST" and not vol["consent_at"]:
                typed = (request.form.get("full_name") or "").strip()
                if not request.form.get("agree"):
                    error = "Please tick the box to give your permission."
                elif len(typed) < 3:
                    error = "Please type your full name to sign."
                else:
                    ip = (request.headers.get("X-Forwarded-For", "") or request.remote_addr or "").split(",")[0].strip()
                    conn.execute("UPDATE call_volunteers SET consent_at = ?, consent_name = ?, consent_ip = ?, consent_text = ? WHERE id = ?",
                                 (_ts(_utc_now()), typed[:120], ip, VOLUNTEER_CONSENT, vol["id"]))
                    conn.commit()
                    return redirect(url_for("public_cep_permission", token=token))
            vol = conn.execute("SELECT * FROM call_volunteers WHERE id = ?", (vol["id"],)).fetchone()
            return render_template("public_cep_permission.html", vol=vol, wording=VOLUNTEER_CONSENT, error=error,
                                   phone=pretty_phone(vol["cell_phone"]), given_text=local_text(vol["consent_at"]))
        finally:
            conn.close()

    # ----- Discovery volunteers: share a link, a friend joins, and gets a page of their own
    def _helper_for_contact(conn, contact_id, referred_by=None, matched_by=None):
        h = conn.execute("SELECT * FROM volunteer_helpers WHERE contact_id = ?", (contact_id,)).fetchone()
        if h:
            return h, False
        tok = secrets.token_urlsafe(18)
        conn.execute("INSERT INTO volunteer_helpers (contact_id, token, referred_by, matched_by, created_at) VALUES (?, ?, ?, ?, ?)",
                     (contact_id, tok, referred_by, matched_by, _ts(_utc_now())))
        return conn.execute("SELECT * FROM volunteer_helpers WHERE contact_id = ?", (contact_id,)).fetchone(), True

    def _match_contact(conn, first, last, email, phone):
        """(contact_id, how) \u2014 by email first (safe to treat as the same person), then by cell number plus a matching first name."""
        row = conn.execute("SELECT id FROM contacts WHERE lower(email) = lower(?) OR lower(email_2) = lower(?) OR lower(email_3) = lower(?) ORDER BY id LIMIT 1",
                           (email, email, email)).fetchone()
        if row:
            return row["id"], "email"
        d = _digits(phone)
        d = d[1:] if len(d) == 11 and d.startswith("1") else d
        if len(d) == 10:
            rows = conn.execute("SELECT id, first_name, last_name, cell_phone, home_phone, work_phone FROM contacts "
                                "WHERE cell_phone IS NOT NULL OR home_phone IS NOT NULL OR work_phone IS NOT NULL ORDER BY id").fetchall()
            for r in rows:
                for ph in (r["cell_phone"], r["home_phone"], r["work_phone"]):
                    pd = _digits(ph)
                    pd = pd[1:] if len(pd) == 11 and pd.startswith("1") else pd
                    if pd == d and _same_first(r["first_name"], first):
                        return r["id"], "cell"
        return None, None

    @app.route("/volunteer-helper/join", methods=["GET", "POST"])
    def public_helper_join():
        ensure_tables(get_db)
        ref = (request.values.get("ref") or "").strip()
        error = None
        if request.method == "POST":
            f = request.form
            if f.get("website"):                      # hidden spam-trap field
                return redirect(url_for("public_helper_thanks"))
            first = (f.get("first_name") or "").strip()[:80]
            last = (f.get("last_name") or "").strip()[:80] or None
            email = (f.get("email") or "").strip()[:200]
            phone = (f.get("phone") or "").strip()[:40]
            if not first or "@" not in email or "." not in email.split("@")[-1]:
                error = "Please enter your first name and a valid email address."
            elif phone and len(_digits(phone)) < 10:
                error = "That cell number looks too short. Please include the area code, or leave it blank."
            if not error:
                conn = get_db()
                try:
                    referrer = None
                    if ref:
                        r = conn.execute("SELECT * FROM volunteer_helpers WHERE token = ?", (ref,)).fetchone()
                        referrer = r
                        # a limit on how many people one volunteer can bring in per day (spam guard)
                        if r:
                            n = conn.execute("SELECT COUNT(*) AS n FROM volunteer_helpers WHERE referred_by = ? AND created_at >= ?",
                                             (r["contact_id"], _ts(_utc_now() - timedelta(hours=24)))).fetchone()["n"]
                            if n >= HELPER_DAILY_LIMIT:
                                error = "A lot of people have joined from this link today. Please try again tomorrow."
                    if not error:
                        cid, how = _match_contact(conn, first, last, email, phone)
                        returning = bool(cid)
                        note = f"Volunteer helper sign-up {_ts(_utc_now())[:10]}"
                        if referrer:
                            rc = conn.execute("SELECT first_name, last_name FROM contacts WHERE id = ?", (referrer["contact_id"],)).fetchone()
                            note += f", shared by {rc['first_name']} {rc['last_name'] or ''}".rstrip()
                        if not cid:
                            cur = conn.execute("""INSERT INTO contacts (first_name, last_name, email, cell_phone, notes, marketing_source, status)
                                                  VALUES (?, ?, ?, ?, ?, ?, ?)""",
                                               (first, last, email, phone or None, note, "Volunteer referral" if referrer else "Volunteer sign-up", "Interested Party"))
                            cid, how = cur.lastrowid, "new"
                        else:
                            _add_note(conn, cid, note + ("" if how == "email" else f" (matched by cell number; they typed {email})"))
                        ref_cid = referrer["contact_id"] if referrer and referrer["contact_id"] != cid else None
                        helper, created = _helper_for_contact(conn, cid, ref_cid, how)
                        add_to_list(conn, cid, RESPONDED_LIST, "Responded to the Excitement blast (volunteer sign-up link)")
                        if ref_cid and created is False and not helper["referred_by"]:
                            conn.execute("UPDATE volunteer_helpers SET referred_by = ? WHERE id = ?", (ref_cid, helper["id"]))
                        # The welcome note goes ONLY to the email they typed, and the contact page link is included only
                        # when that email is already on the contact (otherwise anyone could open someone else's page).
                        profile_link = None
                        if how == "email":
                            pc = conn.execute("SELECT profile_token FROM contacts WHERE id = ?", (cid,)).fetchone()
                            tok = pc["profile_token"] if pc else None
                            if not tok:
                                tok = secrets.token_urlsafe(24)
                                conn.execute("UPDATE contacts SET profile_token = ? WHERE id = ?", (tok, cid))
                            profile_link = _base_url() + url_for("public_complete_profile", token=tok)
                        due = not helper["welcome_sent_at"] or _parse(helper["welcome_sent_at"]) < _utc_now() - timedelta(hours=1)
                        conn.commit()
                        if due and alerts_live():
                            subject, html, text = letter_helper_welcome(first, f"{_base_url()}/volunteer/{helper['token']}",
                                                                        profile_link, returning=returning and how == "email")
                            try:
                                _send(email, subject, html, text, to_name=first)
                                conn.execute("UPDATE volunteer_helpers SET welcome_sent_at = ? WHERE id = ?", (_ts(_utc_now()), helper["id"]))
                                conn.commit()
                            except Exception as e:
                                print(f"Couldn't email the volunteer welcome to {email}: {e}", flush=True)
                        return redirect(url_for("public_helper_thanks"))
                except Exception as e:
                    conn.rollback()
                    print(f"Volunteer join failed: {e}", flush=True)
                    error = "Sorry, something went wrong on our end. Please try again in a moment."
                finally:
                    conn.close()
        return render_template("public_helper_join.html", error=error, ref=ref, form=request.form)

    @app.route("/volunteer-helper/thanks")
    def public_helper_thanks():
        return render_template("public_helper_thanks.html")

    @app.route("/volunteer/<token>")
    def public_helper_page(token):
        ensure_tables(get_db)
        conn = get_db()
        try:
            h = conn.execute("SELECT * FROM volunteer_helpers WHERE token = ?", (token or "",)).fetchone()
            if not h:
                abort(404)
            c = conn.execute("SELECT first_name, last_name, profile_token FROM contacts WHERE id = ?", (h["contact_id"],)).fetchone()
            conn.execute("UPDATE volunteer_helpers SET last_seen_at = ? WHERE id = ?", (_ts(_utc_now()), h["id"]))
            conn.commit()
            joined = conn.execute("SELECT c.first_name, c.last_name, v.created_at FROM volunteer_helpers v JOIN contacts c ON c.id = v.contact_id "
                                  "WHERE v.referred_by = ? ORDER BY v.id DESC", (h["contact_id"],)).fetchall()
            share = f"{_base_url()}/volunteer-helper/join?ref={token}"
            body = ("Hi, it's " + c["first_name"] + ". I volunteer with Discovery! and thought of you. "
                    "If you'd like to help too, tap here and it takes about a minute: " + share)
            profile = _base_url() + url_for("public_complete_profile", token=c["profile_token"]) if c["profile_token"] else None
            return render_template("public_helper_page.html", first=c["first_name"], share=share, sms_body=body,
                                   joined=[dict(name=(r["first_name"] + " " + (r["last_name"] or "")).strip(), when=(r["created_at"] or "")[:10]) for r in joined],
                                   profile=profile)
        finally:
            conn.close()

    # ----- the volunteer's personal link
    def _load(token):
        ensure_tables(get_db)
        conn = get_db()
        n = conn.execute("SELECT * FROM call_notices WHERE token = ?", (token,)).fetchone()
        if not n:
            conn.close()
            abort(404)
        req = conn.execute("SELECT r.*, c.first_name, c.last_name, c.email FROM call_requests r "
                           "JOIN contacts c ON c.id = r.contact_id WHERE r.id = ?", (n["request_id"],)).fetchone()
        vol = conn.execute("SELECT * FROM call_volunteers WHERE id = ?", (n["volunteer_id"],)).fetchone()
        claimer = None
        if req and req["claimed_by"]:
            claimer = conn.execute("SELECT name FROM call_volunteers WHERE id = ?", (req["claimed_by"],)).fetchone()
        return conn, n, req, vol, claimer

    @app.route("/call/<token>", methods=["GET", "POST"])
    def public_call_claim(token):
        conn, n, req, vol, claimer = _load(token)
        try:
            mine = bool(req and req["claimed_by"] == vol["id"])
            if mine and req["source"] == "sponsor":
                import sponsors
                me_c = conn.execute("SELECT * FROM contacts WHERE lower(email) = lower(?) ORDER BY id LIMIT 1", (vol["email"] or "",)).fetchone()
                if me_c is not None:
                    st = sponsors.profile_status(conn, me_c, _base_url())
                    if not st["complete"]:
                        return render_template("public_sponsor_wait.html", first=vol["name"].split()[0], link=st["link"], missing=st["missing"],
                                               who=f"{req['first_name']} {req['last_name'] or ''}".strip())
            if request.method == "POST" and req["status"] == "New" and vol["consent_at"]:
                res = conn.execute("UPDATE call_requests SET status = 'Claimed', claimed_by = ?, claimed_at = ? "
                                   "WHERE id = ? AND status = 'New'", (vol["id"], _ts(_utc_now()), req["id"]))
                conn.commit()
                if res.rowcount == 1:
                    req = conn.execute("SELECT r.*, c.first_name, c.last_name, c.email FROM call_requests r "
                                       "JOIN contacts c ON c.id = r.contact_id WHERE r.id = ?", (req["id"],)).fetchone()
                    _tell_prospect(conn, req, vol, _base_url())
                    conn.commit()
                    mine = True
                else:
                    req = conn.execute("SELECT r.*, c.first_name, c.last_name, c.email FROM call_requests r "
                                       "JOIN contacts c ON c.id = r.contact_id WHERE r.id = ?", (req["id"],)).fetchone()
                    claimer = conn.execute("SELECT name FROM call_volunteers WHERE id = ?", (req["claimed_by"],)).fetchone()
            link = sms_body = None
            if mine and req["outcome"] and not req["outcome"].startswith(("Not interested", "Wrong number")):
                link = reserve_link(conn, req, _base_url())
                sms_body = (f"Hi {req['first_name']}, it's {vol['name'].split()[0]} with Discovery! Here is your personal link "
                            f"to reserve your spot in {_program_label(req['program_code'])}: {link}")
            q = questionnaire_links(conn, req, _base_url()) if mine else {"person": None, "partner": None}
            q_body = (f"Hi {req['first_name']}, it's {vol['name'].split()[0]} with Discovery! Here is your personal link to the "
                      f"questionnaire. You can stop and come back to it any time by opening the same link: {q['person']}") if q["person"] else None
            cap = conn.execute("SELECT name, cell_phone FROM call_volunteers WHERE active = 1 AND program_code = 'CAPTAIN' ORDER BY id LIMIT 1").fetchone()
            prog = client_progress(conn, req, _base_url()) if mine else None
            vfirst = vol["name"].split()[0]
            extra = {}
            if prog and prog["profile_link"]:
                extra["longform"] = f"Hi {req['first_name']}, it's {vfirst} with Discovery! Please take a few minutes to complete your information (and add a photo) here: {prog['profile_link']}"
            if prog and prog["reserved"]:
                extra["payment"] = (f"Hi {req['first_name']}, it's {vfirst} with Discovery! Your seat is reserved. The next step is payment "
                                    f"($1,299 per couple). Call or text me at {pretty_phone(vol['cell_phone'])} and I'll walk you through it.")
                extra["payment_reminder"] = (f"Hi {req['first_name']}, it's {vfirst} with Discovery! A friendly reminder that your payment has "
                                             f"not come in yet. Your spot is held. Call or text me anytime if I can help.")
            return render_template("public_call_claim.html", req=req, vol=vol, mine=mine, claimer=claimer, prog=prog, extra_sms=extra, is_sponsor=(req["source"] == "sponsor"),
                                   captain=(dict(name=cap["name"], phone=pretty_phone(cap["cell_phone"])) if cap else None),
                                   link=link, sms_body=sms_body, q=q, q_body=q_body,
                                   need_permission=(not vol["consent_at"]),
                                   permission_url=(url_for("public_cep_permission", token=vol["consent_token"]) if vol["consent_token"] else None),
                                   label=_program_label(req["program_code"]), token=token,
                                   phone=pretty_phone(req["cell_phone"]), outcomes=OUTCOMES,
                                   pref=(req["contact_pref"] or "either"), pref_short=PREF_SHORT.get(req["contact_pref"] or "either"),
                                   tel=_digits(req["cell_phone"]),
                                   claimed_text=local_text(req["claimed_at"]))
        finally:
            conn.close()

    @app.route("/call/<token>/done", methods=["POST"])
    def public_call_done(token):
        conn, n, req, vol, claimer = _load(token)
        try:
            if req["claimed_by"] != vol["id"]:
                abort(403)
            outcome = request.form.get("outcome", "")
            note = (request.form.get("note") or "").strip()
            if outcome not in OUTCOMES:
                flash("Please choose how the call went.")
                return redirect(url_for("public_call_claim", token=token))
            keep_open = outcome.startswith(("No answer", "Texted", "Left a voicemail"))
            conn.execute("UPDATE call_requests SET outcome = ?, outcome_note = ?, status = ?, closed_at = ? WHERE id = ?",
                         (outcome, note or None, "Claimed" if keep_open else "Called",
                          None if keep_open else _ts(_utc_now()), req["id"]))
            line = f"Call log ({vol['name']}, {local_text(_ts(_utc_now()))}): {outcome}" + (f" – {note}" if note else "")
            cur_notes = conn.execute("SELECT notes FROM contacts WHERE id = ?", (req["contact_id"],)).fetchone()
            merged = ((cur_notes["notes"] + "\n") if cur_notes and cur_notes["notes"] else "") + line
            conn.execute("UPDATE contacts SET notes = ? WHERE id = ?", (merged, req["contact_id"]))
            conn.commit()
            flash("Thank you! Your call has been logged.")
            return redirect(url_for("public_call_claim", token=token))
        finally:
            conn.close()

    @app.route("/call/<token>/help", methods=["POST"])
    def public_call_help(token):
        """A Sponsor taps 'I need help speaking with them': the Guide Team Captain and Kent are told."""
        conn, n, req, vol, claimer = _load(token)
        try:
            if req["claimed_by"] != vol["id"] or req["source"] != "sponsor":
                abort(403)
            who = f"{req['first_name']} {req['last_name'] or ''}".strip()
            note = f"Help asked ({vol['name']}, {local_text(_ts(_utc_now()))}): Sponsor asked for an experienced volunteer to help speak with {who}."
            _add_note(conn, req["contact_id"], note)
            conn.commit()
            if sponsor_live():
                caps = conn.execute("SELECT name, email, push_user_key FROM call_volunteers WHERE active = 1 AND program_code = 'CAPTAIN' ORDER BY id").fetchall()
                subject = f"{vol['name']} needs help speaking with {who}"
                body = (f"<p>{vol['name']} ({pretty_phone(vol['cell_phone'])}, {vol['email']}) is sponsoring <strong>{who}</strong> "
                        f"and asked for an experienced volunteer to reach out to them. Please ask a Guide to call or text {vol['name'].split()[0]}.</p>")
                text = f"{vol['name']} ({pretty_phone(vol['cell_phone'])}, {vol['email']}) is sponsoring {who} and asked for an experienced volunteer to reach out to them."
                targets = [(c["name"], c["email"], c["push_user_key"]) for c in caps] + [("Kent", _leadership_email(), None)]
                for nm, em, pk in targets:
                    try:
                        if pk:
                            push(pk, subject, text, high=False)
                        _send(em, subject, body, text, to_name=nm)
                    except Exception as e:
                        print(f"Help request notice failed: {e}", flush=True)
            flash("Thank you. We have let the team know, and an experienced volunteer will reach out to you.")
            return redirect(url_for("public_call_claim", token=token))
        finally:
            conn.close()

    @app.route("/call/<token>/link-sent", methods=["POST"])
    def public_call_link_sent(token):
        """The volunteer tapped 'Text it from my phone' -- we note that the link went out."""
        conn, n, req, vol, claimer = _load(token)
        try:
            if req["claimed_by"] != vol["id"]:
                abort(403)
            conn.execute("UPDATE call_requests SET link_sent_at = COALESCE(link_sent_at, ?), link_sent_via = COALESCE(link_sent_via, 'text') "
                         "WHERE id = ?", (_ts(_utc_now()), req["id"]))
            conn.commit()
            return ("", 204)
        finally:
            conn.close()

    @app.route("/call/<token>/email-link", methods=["POST"])
    def public_call_email_link(token):
        conn, n, req, vol, claimer = _load(token)
        try:
            if req["claimed_by"] != vol["id"]:
                abort(403)
            if not alerts_live():
                flash("Email sending is switched off right now, so nothing was sent. Please use the text button.")
                return redirect(url_for("public_call_claim", token=token))
            if not req["email"]:
                flash("We don't have an email address for them. Please use the text button.")
                return redirect(url_for("public_call_claim", token=token))
            link = reserve_link(conn, req, _base_url())
            label = _program_label(req["program_code"])
            subject, html, text = letter_reserve_link(req["first_name"], label, link, vol["name"], pretty_phone(vol["cell_phone"]))
            try:
                _send(req["email"], subject, html, text, to_name=req["first_name"])
            except Exception as e:
                print(f"Couldn't email the reserve link for request {req['id']}: {e}", flush=True)
                flash("The email didn't go through. Please use the text button.")
                return redirect(url_for("public_call_claim", token=token))
            conn.execute("UPDATE call_requests SET link_sent_at = COALESCE(link_sent_at, ?), link_sent_via = COALESCE(link_sent_via, 'email') "
                         "WHERE id = ?", (_ts(_utc_now()), req["id"]))
            conn.commit()
            flash(f"Sent to {req['email']}.")
            return redirect(url_for("public_call_claim", token=token))
        finally:
            conn.close()

    @app.route("/call/<token>/send/<kind>", methods=["POST"])
    def public_call_send_letter(token, kind):
        """Guide taps 'Email it' for the profile, payment request or payment reminder; or 'sent by text' is noted."""
        conn, n, req, vol, claimer = _load(token)
        try:
            if req["claimed_by"] != vol["id"]:
                abort(403)
            cols = {"longform": ("guide_longform", "longform_sent_at"), "payment": ("guide_payment", "payment_sent_at"),
                    "payment_reminder": ("guide_payment_reminder", "payment_reminder_at")}
            if kind not in cols:
                abort(404)
            key, col = cols[kind]
            if request.form.get("via") == "text":
                conn.execute(f"UPDATE call_requests SET {col} = ? WHERE id = ?", (_ts(_utc_now()), req["id"]))
                conn.commit()
                return ("", 204)
            if not alerts_live():
                flash("Email sending is switched off right now, so nothing was sent. Please use the text button.")
                return redirect(url_for("public_call_claim", token=token))
            if not req["email"]:
                flash("We don't have an email address for them. Please use the text button.")
                return redirect(url_for("public_call_claim", token=token))
            prog = client_progress(conn, req, _base_url())
            link = prog["profile_link"] if kind == "longform" else None
            if kind == "longform" and not link:
                flash("Their form link isn't ready yet. Please use the text button or try again later.")
                return redirect(url_for("public_call_claim", token=token))
            from email_templates import guide_letter_content
            subject, html, text = guide_letter_content(key, req["first_name"], _program_label(req["program_code"]), vol["name"],
                                                       pretty_phone(vol["cell_phone"]), link=link)
            try:
                _send(req["email"], subject, html, text, to_name=req["first_name"])
            except Exception as e:
                print(f"Couldn't email {kind} for request {req['id']}: {e}", flush=True)
                flash("The email didn't go through. Please use the text button.")
                return redirect(url_for("public_call_claim", token=token))
            conn.execute(f"UPDATE call_requests SET {col} = ? WHERE id = ?", (_ts(_utc_now()), req["id"]))
            conn.commit()
            flash(f"Sent to {req['email']}.")
            return redirect(url_for("public_call_claim", token=token))
        finally:
            conn.close()

    @app.route("/call/<token>/questionnaire-sent", methods=["POST"])
    def public_call_q_sent(token):
        conn, n, req, vol, claimer = _load(token)
        try:
            if req["claimed_by"] != vol["id"]:
                abort(403)
            conn.execute("UPDATE call_requests SET questionnaire_sent_at = COALESCE(questionnaire_sent_at, ?), "
                         "questionnaire_sent_via = COALESCE(questionnaire_sent_via, 'text') WHERE id = ?", (_ts(_utc_now()), req["id"]))
            conn.commit()
            return ("", 204)
        finally:
            conn.close()

    @app.route("/call/<token>/email-questionnaire", methods=["POST"])
    def public_call_email_questionnaire(token):
        conn, n, req, vol, claimer = _load(token)
        try:
            if req["claimed_by"] != vol["id"]:
                abort(403)
            if not alerts_live():
                flash("Email sending is switched off right now, so nothing was sent. Please use the text button.")
                return redirect(url_for("public_call_claim", token=token))
            q = questionnaire_links(conn, req, _base_url())
            if not q["person"]:
                flash("They need to reserve a date first, then the questionnaire link is ready.")
                return redirect(url_for("public_call_claim", token=token))
            label = _program_label(req["program_code"])
            sent_to = []
            targets = [(req["first_name"], req["email"], q["person"])]
            if q["partner"] and q["partner"]["email"]:
                targets.append((q["partner"]["first"], q["partner"]["email"], q["partner"]["link"]))
            for first, addr, link in targets:
                if not addr or not link:
                    continue
                subject, html, text = letter_questionnaire(first, label, link, vol["name"], pretty_phone(vol["cell_phone"]))
                try:
                    _send(addr, subject, html, text, to_name=first)
                    sent_to.append(addr)
                except Exception as e:
                    print(f"Couldn't email questionnaire link for request {req['id']} to {addr}: {e}", flush=True)
            if not sent_to:
                flash("The email didn't go through. Please use the text button.")
            else:
                conn.execute("UPDATE call_requests SET questionnaire_sent_at = COALESCE(questionnaire_sent_at, ?), "
                             "questionnaire_sent_via = COALESCE(questionnaire_sent_via, 'email') WHERE id = ?", (_ts(_utc_now()), req["id"]))
                conn.commit()
                flash("Sent to " + " and ".join(sent_to) + ".")
            return redirect(url_for("public_call_claim", token=token))
        finally:
            conn.close()

    # ----- the person's own Reserve page (opened from the volunteer's link)
    @app.route("/reserve/<token>", methods=["GET", "POST"])
    def public_reserve(token):
        ensure_tables(get_db)
        conn = get_db()
        req = conn.execute("SELECT r.*, c.first_name, c.last_name, c.email, c.cell_phone AS cphone FROM call_requests r "
                           "JOIN contacts c ON c.id = r.contact_id WHERE r.reserve_token = ?", (token,)).fetchone()
        if not req:
            conn.close()
            abort(404)
        code = req["program_code"] or ""
        prog = conn.execute("SELECT name FROM programs WHERE code = ?", (code,)).fetchone()
        sessions = []
        if prog:
            for c in conn.execute("""SELECT c.*, p.code FROM cohorts c JOIN programs p ON p.id = c.program_id
                                     WHERE p.code = ? AND COALESCE(c.end_date, c.session_date) >= date('now')
                                       AND c.status != 'Cancelled' ORDER BY c.session_date""", (code,)).fetchall():
                cap = capacity_of(c, code)
                full = cap is not None and seats_used(conn, c["id"], code) >= cap
                sessions.append(dict(id=c["id"], text=span_text(c) + (f" \u2013 {_loc(c)}" if _loc(c) else ""), full=full))
        def render(**kw):
            base = dict(req=req, token=token, label=_program_label(code) if code else "Discovery!", couple=(code in COUPLE_PROGRAMS),
                        sessions=sessions, result=None, vals={}, done_session=None)
            base.update(kw)
            return render_template("public_reserve.html", **base)
        try:
            if req["reserve_result"]:
                c = next((x for x in sessions if x["id"] == req["reserve_cohort_id"]), None)
                row = conn.execute("SELECT c.*, p.code FROM cohorts c JOIN programs p ON p.id = c.program_id WHERE c.id = ?",
                                   (req["reserve_cohort_id"],)).fetchone() if req["reserve_cohort_id"] else None
                return render(result=req["reserve_result"], done_session=span_text(row) if row else "")
            if request.method == "POST":
                f = request.form
                person = dict(first=(f.get("first_name") or "").strip(), last=(f.get("last_name") or "").strip(),
                              email=(f.get("email") or "").strip(), phone=(f.get("phone") or "").strip())
                partner = dict(first=(f.get("partner_first") or "").strip(), last=(f.get("partner_last") or "").strip(),
                               email=(f.get("partner_email") or "").strip())
                cohort_id = f.get("cohort_id", type=int)
                err = None
                if not person["first"] or not person["last"] or not person["email"]:
                    err = "Please fill in your first name, last name and email."
                elif len(_digits(person["phone"])) < 10:
                    err = "Please enter your cell phone number."
                elif not cohort_id or cohort_id not in [x["id"] for x in sessions]:
                    err = "Please choose a date."
                elif code in COUPLE_PROGRAMS and (not partner["first"] or not partner["email"]):
                    err = "Please tell us your partner's name and email, since this training is for couples."
                if err:
                    flash(err)
                    return render(vals=dict(person, **{"partner_first": partner["first"], "partner_last": partner["last"],
                                                       "partner_email": partner["email"], "cohort_id": cohort_id}))
                conn.close()
                result, coh, msg = reserve_seat(get_db, req["id"], cohort_id, person, partner)
                if result in ("Error", "Already"):
                    flash(msg or "You are already registered for that date. Thank you!")
                    return redirect(url_for("public_reserve", token=token))
                return redirect(url_for("public_reserve", token=token))
            return render(vals=dict(first=req["first_name"], last=req["last_name"] or "", email=req["email"] or "",
                                    phone=pretty_phone(req["cphone"] or req["cell_phone"])))
        finally:
            try:
                conn.close()
            except Exception:
                pass

    # ----- CRM: the queue and the volunteer lists (Leadership)
    @crm.route("/call-requests")
    @leadership_required
    def call_requests_queue():
        ensure_tables(get_db)
        conn = get_db()
        rows = conn.execute(
            """SELECT r.*, c.first_name, c.last_name, c.email, v.name AS vol_name
               FROM call_requests r JOIN contacts c ON c.id = r.contact_id
               LEFT JOIN call_volunteers v ON v.id = r.claimed_by
               ORDER BY r.id DESC LIMIT 200""").fetchall()
        items = []
        now = _utc_now()
        for r in rows:
            d = dict(r)
            d["label"] = _program_label(r["program_code"])
            d["pref"] = PREF_SHORT.get(r["contact_pref"] or "either")
            d["when"] = local_text(r["created_at"])
            d["phone_pretty"] = pretty_phone(r["cell_phone"])
            d["claimed_when"] = local_text(r["claimed_at"])
            d["waiting_hours"] = round((now - _parse(r["created_at"])).total_seconds() / 3600, 1)
            d["overdue"] = r["status"] in ("New", "Claimed") and d["waiting_hours"] > WINDOW_HOURS
            d["others"] = ([v for v in _pool(conn, r["program_code"]) if v["id"] != r["claimed_by"]]
                           if r["status"] == "Claimed" else [])
            items.append(d)
        pools = {c: conn.execute("SELECT COUNT(*) c FROM call_volunteers WHERE active = 1 AND program_code = ?", (c,)).fetchone()["c"]
                 for c, _ in POOLS}
        conn.close()
        return render_template("call_requests.html", items=items, live=alerts_live(), pools=pools, pool_list=POOLS,
                               in_hours=in_send_hours())

    @crm.route("/call-requests/<int:request_id>/resend", methods=["POST"])
    @leadership_required
    def call_request_resend(request_id):
        status = dispatch(get_db, request_id, _base_url(), force=True)
        flash(f"Alert check: {status}.")
        return redirect(url_for(".call_requests_queue"))

    @crm.route("/call-requests/<int:request_id>/reassign", methods=["POST"])
    @guides_required
    def call_request_reassign(request_id):
        """Hand a claimed request to a different Guide. The new Guide gets their own link by email."""
        ensure_tables(get_db)
        conn = get_db()
        try:
            req = conn.execute("SELECT r.*, c.first_name, c.last_name FROM call_requests r JOIN contacts c ON c.id = r.contact_id "
                               "WHERE r.id = ?", (request_id,)).fetchone()
            vid = request.form.get("volunteer_id", type=int)
            vol = conn.execute("SELECT * FROM call_volunteers WHERE id = ? AND active = 1", (vid,)).fetchone() if vid else None
            if not req or req["status"] != "Claimed" or not vol:
                flash("That request can't be handed over (it must be claimed, and the Guide must be active).")
                return redirect(url_for(".call_requests_queue"))
            old = conn.execute("SELECT name FROM call_volunteers WHERE id = ?", (req["claimed_by"],)).fetchone()
            conn.execute("UPDATE call_requests SET claimed_by = ?, claimed_at = ? WHERE id = ? AND status = 'Claimed'",
                         (vol["id"], _ts(_utc_now()), request_id))
            token = _notice_for(conn, request_id, vol["id"])
            conn.commit()
            url = f"{_base_url()}/call/{token}"
            who = f"{req['first_name']} {(req['last_name'] or '')[:1]}.".replace(" .", "")
            label = _program_label(req["program_code"])
            first = vol["name"].split()[0]
            sent = False
            if alerts_live():
                try:
                    _send(vol["email"], f"{who} is now yours to follow up with \u2013 {label}",
                          f"<p>Hi {first},</p><p>{who} asked to be reached about <strong>{label}</strong>"
                          f"{(' and was being helped by ' + old['name']) if old else ''}. You are now their Guide. "
                          f"Open your page to see the details, log your call and send the next link:<br><a href=\"{url}\">{url}</a></p>",
                          f"Hi {first},\n\n{who} asked to be reached about {label}. You are now their Guide. Your page:\n{url}",
                          to_name=vol["name"])
                    sent = True
                except Exception as e:
                    print(f"Hand-over email failed: {e}", flush=True)
            msg = f"{who} is now with {vol['name']}" + (f" (was {old['name']})." if old else ".")
            msg += " They were emailed their link." if sent else f" No email was sent (sending is off or it failed); give them this link: {url}"
            msg += " Note: the person was already told the first Guide's name."
            flash(msg)
        finally:
            conn.close()
        return redirect(url_for(".call_requests_queue"))

    @crm.route("/call-requests/<int:request_id>/close", methods=["POST"])
    @leadership_required
    def call_request_close(request_id):
        conn = get_db()
        conn.execute("UPDATE call_requests SET status = 'Closed', closed_at = ? WHERE id = ?", (_ts(_utc_now()), request_id))
        conn.commit()
        conn.close()
        return redirect(url_for(".call_requests_queue"))

    @crm.route("/call-requests/check-now", methods=["POST"])
    @leadership_required
    def call_requests_check_now():
        sweep(get_db, _base_url())
        flash("Checked for requests that need an alert or a reminder.")
        return redirect(url_for(".call_requests_queue"))

    @crm.route("/interest-report")
    @leadership_required
    def interest_report():
        ensure_tables(get_db)
        days = request.args.get("days", type=int) or 0
        conn = get_db()
        since = _ts(_utc_now() - timedelta(days=days)) if days else "0000-00-00 00:00:00"
        rows = conn.execute("SELECT * FROM interest_log WHERE created_at >= ? ORDER BY id", (since,)).fetchall()
        reached = {r["contact_id"]: r for r in conn.execute(
            "SELECT contact_id, status FROM call_requests WHERE status = 'Called'").fetchall()}
        sent_to, reserved_to, wait_to = set(), set(), set()
        for r in conn.execute("SELECT contact_id, program_code, link_sent_at, reserve_result FROM call_requests").fetchall():
            key = (r["contact_id"], r["program_code"])
            if r["link_sent_at"] or r["reserve_result"]:
                sent_to.add(key)
            if r["reserve_result"] == "Enrolled":
                reserved_to.add(key)
            if r["reserve_result"] == "Waitlist":
                wait_to.add(key)
        enrolled = set()
        for e in conn.execute("""SELECT en.contact_id, p.code FROM enrollments en JOIN cohorts c ON c.id = en.cohort_id
                                  JOIN programs p ON p.id = c.program_id""").fetchall():
            enrolled.add((e["contact_id"], e["code"]))
        names = {r["code"]: r["name"] for r in conn.execute("SELECT code, name FROM programs").fetchall()}
        conn.close()

        def blank():
            return dict(total=0, yes=0, no=0, reached=0, sent=0, reserved=0, wait=0, enrolled=0)

        def add(d, r):
            d["total"] += 1
            pref = LEGACY.get(r["call_ok"], r["call_ok"])
            d["yes"] += pref in PREF_WORD
            d["no"] += pref == "email"
            if pref in PREF_SHORT:
                d.setdefault("prefs", {})[pref] = d.setdefault("prefs", {}).get(pref, 0) + 1
            d["reached"] += r["contact_id"] in reached
            k = (r["contact_id"], r["program_code"])
            d["sent"] += k in sent_to
            d["reserved"] += k in reserved_to
            d["wait"] += k in wait_to
            d["enrolled"] += k in enrolled

        by_prog, by_page, by_day, total = {}, {}, {}, blank()
        for r in rows:
            add(total, r)
            add(by_prog.setdefault(r["program_code"] or "Not sure yet", blank()), r)
            add(by_page.setdefault(PAGES.get(r["page"], "Other"), blank()), r)
            add(by_day.setdefault(local_text(r["created_at"]).split(",")[0], blank()), r)
        prog_rows = sorted(((k, (f"{k} \u2013 {names[k]}" if k in names else k), v) for k, v in by_prog.items()),
                           key=lambda x: -x[2]["total"])
        pref_rows = [(PREF_SHORT[k], total.get("prefs", {}).get(k, 0)) for k in ("either", "call", "text", "email")]
        return render_template("interest_report.html", total=total, pref_rows=pref_rows, prog_rows=prog_rows,
                               page_rows=sorted(by_page.items(), key=lambda x: -x[1]["total"]),
                               day_rows=list(by_day.items())[-14:][::-1], days=days)

    @crm.route("/call-volunteers/people")
    @guides_required
    def call_volunteer_people():
        """Type-ahead / browse list for choosing a volunteer: team members first, then anyone in Contacts."""
        from flask import jsonify
        q = (request.args.get("q") or "").strip().lower()
        mode = request.args.get("mode", "team")          # team | all
        prog = (request.args.get("prog") or "").upper()  # limit team to people who served on this program
        conn = get_db()
        served = {}   # contact_id -> list of (session_date, code, role)
        for r in conn.execute("""SELECT cs.contact_id, cs.role, c.session_date, p.code FROM cohort_staffing cs
                                  JOIN cohorts c ON c.id = cs.cohort_id JOIN programs p ON p.id = c.program_id
                                  WHERE cs.role <> 'Trainee'""").fetchall():
            served.setdefault(r["contact_id"], []).append((str(r["session_date"] or ""), r["code"], r["role"]))
        for r in conn.execute("""SELECT sg.contact_id, sg.role, c.session_date, p.code FROM small_group_staffing sg
                                  JOIN small_groups g ON g.id = sg.small_group_id JOIN cohorts c ON c.id = g.cohort_id
                                  JOIN programs p ON p.id = c.program_id""").fetchall():
            served.setdefault(r["contact_id"], []).append((str(r["session_date"] or ""), r["code"], r["role"]))
        for r in conn.execute("SELECT contact_id FROM staff WHERE contact_id IS NOT NULL AND active = 1").fetchall():
            served.setdefault(r["contact_id"], [])
        used = {r["contact_id"] if False else r["email"].lower() for r in conn.execute(
            "SELECT email FROM call_volunteers WHERE active = 1").fetchall()}
        cols = "id, first_name, last_name, email, cell_phone"
        if mode == "team":
            ids = [i for i, v in served.items() if not prog or any(x[1] == prog for x in v)]
            rows = []
            for i in ids:
                r = conn.execute(f"SELECT {cols} FROM contacts WHERE id = ?", (i,)).fetchone()
                if r:
                    rows.append(r)
        else:
            if len(q) < 2:
                conn.close()
                return jsonify([])
            rows = conn.execute(f"SELECT {cols} FROM contacts ORDER BY last_name, first_name LIMIT 5000").fetchall()
        conn.close()
        toks = q.split()
        out = []
        for r in rows:
            name = f"{r['first_name'] or ''} {r['last_name'] or ''}".strip()
            hay = " ".join([name.lower(), (r["email"] or "").lower(), _digits(r["cell_phone"])])
            if toks and not all(t in hay or (_digits(t) and _digits(t) in hay) for t in toks):
                continue
            hist = sorted(served.get(r["id"], []), reverse=True)
            last = f"{hist[0][2]}, {hist[0][1]} {hist[0][0][:7]}" if hist else ""
            out.append(dict(id=r["id"], name=name, cell=pretty_phone(r["cell_phone"]) if r["cell_phone"] else "",
                            email=r["email"] or "", team=r["id"] in served, last=last, sessions=len(hist),
                            sort=(hist[0][0] if hist else ""), already=(r["email"] or "").lower() in used))
        out.sort(key=lambda x: (not x["team"], "".join(chr(255 - ord(c)) for c in x["sort"]), x["name"].lower()))
        return jsonify(out[:60])

    @crm.route("/call-volunteers/<int:vid>/email-training", methods=["POST"])
    @leadership_required
    def call_volunteer_email_training(vid):
        """Emails the whole Guide Training (all modules) to one Guide. Sent right away; deliberate click by Leadership."""
        import re as _re
        ensure_tables(get_db)
        conn = get_db()
        try:
            v = conn.execute("SELECT id, name, email FROM call_volunteers WHERE id = ? AND active = 1", (vid,)).fetchone()
            back = request.form.get("back") or url_for(".call_volunteers_page")
            if not v or not (v["email"] or "").strip():
                flash("That Guide has no email address on file.")
                return redirect(back)
            base = _base_url()
            body = render_template("_guide_training_body.html", email_mode=True)
            body = body.replace('src="/static', f'src="{base}/static').replace('href="/', f'href="{base}/')
            body = _re.sub(r'class="cep-mod[^"]*"', 'style="border-top:2px solid #e3e8ee; padding:16px 0"', body)
            body = _re.sub(r'class="(goal|muted|cep-top)"', '', body)
            first = v["name"].split()[0]
            html = (f"<p>Hi {first},</p><p>Here is the complete Guide Training for Discovery!, so you can read it at your own pace. "
                    f"You can also open it any time here: <a href=\"{base}/cep-training\">{base}/cep-training</a>.</p>{body}"
                    f"<p>Warmly,<br>The Discovery! Team</p>")
            text = _re.sub(r"<[^>]+>", "", _re.sub(r"</(p|li|h3|h4|div)>", "\n", html))
            text = _re.sub(r"\n{3,}", "\n\n", text)
            try:
                _send(v["email"], "Your Discovery! Guide Training", html, text, to_name=v["name"])
            except Exception as e:
                print(f"Couldn't email the Guide Training to {v['email']}: {e}", flush=True)
                flash("The email didn't go through. Please try again in a moment.")
                return redirect(back)
            flash(f"The Guide Training was emailed to {v['name']} ({v['email']}).")
            return redirect(back)
        finally:
            conn.close()

    @crm.route("/call-volunteers", methods=["GET", "POST"])
    @guides_required
    def call_volunteers_page():
        ensure_tables(get_db)
        conn = get_db()
        if request.method == "POST":
            action = request.form.get("action")
            if action == "add":
                code = request.form.get("program_code", "")
                name = (request.form.get("name") or "").strip()
                phone = (request.form.get("cell_phone") or "").strip()
                email = (request.form.get("email") or "").strip()
                have = conn.execute("SELECT COUNT(*) c FROM call_volunteers WHERE active = 1 AND program_code = ?", (code,)).fetchone()["c"]
                if code not in dict(POOLS):
                    flash("Choose a program.")
                elif not (name and email and len(_digits(phone)) >= 10):
                    flash("Please enter a name, a cell phone number, and an email.")
                elif have >= max_for(code):
                    flash(f"That group already has {max_for(code)}. Remove one first.")
                else:
                    conn.execute("INSERT INTO call_volunteers (program_code, name, cell_phone, email) VALUES (?, ?, ?, ?)",
                                 (code, name, phone, email))
                    conn.commit()
                    flash(f"Added {name}.")
            elif action == "add_contact":
                code = request.form.get("program_code", "")
                ct = conn.execute("SELECT id, first_name, last_name, email, cell_phone FROM contacts WHERE id = ?",
                                  (request.form.get("contact_id", type=int),)).fetchone()
                phone = (request.form.get("cell_phone") or (ct["cell_phone"] if ct else "") or "").strip()
                email = (request.form.get("email") or (ct["email"] if ct else "") or "").strip()
                have = conn.execute("SELECT COUNT(*) c FROM call_volunteers WHERE active = 1 AND program_code = ?", (code,)).fetchone()["c"]
                if not ct or code not in dict(POOLS):
                    flash("Choose a person and a program.")
                elif len(_digits(phone)) < 10 or not email:
                    flash("That contact needs a cell phone and an email. Enter them below the name and try again.")
                elif have >= max_for(code):
                    flash(f"That group already has {max_for(code)}. Remove one first.")
                else:
                    name = f"{ct['first_name']} {ct['last_name'] or ''}".strip()
                    conn.execute("INSERT INTO call_volunteers (program_code, name, cell_phone, email) VALUES (?, ?, ?, ?)",
                                 (code, name, phone, email))
                    if not ct["cell_phone"]:
                        conn.execute("UPDATE contacts SET cell_phone = ? WHERE id = ?", (phone, ct["id"]))
                    if not ct["email"]:
                        conn.execute("UPDATE contacts SET email = ? WHERE id = ?", (email, ct["id"]))
                    conn.commit()
                    flash(f"Added {name}.")
            elif action == "clear_consent":
                pid = request.form.get("id", type=int)
                conn.execute("UPDATE call_volunteers SET consent_at = NULL, consent_name = NULL, consent_ip = NULL, consent_text = NULL WHERE id = ?", (pid,))
                conn.commit()
                conn.close()
                return redirect(url_for(".call_volunteers_page", pid=pid, pm="consent_cleared") + f"#v{pid}")
            elif action == "remove":
                conn.execute("UPDATE call_volunteers SET active = 0 WHERE id = ?", (request.form.get("id"),))
                conn.commit()
            elif action == "set_push_key":
                pid = request.form.get("id", type=int)
                key = (request.form.get("push_key") or "").strip()
                if key and not valid_user_key(key):
                    pm = "badkey"
                else:
                    conn.execute("UPDATE call_volunteers SET push_user_key = ? WHERE id = ?", (key or None, pid))
                    conn.commit()
                    pm = "saved" if key else "removed"
                conn.close()
                return redirect(url_for(".call_volunteers_page", pid=pid, pm=pm) + f"#v{pid}")
            elif action == "test_push":
                pid = request.form.get("id", type=int)
                v = conn.execute("SELECT id, name, push_user_key FROM call_volunteers WHERE id = ? AND active = 1", (pid,)).fetchone()
                pm = "failed"
                if v and not pushover_ready():
                    pm = "noapp"
                elif v and not v["push_user_key"]:
                    pm = "nokey"
                elif v:
                    ok = push(v["push_user_key"], "Test alert from Discovery!",
                              f"Hi {v['name'].split()[0]}, this is a test. If you can read this, your phone alerts are working!",
                              click=_base_url() + "/cep-training#m3")
                    pm = "sent" if ok else "failed"
                conn.close()
                return redirect(url_for(".call_volunteers_page", pid=pid, pm=pm) + f"#v{pid}")
            sync_guide_lists(conn)
            conn.close()
            return redirect(url_for(".call_volunteers_page"))
        sync_guide_lists(conn)
        push_msgs = {
            "saved": ("ok", "Phone alerts saved. Now tap \u201cSend a test alert.\u201d"),
            "removed": ("ok", "Phone alerts removed."),
            "badkey": ("bad", "A Pushover User Key is 30 letters and numbers. Please copy it again from the top of the volunteer's Pushover app."),
            "noapp": ("bad", "Pushover is not connected yet: add PUSHOVER_APP_TOKEN in Render's Environment first."),
            "nokey": ("bad", "No Pushover User Key is saved yet. Paste it above and tap Save."),
            "sent": ("ok", "Test alert sent. Check the phone."),
            "consent_cleared": ("ok", "Permission cleared. They will need to give it again before they can take a request."),
            "failed": ("bad", "The test alert could not be sent. Check that the User Key is right and try again."),
        }
        push_pid = request.args.get("pid", type=int)
        push_note = push_msgs.get(request.args.get("pm", ""))
        groups = []
        for code, label in POOLS:
            vols = conn.execute("SELECT * FROM call_volunteers WHERE active = 1 AND program_code = ? ORDER BY id", (code,)).fetchall()
            for v in vols:
                if not v["consent_token"]:
                    conn.execute("UPDATE call_volunteers SET consent_token = ? WHERE id = ?", (secrets.token_urlsafe(18), v["id"]))
            conn.commit()
            vols = conn.execute("SELECT * FROM call_volunteers WHERE active = 1 AND program_code = ? ORDER BY id", (code,)).fetchall()
            groups.append(dict(code=code, label=label, max=max_for(code),
                               vols=[dict(v, phone_pretty=pretty_phone(v["cell_phone"]), consent_when=local_text(v["consent_at"]),
                                          consent_url=_base_url() + "/cep-permission/" + v["consent_token"]) for v in vols]))
        conn.close()
        from correspondence import GUIDE_EXPLAINER
        return render_template("call_volunteers.html", guide_note=GUIDE_EXPLAINER, groups=groups, max_per=MAX_PER_POOL, client_letters=CLIENT_LETTERS, welcome_video=welcome_video(), pushover_ready=pushover_ready(), push_pid=push_pid, push_note=push_note)
