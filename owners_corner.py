"""Owner's Corner: things that belong to the real Owner only (not Administrators):
ownership transfer, who the Administrators are, and private notes (for example ideas for licensing the software)."""
from flask import render_template, request, redirect, url_for, session, flash


def register(app, crm, true_owner_required, get_db):
    import wording_check
    wording_check.register(app, crm, true_owner_required, get_db)

    def ensure(conn):
        conn.execute("CREATE TABLE IF NOT EXISTS owner_notes (id INTEGER PRIMARY KEY, body TEXT, updated_at TEXT)")
        conn.commit()

    @crm.route("/owners-corner")
    @true_owner_required
    def owners_corner():
        conn = get_db()
        try:
            ensure(conn)
            people = conn.execute(
                "SELECT id, name, email, is_owner, active FROM staff WHERE is_owner IN (1, 2) ORDER BY is_owner, name").fetchall()
            others = conn.execute(
                "SELECT id, name, is_owner FROM staff WHERE active = 1 AND id <> ? ORDER BY name", (session.get("staff_id"),)).fetchall()
            note = conn.execute("SELECT body, updated_at FROM owner_notes WHERE id = 1").fetchone()
        finally:
            conn.close()
        return render_template("owners_corner.html", people=people, others=others, note=note)

    @crm.route("/owners-corner/notes", methods=["POST"])
    @true_owner_required
    def owners_corner_notes():
        body = request.form.get("body") or ""
        conn = get_db()
        try:
            ensure(conn)
            if conn.execute("SELECT 1 FROM owner_notes WHERE id = 1").fetchone():
                conn.execute("UPDATE owner_notes SET body = ?, updated_at = to_char(now(), 'YYYY-MM-DD') WHERE id = 1", (body,))
            else:
                conn.execute("INSERT INTO owner_notes (id, body, updated_at) VALUES (1, ?, to_char(now(), 'YYYY-MM-DD'))", (body,))
            conn.commit()
        finally:
            conn.close()
        flash("Notes saved.")
        return redirect(url_for(".owners_corner"))
