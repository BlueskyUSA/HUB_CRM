"""Owner-only, read-only page: finds saved wording that still says "Guide" or "Guides".

The code that ships with the Hub already says Ambassador everywhere, but text you saved on the Hub (letters you edited on the
Correspondence page, email blast drafts, suggestions) lives in the database, and an update cannot rewrite it. This page lists
every saved item that still contains the word, with the sentence around it and a link to open and fix it. It changes nothing."""
import re
from flask import render_template, url_for

WORD = re.compile(r"\bguides?\b", re.I)
PRE = 70
POST = 70


def _hits(text):
    """[(before, word, after, capitalised)] for each match in a block of text."""
    out = []
    text = text or ""
    for m in WORD.finditer(text):
        a, b = m.start(), m.end()
        out.append((("…" if a > PRE else "") + text[max(0, a - PRE):a], m.group(0),
                    text[b:b + POST] + ("…" if b + POST < len(text) else ""), m.group(0)[0].isupper()))
    return out


def find_all(conn):
    """List of dicts: where (label), what, field, hits, endpoint, args. Each source is optional (a missing table is skipped)."""
    items = []

    def run(sql):
        try:
            return conn.execute(sql).fetchall()
        except Exception:
            try:
                conn.rollback()
            except Exception:
                pass
            return []

    def add(where, label, endpoint, args, fields):
        hs = []
        for fname, txt in fields:
            for h in _hits(txt):
                hs.append(dict(field=fname, before=h[0], word=h[1], after=h[2], cap=h[3]))
        if hs:
            items.append(dict(where=where, label=label, endpoint=endpoint, args=args, hits=hs))

    for r in run("SELECT letter_key, subject, body, signoff, signer FROM session_letter_text ORDER BY letter_key"):
        add("Letter on the Correspondence page", r["letter_key"], "correspondence_letter_edit", dict(key=r["letter_key"]),
            [("Subject", r["subject"]), ("Letter", r["body"]), ("Sign-off", r["signoff"]), ("Signer", r["signer"])])
    for r in run("SELECT id, name, subject, body FROM blast_audiences ORDER BY id"):
        add("Email blast (audience draft)", r["name"] or ("Blast #%s" % r["id"]), "email_blast_edit", dict(aid=r["id"]),
            [("Name", r["name"]), ("Subject", r["subject"]), ("Message", r["body"])])
    for r in run("SELECT id, title, subject, body, sent_at FROM blast_letters ORDER BY id"):
        add("Email blast letter" + (" (already sent)" if r["sent_at"] else " (draft)"), r["title"] or r["subject"] or ("Letter #%s" % r["id"]),
            "email_blast_letter", dict(lid=r["id"]), [("Title", r["title"]), ("Subject", r["subject"]), ("Message", r["body"])])
    for r in run("SELECT id, letter_name, message FROM letter_suggestions ORDER BY id"):
        add("Suggested change from a volunteer", r["letter_name"] or ("Suggestion #%s" % r["id"]), None, {}, [("Message", r["message"])])
    return items


def register(app, crm, true_owner_required, get_db):
    @crm.route("/owner/wording-check")
    @true_owner_required
    def wording_check():
        conn = get_db()
        try:
            items = find_all(conn)
        finally:
            conn.close()
        for it in items:
            it["url"] = url_for("crm." + it["endpoint"], **it["args"]) if it["endpoint"] else None
        total = sum(len(i["hits"]) for i in items)
        return render_template("wording_check.html", items=items, total=total)
