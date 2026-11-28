"""Owner Instructions page: the Render and go-live steps in one place, with the current state of each safety switch
and a checklist that saves. Owner only."""
from flask import render_template, request, redirect, url_for, session, flash

CHECKLIST = [
    ("health_check", "Contact health check passed (Contacts → Health check)"),
    ("keith", "Discussions with Keith finished (Nov 20 go / no-go)"),
    ("brevo_webhook", "Brevo bounce connection set up (see below)"),
    ("test_letters", "Test copies of the main letters sent to myself and read"),
    ("switch_letters", "Turned on SESSION_LETTERS_LIVE in Render"),
    ("switch_auto", "Turned on AUTO_LETTERS_LIVE in Render (automatic letters)"),
    ("switch_blasts", "Turned on BLASTS_LIVE in Render (email blasts)"),
    ("public_site", "Public-site files uploaded to GitHub (held until ready to go live)"),
    ("first_blast", "First email blast sent"),
]


SOFTWARE_SEED = [  # (name, what it is for, login address)
    ("Render", "Runs the Hub and the public site; go-live switches", "https://dashboard.render.com"),
    ("GitHub", "Holds the Hub's code (HUB_CRM)", "https://github.com/login"),
    ("Brevo", "Sends email and reports bounces", "https://app.brevo.com"),
    ("Pushover", "Phone alerts for Ambassadors", "https://pushover.net/login"),
    ("QuickBooks Online", "Accounting", "https://qbo.intuit.com"),
    ("Claude", "Builds and updates the Hub", "https://claude.ai"),
    ("ChatGPT", "", "https://chatgpt.com"),
    ("GoDaddy", "Web addresses (domains)", "https://sso.godaddy.com"),
]


SOFTWARE_ADDED = [
    ("seed_google", [
        ("Google Meet", "Video call link saved on contact pages. The link is only pasted in; the Hub is not connected to Google", "https://meet.google.com", "Free"),
        ("Google Fonts", "Lettering on the website pages. No account needed; the site still works without it", "https://fonts.google.com", "Free"),
    ]),
]


def ensure(conn):
    conn.execute("CREATE TABLE IF NOT EXISTS owner_checklist (key TEXT PRIMARY KEY, done_by TEXT, done_at TEXT)")
    conn.execute("""CREATE TABLE IF NOT EXISTS software_accounts (
        id SERIAL PRIMARY KEY, name TEXT NOT NULL, purpose TEXT, login_url TEXT, login_name TEXT,
        password_where TEXT, monthly_cost TEXT, notes TEXT, updated_by TEXT, updated_at TEXT)""")
    if not conn.execute("SELECT 1 FROM software_accounts LIMIT 1").fetchone():
        for n, w, u in SOFTWARE_SEED:
            conn.execute("INSERT INTO software_accounts (name, purpose, login_url) VALUES (?, ?, ?)", (n, w, u))
    # One-time additions to an already-filled list (a marker keeps a removed row from coming back).
    for marker, rows in SOFTWARE_ADDED:
        if not conn.execute("SELECT 1 FROM owner_checklist WHERE key = ?", (marker,)).fetchone():
            for n, w, u, c in rows:
                if not conn.execute("SELECT 1 FROM software_accounts WHERE name = ?", (n,)).fetchone():
                    conn.execute("INSERT INTO software_accounts (name, purpose, login_url, monthly_cost) VALUES (?, ?, ?, ?)", (n, w, u, c))
            conn.execute("INSERT INTO owner_checklist (key, done_by, done_at) VALUES (?, 'system', to_char(now(), 'YYYY-MM-DD'))", (marker,))
    conn.commit()


def register(app, crm, owner_required, get_db, switches_fn):
    @crm.route("/owner-instructions")
    @owner_required
    def owner_instructions():
        import bounces
        conn = get_db()
        try:
            ensure(conn)
            done = {r["key"]: r for r in conn.execute("SELECT key, done_by, done_at FROM owner_checklist").fetchall()}
            software = conn.execute("SELECT * FROM software_accounts ORDER BY id").fetchall()
        finally:
            conn.close()
        try:
            hook = url_for("brevo_webhook", key=bounces.secret(app), _external=True)
        except Exception:
            hook = None
        return render_template("owner_instructions.html", checklist=CHECKLIST, done=done,
                               switches=switches_fn(), hook=hook, software=software)

    @crm.route("/owner-instructions/software", methods=["POST"])
    @owner_required
    def owner_software_save():
        """Add or update one row of the software list. Passwords are never stored here."""
        f = request.form
        name = (f.get("name") or "").strip()
        if not name:
            flash("Enter the software's name. Nothing was saved.")
            return redirect(url_for(".owner_instructions") + "#software")
        vals = [(f.get(k) or "").strip() for k in ("purpose", "login_url", "login_name", "password_where", "monthly_cost", "notes")]
        conn = get_db()
        try:
            ensure(conn)
            sid = f.get("id")
            if sid:
                conn.execute("""UPDATE software_accounts SET name=?, purpose=?, login_url=?, login_name=?, password_where=?,
                                monthly_cost=?, notes=?, updated_by=?, updated_at=to_char(now(), 'YYYY-MM-DD') WHERE id=?""",
                             [name] + vals + [session.get("staff_name"), sid])
            else:
                conn.execute("""INSERT INTO software_accounts (name, purpose, login_url, login_name, password_where,
                                monthly_cost, notes, updated_by, updated_at) VALUES (?,?,?,?,?,?,?,?,to_char(now(), 'YYYY-MM-DD'))""",
                             [name] + vals + [session.get("staff_name")])
            conn.commit()
        finally:
            conn.close()
        flash("Saved.")
        return redirect(url_for(".owner_instructions") + "#software")

    @crm.route("/owner-instructions/software/<int:sid>/delete", methods=["POST"])
    @owner_required
    def owner_software_delete(sid):
        conn = get_db()
        try:
            ensure(conn)
            conn.execute("DELETE FROM software_accounts WHERE id = ?", (sid,))
            conn.commit()
        finally:
            conn.close()
        flash("Removed.")
        return redirect(url_for(".owner_instructions") + "#software")

    @crm.route("/owner-instructions/check", methods=["POST"])
    @owner_required
    def owner_instructions_check():
        key = request.form.get("key")
        if key in dict(CHECKLIST):
            conn = get_db()
            try:
                ensure(conn)
                if conn.execute("SELECT 1 FROM owner_checklist WHERE key = ?", (key,)).fetchone():
                    conn.execute("DELETE FROM owner_checklist WHERE key = ?", (key,))
                else:
                    conn.execute("INSERT INTO owner_checklist (key, done_by, done_at) VALUES (?, ?, to_char(now(), 'YYYY-MM-DD'))",
                                 (key, session.get("staff_name")))
                conn.commit()
            finally:
                conn.close()
        return redirect(url_for(".owner_instructions") + "#checklist")
