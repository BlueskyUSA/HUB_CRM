"""Owner-only email blasts: one card per audience (a contact list, attendees, or the Guides). Each audience holds
LETTERS: you write or upload a letter, edit it while it is a draft, send yourself a test, and send it (confirmed,
paced, logged). Once a letter has been sent it is locked and shows the date it went out; start a new letter for the next one.

Safety: real sends need BLASTS_LIVE=1 in the environment, a test send of the CURRENT wording, and the
word SEND typed on the confirm box. Nobody who asked not to be emailed is sent to, nobody gets the same
message twice, and every send is logged.
"""
import hashlib
import hmac
import html as _html
import os
import re
import threading
import time

from flask import render_template, request, redirect, url_for, flash, abort, session, current_app

import call_flow as cf
from email_templates import excitement_blast_content, EXCITEMENT_BLAST_SUBJECT, preliminary_plan_content, PRELIMINARY_PLAN_SUBJECT

PAUSE = 0.25          # seconds between emails, so the email service is never flooded
_ready = False

VOLUNTEERS_BODY = """Dear {first},

When people ask about Discovery!, we want them to visit with an experienced, credible person who has been through the training. The training changed your life, and we hope you are passionate about sharing what it did for you.

Instead of relying on staff for the heavy lifting, we built an AI-assisted portal that makes it easy for every willing Discovery! volunteer to help people register for the training. Our hope is you will help us fill seats. Your personal page works on your Android or Apple phone, iPad, or computer.

If you are willing, tap the link below to get your own personal volunteer page. If you know another Discovery! volunteer who would like to help, your page has a link you can text or email to them.

{link}

Thank you for all that you do.

The Discovery! Team"""

GUIDES_BODY = ""


def ensure_tables(get_db):
    global _ready
    if _ready:
        return
    conn = get_db()
    try:
        conn.execute("""CREATE TABLE IF NOT EXISTS blast_audiences (
            id SERIAL PRIMARY KEY,
            name TEXT NOT NULL,
            kind TEXT NOT NULL DEFAULT 'text',
            list_id INTEGER,
            subject TEXT,
            body TEXT,
            link_path TEXT,
            tested_hash TEXT,
            tested_at TEXT,
            sort_order INTEGER NOT NULL DEFAULT 100,
            everyone INTEGER NOT NULL DEFAULT 0,
            scope TEXT,
            program_id INTEGER,
            cohort_id INTEGER,
            created_at TEXT NOT NULL)""")
        conn.execute("""CREATE TABLE IF NOT EXISTS blast_sends (
            id SERIAL PRIMARY KEY,
            audience_id INTEGER NOT NULL,
            subject TEXT,
            sent_by TEXT,
            status TEXT NOT NULL DEFAULT 'running',
            total INTEGER NOT NULL DEFAULT 0,
            sent_count INTEGER NOT NULL DEFAULT 0,
            failed_count INTEGER NOT NULL DEFAULT 0,
            skipped_count INTEGER NOT NULL DEFAULT 0,
            started_at TEXT NOT NULL,
            finished_at TEXT,
            snapshot_html TEXT)""")
        conn.execute("""CREATE TABLE IF NOT EXISTS blast_letters (
            id SERIAL PRIMARY KEY,
            audience_id INTEGER NOT NULL,
            title TEXT,
            kind TEXT NOT NULL DEFAULT 'text',
            subject TEXT,
            body TEXT,
            link_path TEXT,
            tested_hash TEXT,
            tested_at TEXT,
            sent_at TEXT,
            created_at TEXT NOT NULL)""")
        conn.execute("""CREATE TABLE IF NOT EXISTS blast_recipients (
            id SERIAL PRIMARY KEY,
            send_id INTEGER NOT NULL,
            contact_id INTEGER,
            first_name TEXT,
            email TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'queued',
            error TEXT,
            sent_at TEXT)""")
        conn.execute("ALTER TABLE call_volunteers ADD COLUMN IF NOT EXISTS blast_optout INTEGER NOT NULL DEFAULT 0")
        conn.execute("ALTER TABLE blast_audiences ADD COLUMN IF NOT EXISTS everyone INTEGER NOT NULL DEFAULT 0")
        conn.execute("ALTER TABLE blast_audiences ADD COLUMN IF NOT EXISTS scope TEXT")
        conn.execute("ALTER TABLE blast_audiences ADD COLUMN IF NOT EXISTS program_id INTEGER")
        conn.execute("ALTER TABLE blast_audiences ADD COLUMN IF NOT EXISTS cohort_id INTEGER")
        conn.execute("ALTER TABLE blast_sends ADD COLUMN IF NOT EXISTS snapshot_html TEXT")
        conn.execute("ALTER TABLE blast_sends ADD COLUMN IF NOT EXISTS letter_id INTEGER")
        conn.execute("ALTER TABLE contacts ADD COLUMN IF NOT EXISTS do_not_email INTEGER NOT NULL DEFAULT 0")
        conn.commit()
        n = conn.execute("SELECT COUNT(*) AS n FROM blast_audiences").fetchone()["n"]
        if not n:
            list_id = lambda name: cf.list_id_for(conn, name)
            now = cf._ts(cf._utc_now())
            seeds = [
                ("Excitement blast: Kent's contacts", "excitement", None, EXCITEMENT_BLAST_SUBJECT, None, None, 10),
                ("Excitement blast: Discovery Contact list", "excitement", list_id(cf.DISCOVERY_LIST), EXCITEMENT_BLAST_SUBJECT, None, None, 20),
                ("Excitement blast: Entire Database", "excitement", None, EXCITEMENT_BLAST_SUBJECT, None, None, 25),
                ("Discovery Guides", "guides", None, "", GUIDES_BODY, None, 30),
                ("Discovery volunteers", "text", list_id(cf.RESPONDED_LIST), "Exciting Changes to the Discovery! Program",
                 VOLUNTEERS_BODY, "/volunteer-helper/join", 40),
                ("Volunteer staff", "text", list_id("Volunteer staff"), "", "", None, 50),
            ]
            for name, kind, lid, subj, body, link, order in seeds:
                conn.execute("INSERT INTO blast_audiences (name, kind, list_id, subject, body, link_path, sort_order, everyone, created_at) "
                             "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)", (name, kind, lid, subj, body, link, order, 1 if "Entire Database" in name else 0, now))
            conn.commit()
        conn.execute("UPDATE blast_audiences SET name = ? WHERE name = ?", ("Excitement blast: Kent's contacts", "Excitement blast: my contacts"))
        conn.commit()
        # make sure the two data-set lists exist, and point the volunteer email at the people who responded
        if not conn.execute("SELECT 1 FROM blast_audiences WHERE scope = 'attendees'").fetchone():
            now2 = cf._ts(cf._utc_now())
            for name, order in (("Attendees: all programs", 60), ("Attendees: one program or session", 61)):
                conn.execute("INSERT INTO blast_audiences (name, kind, subject, body, sort_order, scope, created_at) VALUES (?, 'text', '', '', ?, 'attendees', ?)",
                             (name, order, now2))
        # The Discovery download keeps its own list, separate from all other data (earlier names are renamed).
        if not conn.execute("SELECT 1 FROM contact_lists WHERE LOWER(name) = LOWER(?)", (cf.DISCOVERY_LIST,)).fetchone():
            for old_name in cf.OLD_DISCOVERY_LISTS:
                old = conn.execute("SELECT id FROM contact_lists WHERE LOWER(name) = LOWER(?)", (old_name,)).fetchone()
                if old:
                    conn.execute("UPDATE contact_lists SET name = ? WHERE id = ?", (cf.DISCOVERY_LIST, old["id"]))
                    break
        disc_id = cf.list_id_for(conn, cf.DISCOVERY_LIST)
        conn.execute("UPDATE blast_audiences SET name = 'Excitement blast: Discovery Contact list', list_id = ?, everyone = 0 "
                     "WHERE name IN ('Excitement blast: Discovery contacts', 'Excitement blast: Discovery database') OR (name IN ('Excitement blast: entire database', 'Excitement blast: Entire Database') AND list_id = ?)",
                     (disc_id, disc_id))
        conn.execute("UPDATE blast_audiences SET name = 'Excitement blast: Entire Database' WHERE everyone = 1 AND name = 'Excitement blast: entire database'")
        if not conn.execute("SELECT 1 FROM blast_audiences WHERE everyone = 1").fetchone():
            conn.execute("INSERT INTO blast_audiences (name, kind, list_id, subject, body, sort_order, everyone, created_at) "
                         "VALUES ('Excitement blast: Entire Database', 'excitement', NULL, ?, NULL, 25, 1, ?)",
                         (EXCITEMENT_BLAST_SUBJECT, cf._ts(cf._utc_now())))
        # every audience gets at least one letter (earlier versions kept the wording on the audience itself)
        first_time = not conn.execute("SELECT 1 FROM blast_letters LIMIT 1").fetchone()
        for au in (conn.execute("SELECT * FROM blast_audiences ORDER BY id").fetchall() if first_time else []):
            if conn.execute("SELECT 1 FROM blast_letters WHERE audience_id = ?", (au["id"],)).fetchone():
                continue
            lkind = "standard" if au["kind"] == "excitement" else "text"
            if lkind == "standard":
                title = "Excitement is Growing (standard letter)"
            elif (au["body"] or "").strip():
                title = au["subject"] or "Letter"
            else:
                title = "Draft letter"
            letter = dict(kind=lkind, subject=au["subject"], body=au["body"], link_path=au["link_path"])
            old_hash = hashlib.sha1(f"{au['kind']}|{au['subject']}|{au['body']}|{au['link_path']}".encode()).hexdigest()
            th = content_hash(letter) if au["tested_hash"] and au["tested_hash"] == old_hash else None
            conn.execute("INSERT INTO blast_letters (audience_id, title, kind, subject, body, link_path, tested_hash, tested_at, created_at) "
                         "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                         (au["id"], title, lkind, au["subject"], au["body"], au["link_path"], th, au["tested_at"] if th else None, cf._ts(cf._utc_now())))
            lid = conn.execute("SELECT id FROM blast_letters ORDER BY id DESC LIMIT 1").fetchone()["id"]
            first_send = conn.execute("SELECT started_at FROM blast_sends WHERE audience_id = ? ORDER BY id LIMIT 1", (au["id"],)).fetchone()
            if first_send:
                conn.execute("UPDATE blast_letters SET sent_at = ? WHERE id = ?", (first_send["started_at"], lid))
                conn.execute("UPDATE blast_sends SET letter_id = ? WHERE audience_id = ? AND letter_id IS NULL", (lid, au["id"]))
        # The Preliminary Business Plan waits here as a draft (no recipients chosen, so nothing can go out until Kent picks an audience).
        if not conn.execute("SELECT 1 FROM blast_audiences WHERE name = 'Preliminary business plan'").fetchone():
            nowp = cf._ts(cf._utc_now())
            conn.execute("INSERT INTO blast_audiences (name, kind, subject, body, sort_order, created_at) VALUES ('Preliminary business plan', 'text', ?, '', 70, ?)",
                         (PRELIMINARY_PLAN_SUBJECT, nowp))
            pid = conn.execute("SELECT id FROM blast_audiences WHERE name = 'Preliminary business plan'").fetchone()["id"]
            conn.execute("INSERT INTO blast_letters (audience_id, title, kind, subject, body, created_at) VALUES (?, 'Preliminary business plan (waiting on the name and Keith)', 'html', ?, ?, ?)",
                         (pid, PRELIMINARY_PLAN_SUBJECT, preliminary_plan_content("[First name]")[0], nowp))
        resp_id = cf.list_id_for(conn, cf.RESPONDED_LIST)
        old = conn.execute("SELECT l.id FROM contact_lists l WHERE LOWER(l.name) = 'discovery volunteers'").fetchone()
        if old:
            conn.execute("UPDATE blast_audiences SET list_id = ? WHERE name = 'Discovery volunteers' AND list_id = ?", (resp_id, old["id"]))
        conn.commit()
        _ready = True
    except Exception as e:
        conn.rollback()
        print(f"Couldn't set up the email-blast tables: {e}", flush=True)
    finally:
        conn.close()


MAILING_ADDRESS = os.environ.get("BLAST_MAILING_ADDRESS", "Discovery!, 964 Condor Drive, Coppell, TX 75019")


def blasts_live():
    return os.environ.get("BLASTS_LIVE") == "1"


def _secret():
    return (current_app.secret_key or "dev").encode()


def unsub_token(ref):
    """ref > 0 is a contact id; ref < 0 is a Guide (call_volunteers id)."""
    if ref < 0:
        sig = hmac.new(_secret(), f"unsubg:{-ref}".encode(), hashlib.sha256).hexdigest()[:24]
        return f"g{-ref}-{sig}"
    sig = hmac.new(_secret(), f"unsub:{ref}".encode(), hashlib.sha256).hexdigest()[:24]
    return f"c{ref}-{sig}"


def unsub_target(token):
    """('contact', id) or ('guide', id) for a valid link, else None."""
    try:
        head, sig = (token or "").split("-", 1)
        if head[:1] == "g":
            n = int(head[1:])
            good = hmac.new(_secret(), f"unsubg:{n}".encode(), hashlib.sha256).hexdigest()[:24]
            return ("guide", n) if hmac.compare_digest(sig, good) else None
        n = int(head[1:] if head[:1] == "c" else head)
        good = hmac.new(_secret(), f"unsub:{n}".encode(), hashlib.sha256).hexdigest()[:24]
        return ("contact", n) if hmac.compare_digest(sig, good) else None
    except Exception:
        return None


def content_hash(letter):
    return hashlib.sha1(f"{letter['kind']}|{letter['subject']}|{letter['body']}|{letter['link_path']}".encode()).hexdigest()


def recipients(conn, aud):
    """[(contact_id or None, first_name, email)] — people who can be emailed, one per address."""
    rows = []
    if aud["kind"] == "guides":
        for r in conn.execute("SELECT id, name, email FROM call_volunteers WHERE active = 1 AND COALESCE(blast_optout, 0) = 0 ORDER BY id").fetchall():
            rows.append((-r["id"], (r["name"] or "").split()[0] if r["name"] else "", r["email"]))
    elif aud["scope"] == "attendees":
        sql = ("SELECT DISTINCT c.id, c.first_name, c.email FROM enrollments e JOIN contacts c ON c.id = e.contact_id "
               "JOIN cohorts co ON co.id = e.cohort_id WHERE COALESCE(co.status, '') <> 'Cancelled' "
               "AND c.email IS NOT NULL AND c.email <> '' AND COALESCE(c.do_not_email, 0) = 0")
        args = []
        if aud["cohort_id"]:
            sql += " AND co.id = ?"
            args.append(aud["cohort_id"])
        elif aud["program_id"]:
            sql += " AND co.program_id = ?"
            args.append(aud["program_id"])
        for r in conn.execute(sql + " ORDER BY c.id", tuple(args)).fetchall():
            rows.append((r["id"], r["first_name"] or "", r["email"]))
    elif aud["everyone"]:
        for r in conn.execute("""SELECT id, first_name, email FROM contacts WHERE email IS NOT NULL AND email <> '' AND COALESCE(do_not_email, 0) = 0 ORDER BY id""").fetchall():
            rows.append((r["id"], r["first_name"] or "", r["email"]))
    elif aud["list_id"]:
        q = conn.execute("""SELECT c.id, c.first_name, c.email FROM contact_list_members m JOIN contacts c ON c.id = m.contact_id
                            WHERE m.list_id = ? AND c.email IS NOT NULL AND c.email <> '' AND COALESCE(c.do_not_email, 0) = 0
                            ORDER BY c.id""", (aud["list_id"],)).fetchall()
        for r in q:
            rows.append((r["id"], r["first_name"] or "", r["email"]))
    # an address that has unsubscribed on ANY contact record is never emailed (people are sometimes in the database twice)
    blocked = {r["e"] for r in conn.execute("SELECT DISTINCT LOWER(email) AS e FROM contacts WHERE COALESCE(do_not_email, 0) = 1 AND email IS NOT NULL").fetchall()}
    blocked |= {r["e"] for r in conn.execute("SELECT DISTINCT LOWER(email) AS e FROM call_volunteers WHERE COALESCE(blast_optout, 0) = 1 AND email IS NOT NULL").fetchall()}
    try:
        import do_not_contact as _dnc
        blocked |= _dnc.suppressed_addresses(conn)
    except Exception:
        pass
    try:
        import bounces as _bn
        blocked |= _bn.hard_bounced_addresses(conn)
    except Exception:
        pass
    seen, out = set(blocked), []
    for cid, first, email in rows:
        e = (email or "").strip()
        k = e.lower()
        if "@" not in e or "." not in e.split("@")[-1] or k in seen:
            continue
        seen.add(k)
        out.append((cid, first, e))
    return out


def already_received(conn, letter):
    rows = conn.execute("""SELECT DISTINCT LOWER(r.email) AS e FROM blast_recipients r JOIN blast_sends s ON s.id = r.send_id
                           WHERE s.letter_id = ? AND r.status = 'sent'""", (letter["id"],)).fetchall()
    return {r["e"] for r in rows}


def standard_text():
    """The standard Excitement letter as plain text, with {first} where the name goes (a starting point to edit)."""
    return excitement_blast_content("{first}")[1].strip()


def build(letter, aud, first, contact_id, base_url):
    """(subject, html, text) for one person. contact_id: 0 = preview, None = no unsubscribe line, <0 = a Guide."""
    greet = first.strip() if first and first.strip() else "Friend"
    footer_h = footer_t = ""
    if contact_id is not None:
        u = "#" if contact_id == 0 else f"{base_url}/unsubscribe/{unsub_token(contact_id)}"
        what = ("Unsubscribe from Guide announcements (you will still get alerts about requests)" if aud["kind"] == "guides" else "Unsubscribe")
        why = ("You are receiving this because you are a Discovery! Guide." if aud["kind"] == "guides"
               else "You are receiving this because you are part of the Discovery! community.")
        footer_h = (f'<hr style="border:none;border-top:1px solid #ddd;margin:24px 0 10px">'
                    f'<p style="font-size:.8em;color:#777">{why} <a href="{u}">{what}</a><br>{_html.escape(MAILING_ADDRESS)}</p>')
        footer_t = f"\n\n--\n{why} {what}: {u}\n{MAILING_ADDRESS}"
    if letter["kind"] == "html":
        g = _html.escape(greet)
        body_h = re.sub(r"(?i)\[\s*first\s*name\s*\]|\{\s*first\s*name\s*\}", g, letter["body"] or "")
        plain = re.sub(r"(?i)</(p|h2|li)>", "\n\n", body_h.replace("<br>", "\n"))
        plain = _html.unescape(re.sub(r"<[^>]+>", "", plain)).strip()
        wrap = '<div style="font-family:Arial,Helvetica,sans-serif;font-size:15px;line-height:1.55;color:#222">' + body_h + "</div>"
        return letter["subject"] or "", wrap + footer_h, plain + footer_t
    if letter["kind"] == "standard":
        html, text = excitement_blast_content(greet)
        return letter["subject"] or EXCITEMENT_BLAST_SUBJECT, html + footer_h, text + footer_t
    link = (base_url + letter["link_path"]) if letter["link_path"] else ""
    body = re.sub(r"(?i)\[\s*first\s*name\s*\]|\{\s*first\s*name\s*\}", greet, letter["body"] or "").replace("{first}", greet)
    paras = [p for p in body.replace("\r\n", "\n").split("\n\n") if p.strip()]
    html_parts = []
    for p in paras:
        if p.strip() == "{link}":
            html_parts.append(f'<p><a href="{link}" style="display:inline-block;background:#1b2b45;color:#fff;padding:12px 22px;'
                              f'border-radius:8px;text-decoration:none;font-weight:bold">Open the page</a></p>'
                              f'<p style="font-size:.85em;color:#555">Or paste this into your browser: {link}</p>')
        else:
            esc = _html.escape(p.strip()).replace("\n", "<br>").replace("{link}", f'<a href="{link}">{link}</a>')
            esc = re.sub(r'(?<!["\'>=])(https?://[^\s<]+)', r'<a href="\1">\1</a>', esc)
            esc = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", esc)
            html_parts.append("<p>" + esc + "</p>")
    text = body.replace("{link}", link)
    return letter["subject"], "".join(html_parts) + footer_h, text + footer_t


def docx_to_html(raw):
    """(subject or None, safe html) from a Word file, keeping bold, italic, underline, color, size, links, headings, lists and alignment."""
    import zipfile, io
    import xml.etree.ElementTree as ET
    W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
    R = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}"
    z = zipfile.ZipFile(io.BytesIO(raw))
    doc = ET.fromstring(z.read("word/document.xml"))
    rels = {}
    try:
        for r in ET.fromstring(z.read("word/_rels/document.xml.rels")):
            rels[r.get("Id")] = r.get("Target")
    except KeyError:
        pass
    numfmt = {}
    try:
        num = ET.fromstring(z.read("word/numbering.xml"))
        absfmt = {}
        for a in num.iter(W + "abstractNum"):
            lvl = a.find(W + "lvl")
            f = lvl.find(W + "numFmt") if lvl is not None else None
            absfmt[a.get(W + "abstractNumId")] = f.get(W + "val") if f is not None else "bullet"
        for n in num.iter(W + "num"):
            ab = n.find(W + "abstractNumId")
            if ab is not None:
                numfmt[n.get(W + "numId")] = absfmt.get(ab.get(W + "val"), "bullet")
    except KeyError:
        pass

    def on(el):
        return el is not None and el.get(W + "val", "1").lower() not in ("0", "false", "none")

    def run_html(r):
        parts = []
        for c in r:
            if c.tag == W + "t":
                parts.append(_html.escape(c.text or ""))
            elif c.tag == W + "br":
                parts.append("<br>")
            elif c.tag == W + "tab":
                parts.append("&emsp;&emsp;")
        out = "".join(parts)
        if not out:
            return ""
        rp = r.find(W + "rPr")
        if rp is not None:
            css = []
            col = rp.find(W + "color")
            if col is not None and re.fullmatch(r"[0-9A-Fa-f]{6}", col.get(W + "val", "")) and col.get(W + "val").lower() != "000000":
                css.append("color:#" + col.get(W + "val"))
            sz = rp.find(W + "sz")
            if sz is not None and sz.get(W + "val", "").isdigit() and int(sz.get(W + "val")) not in (22, 24):
                css.append(f"font-size:{int(sz.get(W + 'val')) / 2:g}pt")
            if css:
                out = f'<span style="{";".join(css)}">{out}</span>'
            if on(rp.find(W + "u")):
                out = f"<u>{out}</u>"
            if on(rp.find(W + "i")):
                out = f"<em>{out}</em>"
            if on(rp.find(W + "b")):
                out = f"<strong>{out}</strong>"
        return out

    def walk(el):
        out = ""
        for c in el:
            if c.tag == W + "r":
                out += run_html(c)
            elif c.tag == W + "hyperlink":
                inner = walk(c)
                href = rels.get(c.get(R + "id"), "")
                if href.lower().startswith(("http://", "https://", "mailto:")):
                    out += f'<a href="{_html.escape(href, quote=True)}">{inner}</a>'
                else:
                    out += inner
            elif c.tag in (W + "ins", W + "smartTag", W + "sdt", W + "sdtContent", W + "fldSimple"):
                out += walk(c)
        return out

    blocks = []   # (list_kind or None, html, plain)
    for p in doc.iter(W + "p"):
        inner = walk(p)
        plain = re.sub(r"<[^>]+>", "", inner.replace("<br>", "\n"))
        if not plain.strip():
            continue
        pp = p.find(W + "pPr")
        style, jc, numid = "", "", None
        if pp is not None:
            ps = pp.find(W + "pStyle")
            style = ps.get(W + "val", "") if ps is not None else ""
            j = pp.find(W + "jc")
            jc = j.get(W + "val", "") if j is not None else ""
            npr = pp.find(W + "numPr")
            if npr is not None and npr.find(W + "numId") is not None:
                numid = npr.find(W + "numId").get(W + "val")
        align = f"text-align:{ {'center': 'center', 'right': 'right', 'both': 'left'}.get(jc, 'left') };" if jc in ("center", "right") else ""
        if style.lower().startswith("listbullet") or style.lower().startswith("listparagraph") and not numid:
            blocks.append(("ul", f"<li>{inner}</li>", plain))
        elif style.lower().startswith("listnumber"):
            blocks.append(("ol", f"<li>{inner}</li>", plain))
        elif numid and numid != "0":
            blocks.append(("ol" if numfmt.get(numid, "bullet") != "bullet" else "ul", f"<li>{inner}</li>", plain))
        elif style.lower().startswith("heading") or style.lower() == "title":
            blocks.append((None, f'<h2 style="margin:18px 0 8px;{align}">{inner}</h2>', plain))
        else:
            blocks.append((None, f'<p style="margin:0 0 14px;{align}">{inner}</p>', plain))
    subject = None
    if blocks and re.match(r"(?i)\s*subject\s*:", blocks[0][2]):
        subject = re.sub(r"(?i)^\s*subject\s*:\s*", "", blocks[0][2]).strip()[:200]
        blocks = blocks[1:]
    out, i = [], 0
    while i < len(blocks):
        k = blocks[i][0]
        if k:
            j = i
            items = []
            while j < len(blocks) and blocks[j][0] == k:
                items.append(blocks[j][1]); j += 1
            out.append(f'<{k} style="margin:0 0 14px 22px;padding:0">' + "".join(items) + f"</{k}>")
            i = j
        else:
            out.append(blocks[i][1]); i += 1
    return subject, "".join(out)


def parse_upload(f):
    """(subject or None, body text) from an uploaded .docx, .txt or .html letter."""
    name = (f.filename or "").lower()
    raw = f.read(3_000_000)
    if name.endswith(".docx"):
        import zipfile, io
        import xml.etree.ElementTree as ET
        W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
        with zipfile.ZipFile(io.BytesIO(raw)) as z:
            root = ET.fromstring(z.read("word/document.xml"))
        paras = []
        for para in root.iter(W + "p"):
            buf = []
            for t in para.iter():
                if t.tag == W + "t":
                    buf.append(t.text or "")
                elif t.tag == W + "br":
                    buf.append("\n")
                elif t.tag == W + "tab":
                    buf.append("    ")
            line = "".join(buf).strip()
            if line:
                paras.append(line)
        text = "\n\n".join(paras)
    else:
        text = raw.decode("utf-8", errors="replace")
        if name.endswith((".html", ".htm")):
            text = re.sub(r"(?is)<(script|style).*?</\1>", "", text)
            text = re.sub(r"(?i)</(p|div|h[1-6]|li|tr)>", "\n\n", text)
            text = re.sub(r"(?i)<br\s*/?>", "\n", text)
            text = re.sub(r"<[^>]+>", "", text)
            text = _html.unescape(text)
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = re.sub(r"[ \t]+\n", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text).strip()
    # Word puts each paragraph on one line; make single line breaks into paragraph breaks unless blank lines already exist
    if "\n\n" not in text:
        text = text.replace("\n", "\n\n")
    subject = None
    m = re.match(r"(?i)\s*subject\s*:\s*(.+)\n+", text)
    if m:
        subject = m.group(1).strip()[:200]
        text = text[m.end():].lstrip()
    return subject, text


def run_send(get_db, send_id, base_url):
    """Sends every queued recipient of one send, a few per second. Safe to run again after a restart."""
    conn = get_db()
    try:
        s = conn.execute("SELECT * FROM blast_sends WHERE id = ?", (send_id,)).fetchone()
        aud = conn.execute("SELECT * FROM blast_audiences WHERE id = ?", (s["audience_id"],)).fetchone()
        letter = conn.execute("SELECT * FROM blast_letters WHERE id = ?", (s["letter_id"],)).fetchone()
        queue = conn.execute("SELECT * FROM blast_recipients WHERE send_id = ? AND status = 'queued' ORDER BY id", (send_id,)).fetchall()
        for r in queue:
            cur = conn.execute("SELECT status FROM blast_sends WHERE id = ?", (send_id,)).fetchone()
            if cur["status"] != "running":
                break
            subject, html, text = build(letter, aud, r["first_name"], r["contact_id"], base_url)
            subject = s["subject"] or subject
            try:
                _u = f"{base_url}/unsubscribe/{unsub_token(r['contact_id'])}" if r["contact_id"] else None
                cf._send(r["email"], subject, html, text, to_name=r["first_name"] or None,
                         headers=({"List-Unsubscribe": f"<{_u}>", "List-Unsubscribe-Post": "List-Unsubscribe=One-Click"} if _u else None))
                conn.execute("UPDATE blast_recipients SET status = 'sent', sent_at = ? WHERE id = ?", (cf._ts(cf._utc_now()), r["id"]))
                conn.execute("UPDATE blast_sends SET sent_count = sent_count + 1 WHERE id = ?", (send_id,))
            except Exception as e:
                conn.execute("UPDATE blast_recipients SET status = 'failed', error = ? WHERE id = ?", (str(e)[:300], r["id"]))
                conn.execute("UPDATE blast_sends SET failed_count = failed_count + 1 WHERE id = ?", (send_id,))
            conn.commit()
            time.sleep(PAUSE)
        cur = conn.execute("SELECT status FROM blast_sends WHERE id = ?", (send_id,)).fetchone()
        if cur["status"] == "running":
            conn.execute("UPDATE blast_sends SET status = 'done', finished_at = ? WHERE id = ?", (cf._ts(cf._utc_now()), send_id))
            conn.commit()
    except Exception as e:
        print(f"Email blast {send_id} stopped: {e}", flush=True)
    finally:
        conn.close()


def attendee_label(conn, aud):
    """Plain-English description of who an 'attendees' audience goes to."""
    if aud["cohort_id"]:
        r = conn.execute("SELECT p.name AS pn, p.code AS pc, co.session_number AS n, co.session_date AS d FROM cohorts co JOIN programs p ON p.id = co.program_id WHERE co.id = ?", (aud["cohort_id"],)).fetchone()
        if r:
            return f"Enrolled in {r['pc']} session #{r['n']} ({r['d']})"
    if aud["program_id"]:
        r = conn.execute("SELECT code, name FROM programs WHERE id = ?", (aud["program_id"],)).fetchone()
        if r:
            return f"Everyone enrolled in {r['code']}" + (f" ({r['name']})" if r['name'] != r['code'] else "")
    return "Everyone enrolled in any program"


def programs_and_sessions(conn):
    progs = conn.execute("SELECT id, code, name FROM programs ORDER BY code").fetchall()
    sess = conn.execute("SELECT co.id, co.program_id, co.session_number, co.session_date, p.name AS pn, p.code AS pc FROM cohorts co JOIN programs p ON p.id = co.program_id "
                        "ORDER BY co.session_date DESC").fetchall()
    return progs, sess


def register(app, crm, owner_required, get_db):
    base = lambda: cf._base_url()

    def _aud(conn, aid):
        a = conn.execute("SELECT * FROM blast_audiences WHERE id = ?", (aid,)).fetchone()
        if not a:
            abort(404)
        return a

    def _letter(conn, lid):
        l = conn.execute("SELECT * FROM blast_letters WHERE id = ?", (lid,)).fetchone()
        if not l:
            abort(404)
        return l

    def _lists(conn):
        return conn.execute("SELECT id, name FROM contact_lists ORDER BY name").fetchall()

    def _new_letter(conn, aid, title, kind="text", subject="", body="", link_path=None):
        conn.execute("INSERT INTO blast_letters (audience_id, title, kind, subject, body, link_path, created_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
                     (aid, title[:160], kind, subject, body, link_path, cf._ts(cf._utc_now())))
        return conn.execute("SELECT id FROM blast_letters ORDER BY id DESC LIMIT 1").fetchone()["id"]

    def _first_name():
        n = session.get("staff_name") or ""
        return n.split()[0] if n else "Friend"

    def _letter_row(conn, l):
        n_sent = conn.execute("SELECT COALESCE(SUM(sent_count), 0) AS n FROM blast_sends WHERE letter_id = ?", (l["id"],)).fetchone()["n"]
        return dict(l, sent_when=(cf.local_text(l["sent_at"]) if l["sent_at"] else ""), sent_date=(cf.local_text(l["sent_at"]).split(",")[0] if l["sent_at"] else ""),
                    sent_count=n_sent, empty=(l["kind"] != "standard" and not (l["body"] or "").strip()),
                    shown_name=(l["title"] or l["subject"] or "Letter"))

    @crm.route("/email-blasts/from-list/<int:list_id>", methods=["GET", "POST"])
    @owner_required
    def email_blast_from_list(list_id):
        """From the Contacts page: start (or reopen) an email to everyone on one contact list."""
        ensure_tables(get_db)
        conn = get_db()
        try:
            lst = conn.execute("SELECT id, name FROM contact_lists WHERE id = ?", (list_id,)).fetchone()
            if not lst:
                flash("Couldn't find that list.")
                return redirect(url_for(".email_blasts"))
            a = conn.execute("SELECT id FROM blast_audiences WHERE list_id = ? AND kind = 'text' AND scope IS NULL ORDER BY id LIMIT 1", (list_id,)).fetchone()
            if not a:
                conn.execute("INSERT INTO blast_audiences (name, kind, list_id, subject, body, sort_order, scope, created_at) VALUES (?, 'text', ?, '', '', 90, NULL, ?)",
                             (lst["name"][:120], list_id, cf._ts(cf._utc_now())))
                a = conn.execute("SELECT id FROM blast_audiences ORDER BY id DESC LIMIT 1").fetchone()
                _new_letter(conn, a["id"], "Draft letter")
                conn.commit()
            return redirect(url_for(".email_blast_edit", aid=a["id"]))
        finally:
            conn.close()

    @crm.route("/email-blasts", methods=["GET", "POST"])
    @owner_required
    def email_blasts():
        ensure_tables(get_db)
        conn = get_db()
        try:
            if request.method == "POST":
                name = (request.form.get("name") or "").strip()[:120]
                lid = request.form.get("list_id") or None
                if name:
                    conn.execute("INSERT INTO blast_audiences (name, kind, list_id, subject, body, sort_order, scope, created_at) VALUES (?, 'text', ?, '', '', 90, ?, ?)",
                                 (name, int(lid) if (lid and request.form.get("type") != "attendees") else None,
                                  "attendees" if request.form.get("type") == "attendees" else None, cf._ts(cf._utc_now())))
                    new = conn.execute("SELECT id FROM blast_audiences ORDER BY id DESC LIMIT 1").fetchone()
                    _new_letter(conn, new["id"], "Draft letter")
                    conn.commit()
                    return redirect(url_for(".email_blast_edit", aid=new["id"]))
            cards = []
            for a in conn.execute("SELECT * FROM blast_audiences ORDER BY sort_order, id").fetchall():
                recips = recipients(conn, a)
                lst = conn.execute("SELECT name FROM contact_lists WHERE id = ?", (a["list_id"],)).fetchone() if a["list_id"] else None
                letters = [_letter_row(conn, l) for l in conn.execute("SELECT * FROM blast_letters WHERE audience_id = ? ORDER BY id DESC", (a["id"],)).fetchall()]
                drafts = [l for l in letters if not l["sent_at"]]
                sent = [l for l in letters if l["sent_at"]]
                cards.append(dict(a=a, count=len(recips), list_name=lst["name"] if lst else None,
                                  who=(attendee_label(conn, a) if a["scope"] == "attendees" else None),
                                  n_drafts=len(drafts), n_sent=len(sent), last_sent=(sent[0] if sent else None),
                                  latest=(letters[0] if letters else None)))
            history, drafts = [], []
            for c in cards:
                for l in conn.execute("SELECT * FROM blast_letters WHERE audience_id = ? ORDER BY id DESC", (c["a"]["id"],)).fetchall():
                    row = _letter_row(conn, l)
                    item = dict(lid=l["id"], aid=c["a"]["id"], group=c["a"]["name"], title=row["shown_name"], subject=l["subject"] or "",
                                sent_at=l["sent_at"] or "", sent_date=row["sent_date"], year=(l["sent_at"] or "")[:4], sent_count=row["sent_count"], empty=row["empty"])
                    if l["sent_at"]:
                        history.append(item)
                    elif not row["empty"]:
                        drafts.append(item)
            history.sort(key=lambda x: x["sent_at"], reverse=True)
            return render_template("email_blasts.html", cards=cards, lists=_lists(conn), live=blasts_live(),
                                   history=history, drafts=drafts, years=sorted({h["year"] for h in history}, reverse=True))
        finally:
            conn.close()

    @crm.route("/email-blasts/<int:aid>", methods=["GET", "POST"])
    @owner_required
    def email_blast_edit(aid):
        """One audience: who it goes to, and its letters (drafts you can edit, and letters already sent)."""
        ensure_tables(get_db)
        conn = get_db()
        try:
            a = _aud(conn, aid)
            act = request.form.get("action") if request.method == "POST" else None
            if act == "save_audience":
                lid = request.form.get("list_id") or None
                if a["scope"] == "attendees":
                    pid = request.form.get("program_id") or None
                    cid = request.form.get("cohort_id") or None
                    if cid:
                        row = conn.execute("SELECT program_id FROM cohorts WHERE id = ?", (int(cid),)).fetchone()
                        pid = row["program_id"] if row else pid
                    conn.execute("UPDATE blast_audiences SET program_id = ?, cohort_id = ? WHERE id = ?",
                                 (int(pid) if pid else None, int(cid) if cid else None, aid))
                conn.execute("UPDATE blast_audiences SET name = ?, list_id = ? WHERE id = ?",
                             ((request.form.get("name") or a["name"]).strip()[:120],
                              int(lid) if (lid and a["kind"] != "guides" and not a["everyone"] and a["scope"] != "attendees") else a["list_id"], aid))
                conn.commit()
                flash("Saved who this goes to.")
                return redirect(url_for(".email_blast_edit", aid=aid))
            if act == "add_standard":
                lid = _new_letter(conn, aid, "Excitement is Growing (standard letter)", "standard", EXCITEMENT_BLAST_SUBJECT, "", None)
                conn.commit()
                flash("The standard Excitement letter was added with its original look. Send yourself a test, then send.")
                return redirect(url_for(".email_blast_letter", lid=lid))
            if act == "new_letter":
                title = (request.form.get("title") or "").strip() or "New letter"
                subject, body, lkind = "", "", "text"
                f = request.files.get("file")
                if f and f.filename:
                    ext = (f.filename or "").lower().rsplit(".", 1)[-1]
                    if ext not in ("docx", "txt", "html", "htm"):
                        flash(f"I could not use \u201c{f.filename}\u201d. Only Word (.docx), text (.txt) or web page (.html) files work. "
                              "In Word, use Save As > Word Document (.docx); older .doc, .pdf and .pages files are not supported. "
                              "You can also leave the file empty and paste the wording in on the next page.")
                        return redirect(url_for(".email_blast_edit", aid=aid))
                    try:
                        if ext == "docx":
                            subject, body = docx_to_html(f.read(3_000_000))
                            lkind = "html"
                        else:
                            subject, body = parse_upload(f)
                        subject = subject or ""
                    except Exception as e:
                        flash(f"That file could not be read ({e}). Please save it as a Word (.docx) file and try again.")
                        return redirect(url_for(".email_blast_edit", aid=aid))
                    if not re.sub(r"<[^>]+>", "", body).strip():
                        flash("That file had no text in it. Nothing was added.")
                        return redirect(url_for(".email_blast_edit", aid=aid))
                lid = _new_letter(conn, aid, title, lkind, subject, body, None)
                conn.commit()
                flash("Letter uploaded with its formatting. Check it below, then send yourself a test." if body else "New letter started. Write the wording below.")
                return redirect(url_for(".email_blast_letter", lid=lid))
            recips = recipients(conn, a)
            letters = [_letter_row(conn, l) for l in conn.execute("SELECT * FROM blast_letters WHERE audience_id = ? ORDER BY id DESC", (aid,)).fetchall()]
            progs, sess = programs_and_sessions(conn)
            sends = [dict(s, when=cf.local_text(s["started_at"])) for s in
                     conn.execute("SELECT * FROM blast_sends WHERE audience_id = ? ORDER BY id DESC LIMIT 10", (aid,)).fetchall()]
            return render_template("email_blast_edit.html", a=a, lists=_lists(conn), progs=progs, sess=sess,
                                   who=(attendee_label(conn, a) if a["scope"] == "attendees" else None), count=len(recips),
                                   letters=letters, sends=sends, live=blasts_live())
        finally:
            conn.close()

    @crm.route("/email-blasts/letter/<int:lid>", methods=["GET", "POST"])
    @owner_required
    def email_blast_letter(lid):
        ensure_tables(get_db)
        conn = get_db()
        try:
            l = _letter(conn, lid)
            a = _aud(conn, l["audience_id"])
            locked = bool(l["sent_at"])
            act = request.form.get("action") if request.method == "POST" else None
            back = redirect(url_for(".email_blast_letter", lid=lid))
            if act == "duplicate":
                if l["kind"] == "standard":
                    nid = _new_letter(conn, a["id"], (l["title"] or "Letter") + " (copy)", "standard", l["subject"] or EXCITEMENT_BLAST_SUBJECT, "", None)
                else:
                    nid = _new_letter(conn, a["id"], (l["title"] or "Letter") + " (copy)", l["kind"],
                                      l["subject"] or "", l["body"], l["link_path"])
                conn.commit()
                flash("A new draft was made from this letter. You can edit this one.")
                return redirect(url_for(".email_blast_letter", lid=nid))
            if act == "delete":
                used = conn.execute("SELECT 1 FROM blast_sends WHERE letter_id = ?", (lid,)).fetchone()
                if locked or used:
                    flash("A letter that has been sent cannot be deleted.")
                    return back
                conn.execute("DELETE FROM blast_letters WHERE id = ?", (lid,))
                conn.commit()
                flash("Draft deleted.")
                return redirect(url_for(".email_blast_edit", aid=a["id"]))
            if act in ("save", "customize", "test", "replace_file", "to_text") and locked:
                flash("This letter has already been sent, so it can no longer be changed. Use \u201cCopy to a new draft\u201d to write another.")
                return back
            if act == "replace_file":
                f = request.files.get("file")
                if not f or not (f.filename or "").lower().endswith(".docx"):
                    flash("Choose a Word (.docx) file to replace this letter.")
                    return back
                try:
                    subj, body = docx_to_html(f.read(3_000_000))
                except Exception as e:
                    flash(f"That file could not be read ({e}). Please save it as a Word (.docx) file and try again.")
                    return back
                if not re.sub(r"<[^>]+>", "", body).strip():
                    flash("That file had no text in it. Nothing was changed.")
                    return back
                conn.execute("UPDATE blast_letters SET kind = 'html', body = ?, subject = ? WHERE id = ?", (body, subj or l["subject"], lid))
                conn.commit()
                flash("Letter replaced with the new Word file. Send yourself a test.")
                return back
            if act == "to_text" and l["kind"] == "html":
                plain = re.sub(r"(?i)</(p|h2|li)>", "\n\n", l["body"].replace("<br>", "\n"))
                plain = _html.unescape(re.sub(r"<[^>]+>", "", plain)).strip()
                conn.execute("UPDATE blast_letters SET kind = 'text', body = ? WHERE id = ?", (plain, lid))
                conn.commit()
                flash("Now plain text. You can type changes here, but the colors, bold and links are gone.")
                return back
            if act == "customize" and l["kind"] == "standard":
                conn.execute("UPDATE blast_letters SET kind = 'text', body = ?, title = ? WHERE id = ?",
                             (standard_text(), "Excitement is Growing (edited)", lid))
                conn.commit()
                flash("You can now edit the wording. Don't forget to send yourself a test.")
                return back
            if act == "save":
                conn.execute("UPDATE blast_letters SET title = ?, subject = ?, body = ?, link_path = ? WHERE id = ?",
                             ((request.form.get("title") or l["title"] or "Letter").strip()[:160], (request.form.get("subject") or "").strip()[:200],
                              request.form.get("body") if l["kind"] == "text" else l["body"],
                              ((request.form.get("link_path") or "").strip() or None) if l["kind"] == "text" else l["link_path"], lid))
                conn.commit()
                flash("Saved. Send yourself a test before the real send.")
                return back
            if act == "test":
                to = (request.form.get("to") or "").strip()
                if "@" not in to:
                    flash("Please enter an email address for the test.")
                else:
                    subject, html, text = build(l, a, _first_name(), 0, base())
                    try:
                        cf._send(to, "[TEST] " + (subject or "(no subject)"), html, text, to_name=_first_name())
                        conn.execute("UPDATE blast_letters SET tested_hash = ?, tested_at = ? WHERE id = ?", (content_hash(l), cf._ts(cf._utc_now()), lid))
                        conn.commit()
                        flash(f"Test sent to {to}. Check how it looks, then you can send for real.")
                    except Exception as e:
                        flash(f"The test could not be sent: {e}")
                return back
            recips = recipients(conn, a)
            skip = already_received(conn, l)
            todo = [r for r in recips if r[2].lower() not in skip]
            if act == "send":
                if not blasts_live():
                    flash("Real sending is switched off (BLASTS_LIVE is not set to 1 in Render).")
                elif (request.form.get("confirm") or "").strip() != "SEND":
                    flash("Type SEND in the box to confirm.")
                elif l["tested_hash"] != content_hash(l):
                    flash("Please send yourself a test of the current wording first.")
                elif not (l["subject"] or "").strip() and l["kind"] != "standard":
                    flash("Please add a subject line.")
                elif l["kind"] != "standard" and not (l["body"] or "").strip():
                    flash("Please write the message first.")
                elif not todo:
                    flash("There is nobody left to send this to.")
                else:
                    snap_subject, snap_html, _t = build(l, a, "Friend", 0, base())
                    now = cf._ts(cf._utc_now())
                    conn.execute("INSERT INTO blast_sends (audience_id, letter_id, subject, sent_by, status, total, skipped_count, started_at, snapshot_html) "
                                 "VALUES (?, ?, ?, ?, 'running', ?, ?, ?, ?)",
                                 (a["id"], lid, l["subject"] or snap_subject, session.get("staff_name"), len(todo), len(recips) - len(todo), now, snap_html))
                    sid = conn.execute("SELECT id FROM blast_sends ORDER BY id DESC LIMIT 1").fetchone()["id"]
                    if not l["sent_at"]:
                        conn.execute("UPDATE blast_letters SET sent_at = ? WHERE id = ?", (now, lid))
                    for cid, first, email in todo:
                        conn.execute("INSERT INTO blast_recipients (send_id, contact_id, first_name, email) VALUES (?, ?, ?, ?)", (sid, cid, first, email))
                    conn.commit()
                    if os.environ.get("DISABLE_BACKGROUND_THREADS"):
                        run_send(get_db, sid, base())
                    else:
                        threading.Thread(target=run_send, args=(get_db, sid, base()), daemon=True).start()
                    return redirect(url_for(".email_blast_send", sid=sid))
                return back
            subject, html, _t = build(l, a, _first_name(), 0, base())
            sends = [dict(s, when=cf.local_text(s["started_at"])) for s in
                     conn.execute("SELECT * FROM blast_sends WHERE letter_id = ? ORDER BY id DESC LIMIT 10", (lid,)).fetchall()]
            owner = conn.execute("SELECT email FROM staff WHERE id = ?", (session.get("staff_id"),)).fetchone()
            lr = _letter_row(conn, conn.execute("SELECT * FROM blast_letters WHERE id = ?", (lid,)).fetchone())
            return render_template("email_blast_letter.html", a=a, l=lr, locked=locked, count=len(recips), remaining=len(todo),
                                   already=len(recips) - len(todo), preview_subject=subject, preview_html=html,
                                   tested=(l["tested_hash"] == content_hash(l)), tested_when=cf.local_text(l["tested_at"]) if l["tested_at"] else "",
                                   live=blasts_live(), sends=sends, owner_email=(owner["email"] if owner else ""))
        finally:
            conn.close()

    @crm.route("/email-blasts/letters")
    @owner_required
    def email_blast_letters():
        """Every letter on one page: drafts and the ones already sent, with the dates."""
        ensure_tables(get_db)
        conn = get_db()
        try:
            items = []
            for a in conn.execute("SELECT * FROM blast_audiences ORDER BY sort_order, id").fetchall():
                count = len(recipients(conn, a))
                ls = []
                for l in conn.execute("SELECT * FROM blast_letters WHERE audience_id = ? ORDER BY id DESC", (a["id"],)).fetchall():
                    row = _letter_row(conn, l)
                    subject, html, _t = build(l, a, _first_name(), 0, base())
                    ls.append(dict(row, subject_shown=subject, html=html))
                items.append(dict(a=a, count=count, letters=ls))
            return render_template("email_blast_letters.html", items=items)
        finally:
            conn.close()

    @crm.route("/email-blasts/send/<int:sid>", methods=["GET", "POST"])
    @owner_required
    def email_blast_send(sid):
        ensure_tables(get_db)
        conn = get_db()
        try:
            s = conn.execute("SELECT * FROM blast_sends WHERE id = ?", (sid,)).fetchone()
            if not s:
                abort(404)
            if request.method == "POST" and request.form.get("action") == "stop" and s["status"] == "running":
                conn.execute("UPDATE blast_sends SET status = 'stopped', finished_at = ? WHERE id = ?", (cf._ts(cf._utc_now()), sid))
                conn.commit()
                return redirect(url_for(".email_blast_send", sid=sid))
            a = _aud(conn, s["audience_id"])
            failed = conn.execute("SELECT first_name, email, error FROM blast_recipients WHERE send_id = ? AND status = 'failed' LIMIT 50", (sid,)).fetchall()
            s = conn.execute("SELECT * FROM blast_sends WHERE id = ?", (sid,)).fetchone()
            return render_template("email_blast_send.html", s=s, a=a, failed=failed, started=cf.local_text(s["started_at"]))
        finally:
            conn.close()

    def _record_unsub(conn, where_sql, args):
        try:
            import do_not_contact as _dnc
            _dnc.ensure(conn)
            _dnc.note_unsubscribed(conn, where_sql, args)
        except Exception:
            try: conn.rollback()
            except Exception: pass

    @app.route("/unsubscribe/<token>", methods=["GET", "POST"])
    def public_unsubscribe(token):
        ensure_tables(get_db)
        t = unsub_target(token)
        if not t:
            abort(404)
        kind, n = t
        done = False
        if request.method == "POST":
            conn = get_db()
            try:
                if kind == "guide":
                    conn.execute("UPDATE call_volunteers SET blast_optout = 1 WHERE LOWER(email) = (SELECT LOWER(email) FROM call_volunteers WHERE id = ?)", (n,))
                    conn.execute("UPDATE contacts SET do_not_email = 1 WHERE email IS NOT NULL AND LOWER(email) = "
                                 "(SELECT LOWER(email) FROM call_volunteers WHERE id = ?)", (n,))
                    _record_unsub(conn, "email IS NOT NULL AND LOWER(email) = (SELECT LOWER(email) FROM call_volunteers WHERE id = ?)", (n,))
                else:
                    conn.execute("UPDATE contacts SET do_not_email = 1 WHERE id = ?", (n,))
                    conn.execute("UPDATE contacts SET do_not_email = 1 WHERE email IS NOT NULL AND LOWER(email) = "
                                 "(SELECT LOWER(email) FROM contacts WHERE id = ?)", (n,))
                    _record_unsub(conn, "id = ? OR (email IS NOT NULL AND LOWER(email) = (SELECT LOWER(email) FROM contacts WHERE id = ?))", (n, n))
                    conn.execute("UPDATE call_volunteers SET blast_optout = 1 WHERE LOWER(email) = "
                                 "(SELECT LOWER(email) FROM contacts WHERE id = ?)", (n,))
                conn.commit()
                done = True
            finally:
                conn.close()
        return render_template("public_unsubscribe.html", done=done, guide=(kind == "guide"))

    # a restart in the middle of a send picks up where it left off
    def _resume():
        time.sleep(30)
        try:
            ensure_tables(get_db)
            conn = get_db()
            try:
                ids = [r["id"] for r in conn.execute("SELECT id FROM blast_sends WHERE status = 'running'").fetchall()]
            finally:
                conn.close()
            for sid in ids:
                run_send(get_db, sid, (os.environ.get("PUBLIC_BASE_URL") or "https://dallas-discovery-crm.onrender.com").rstrip("/"))
        except Exception as e:
            print(f"Couldn't resume email blasts: {e}", flush=True)

    if not os.environ.get("DISABLE_BACKGROUND_THREADS"):
        threading.Thread(target=_resume, daemon=True).start()
