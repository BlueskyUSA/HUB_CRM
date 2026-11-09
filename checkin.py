"""Greeter check-in table: the greeter logs in, opens the session, taps a couple, takes the couple photo with the computer's or
iPad's camera, and it is saved on both partners' pages. Also shows what is still missing (payment, questionnaire, profile).
A 'Photo board' page shows every couple's photo for the session so TAs can remember who they are visiting with."""
import re
from datetime import datetime, timedelta
from flask import render_template, request, session, redirect, url_for, flash, jsonify, abort, make_response

FULL_AREAS = ("checkin", "contacts")                      # may take photos
VIEW_AREAS = ("checkin", "contacts", "trainee_roster", "session_team")   # may see the photo board


def register(app, crm, get_db, has_area_access, auto_link, full_name_sql, process_photo, cp, upsert_photo=None, hooks=None):
    hooks = hooks or {}
    money_required = hooks.get("money_required") or (lambda f: f)
    def _allowed(areas):
        return bool(session.get("is_owner")) or any(has_area_access(a) for a in areas)


    _ready = {"v": False}

    def _ensure_tables(conn):
        if _ready["v"]:
            return
        conn.execute("""CREATE TABLE IF NOT EXISTS checkin_payments (
            id SERIAL PRIMARY KEY, cohort_id INTEGER NOT NULL, enrollment_id INTEGER NOT NULL, contact_id INTEGER,
            amount REAL, method TEXT, reference TEXT, status TEXT NOT NULL DEFAULT 'pending',
            noted_by TEXT, noted_at TEXT NOT NULL DEFAULT to_char(now(), 'YYYY-MM-DD HH24:MI:SS'),
            decided_by TEXT, decided_at TEXT)""")
        conn.execute("""CREATE TABLE IF NOT EXISTS checkin_link_log (
            id SERIAL PRIMARY KEY, cohort_id INTEGER NOT NULL, contact_id INTEGER NOT NULL, kind TEXT NOT NULL, how TEXT,
            sent_by TEXT, sent_at TEXT NOT NULL DEFAULT to_char(now(), 'YYYY-MM-DD HH24:MI:SS'))""")
        conn.commit()
        _ready["v"] = True

    def _mask(email):
        e = (email or "").strip()
        if "@" not in e:
            return ""
        a, d = e.split("@", 1)
        return (a[:2] + "***@" + d) if len(a) > 2 else (a[:1] + "***@" + d)

    def _can_money():
        f = hooks.get("can_money")
        return bool(f and f())

    def contact_trainings(contact_id):
        """Trainings this person is enrolled in, with payment status. A couple makes ONE payment, so if either partner is paid, both show as paid."""
        try:
            conn = get_db()
            try:
                rows = conn.execute(f"""SELECT p.code, p.name, c.session_number, c.session_date, c.status,
                           e.payment_completed_at AS own_paid, pe.payment_completed_at AS mate_paid,
                           {full_name_sql('pct')} AS partner_name
                    FROM enrollments e JOIN cohorts c ON c.id = e.cohort_id JOIN programs p ON p.id = c.program_id
                    LEFT JOIN enrollments pe ON pe.id = e.partner_enrollment_id
                    LEFT JOIN contacts pct ON pct.id = pe.contact_id
                    WHERE e.contact_id = ? ORDER BY c.session_date DESC""", (contact_id,)).fetchall()
            finally:
                conn.close()
            out = []
            for r in rows:
                paid = r["own_paid"] or r["mate_paid"]
                out.append(dict(label=f"{r['name']} (Session {r['session_number']})", date=r["session_date"], status=r["status"], paid=paid,
                                with_partner=bool(paid and not r["own_paid"] and r["mate_paid"]) or bool(paid and r["partner_name"]),
                                partner=r["partner_name"]))
            return out
        except Exception:
            return []
    app.jinja_env.globals["contact_trainings"] = contact_trainings

    def _need(areas):
        if _allowed(areas):
            return None
        flash("This area is restricted. Ask the Owner to give you Check-in access under HUB Access.")
        return redirect(url_for(".dashboard"))

    def _couples(conn, cohort_id):
        try:
            _ensure_tables(conn)
        except Exception:
            try: conn.rollback()
            except Exception: pass
        try:
            cp.ensure(conn)          # the couple-photo table is created the first time it is needed
        except Exception:
            try: conn.rollback()
            except Exception: pass
        try:
            auto_link(conn, cohort_id)
        except Exception:
            try: conn.rollback()
            except Exception: pass
        rows = conn.execute(f"""SELECT ct.*, e.id AS eid, e.partner_enrollment_id AS pe, e.questionnaire_completed_at AS quest, e.payment_completed_at AS paid,
                   ct.id AS cid, ct.first_name, ct.last_name, {full_name_sql('ct')} AS full_name,
                   (SELECT 1 FROM training_profiles tp WHERE tp.enrollment_id = e.id LIMIT 1) AS has_profile,
                   (SELECT 1 FROM contact_photos cph WHERE cph.contact_id = ct.id LIMIT 1) AS has_photo,
                   cpx.updated_at AS photo_ts
            FROM enrollments e JOIN contacts ct ON ct.id = e.contact_id
            LEFT JOIN couple_photos cpx ON cpx.contact_id = ct.id
            WHERE e.cohort_id = ? ORDER BY ct.last_name, ct.first_name""", (cohort_id,)).fetchall()
        byid = {r["eid"]: r for r in rows}
        pend = {}
        try:
            for p_ in conn.execute("SELECT id, enrollment_id, amount, method, noted_by FROM checkin_payments WHERE cohort_id = ? AND status = 'pending' ORDER BY id", (cohort_id,)).fetchall():
                pend[p_["enrollment_id"]] = p_
        except Exception:
            try: conn.rollback()
            except Exception: pass
        logs = {}
        try:
            for l_ in conn.execute("SELECT contact_id, kind, how, sent_at FROM checkin_link_log WHERE cohort_id = ? ORDER BY id", (cohort_id,)).fetchall():
                logs[(l_["contact_id"], l_["kind"])] = l_
        except Exception:
            try: conn.rollback()
            except Exception: pass
        seen, groups = set(), []
        for r in rows:
            if r["eid"] in seen:
                continue
            seen.add(r["eid"])
            mates = [r]
            pr = byid.get(r["pe"]) if r["pe"] else None
            if pr and pr["eid"] not in seen:
                seen.add(pr["eid"]); mates.append(pr)
            ts = next((m["photo_ts"] for m in mates if m["photo_ts"]), None)
            missing = []
            pm_f = app.jinja_env.globals.get("profile_missing"); ps_f = app.jinja_env.globals.get("personal_missing")
            for m in mates:
                try:
                    m["basic_missing"] = [x for x in pm_f(m) if x != "photo"] if pm_f else []
                    m["personal_missing"] = ps_f(m) if ps_f else []
                except Exception:
                    m["basic_missing"], m["personal_missing"] = [], []
            couple_paid = any(m["paid"] for m in mates)      # a couple makes one payment
            gp = next((pend[m["eid"]] for m in mates if m["eid"] in pend), None)
            for m in mates:
                bits = [w for w, ok in (("basic info", not m["basic_missing"]), ("personal info", not m["personal_missing"]), ("individual photo", m["has_photo"]), ("questionnaire", m["quest"]), ("payment", m["paid"] or couple_paid or gp)) if not ok]
                if bits:
                    missing.append((m["first_name"] or "?") + ": " + ", ".join(bits))
            for m in mates:
                m["paid"] = m["paid"] or (couple_paid and "yes")
                m["pay_state"] = "paid" if m["paid"] else ("pending" if gp else "due")
                m["email_masked"] = _mask(m.get("email"))
                m["q_log"] = logs.get((m["cid"], "questionnaire")); m["p_log"] = logs.get((m["cid"], "profile"))
            groups.append(dict(pending=gp, pay_due=(not couple_paid and not gp), pay_eid=mates[0]["eid"], people=mates, photo_ts=ts, missing=missing, ready=not missing, photo_cid=next((m["cid"] for m in mates if m["photo_ts"]), mates[0]["cid"]),
                               names=" & ".join((m["first_name"] or "") for m in mates) + " " + (mates[0]["last_name"] or "")))
        groups.sort(key=lambda g: (g["people"][0]["last_name"] or "").lower())
        return groups

    def _cohort(conn, cohort_id):
        return conn.execute("""SELECT c.*, p.code, p.name FROM cohorts c JOIN programs p ON p.id = c.program_id WHERE c.id = ?""", (cohort_id,)).fetchone()

    @crm.route("/check-in")
    def checkin_home():
        r = _need(VIEW_AREAS)
        if r: return r
        since = (datetime.now() - timedelta(days=10)).strftime("%Y-%m-%d")
        conn = get_db()
        try:
            rows = conn.execute("""SELECT c.id, c.session_number, c.session_date, c.end_date, c.status, p.code, p.name,
                       (SELECT COUNT(*) FROM enrollments e WHERE e.cohort_id = c.id) AS n
                FROM cohorts c JOIN programs p ON p.id = c.program_id
                WHERE c.session_date >= ? AND c.status <> 'Cancelled' ORDER BY c.session_date, p.code""", (since,)).fetchall()
        finally:
            conn.close()
        pending_n = 0
        if _can_money():
            try:
                conn = get_db()
                try:
                    _ensure_tables(conn)
                    pending_n = conn.execute("SELECT COUNT(*) AS n FROM checkin_payments WHERE status = 'pending'").fetchone()["n"]
                finally:
                    conn.close()
            except Exception:
                pending_n = 0
        return render_template("checkin_home.html", rows=rows, can_photo=_allowed(FULL_AREAS), can_money=_can_money(), pending_n=pending_n)

    @crm.route("/check-in/<int:cohort_id>")
    def checkin_session(cohort_id):
        r = _need(FULL_AREAS)
        if r: return r
        conn = get_db()
        try:
            cohort = _cohort(conn, cohort_id)
            if not cohort:
                abort(404)
            groups = _couples(conn, cohort_id)
        finally:
            conn.close()
        return render_template("checkin_session.html", cohort=cohort, groups=groups, is_couples=(cohort["code"] == "D4"), can_money=_can_money(), fee=(hooks.get("fees") or {}).get(cohort["code"]), methods=hooks.get("methods") or ["Check", "Cash", "Card", "Zelle", "Other"], live=(hooks["live"]() if hooks.get("live") else False))


    RANK = {"Lead Facilitator": 0, "Support Facilitator": 1, "Team Captain": 2, "TA": 3, "Support Team": 4, "Back-up TA": 5}

    @crm.route("/check-in/<int:cohort_id>/team")
    def checkin_team(cohort_id):
        r = _need(VIEW_AREAS)
        if r: return r
        conn = get_db()
        try:
            cohort = _cohort(conn, cohort_id)
            if not cohort:
                abort(404)
            rows = conn.execute(f"""SELECT cs.role, cs.duty, ct.id AS cid, ct.first_name, ct.last_name, {full_name_sql('ct')} AS full_name,
                       ct.cell_phone, ct.home_phone, ct.work_phone
                FROM cohort_staffing cs JOIN contacts ct ON ct.id = cs.contact_id
                WHERE cs.cohort_id = ? AND cs.role <> 'Trainee'""", (cohort_id,)).fetchall()
        finally:
            conn.close()
        people = {}
        for r_ in rows:
            p = people.setdefault(r_["cid"], dict(name=r_["full_name"], last=(r_["last_name"] or "").lower(), first=(r_["first_name"] or "").lower(),
                                                  roles=[], duties=[], rank=9,
                                                  phones=[(lbl, v) for lbl, v in (("Cell", r_["cell_phone"]), ("Home", r_["home_phone"]), ("Work", r_["work_phone"])) if (v or "").strip()]))
            if r_["role"] not in p["roles"]:
                p["roles"].append(r_["role"])
            if r_["duty"] and r_["duty"] not in p["duties"] and r_["duty"] != "Not confirmed":
                p["duties"].append(r_["duty"])
            p["rank"] = min(p["rank"], RANK.get(r_["role"], 8), 2 if (r_["duty"] or "").strip().lower() == "team captain" else 9)
        team = sorted(people.values(), key=lambda p: (p["rank"], p["last"], p["first"]))
        for p in team:
            p["phones"] = [(lbl, v, re.sub(r"[^\d+]", "", v)) for lbl, v in p["phones"]]
        return render_template("checkin_team.html", cohort=cohort, team=team, can_photo=_allowed(FULL_AREAS))

    @crm.route("/check-in/<int:cohort_id>/photos")
    def checkin_photos(cohort_id):
        r = _need(VIEW_AREAS)
        if r: return r
        conn = get_db()
        try:
            cohort = _cohort(conn, cohort_id)
            if not cohort:
                abort(404)
            groups = _couples(conn, cohort_id)
        finally:
            conn.close()
        return render_template("checkin_photos.html", cohort=cohort, groups=groups, can_photo=_allowed(FULL_AREAS))

    @crm.route("/check-in/<int:cohort_id>/photo/<int:contact_id>", methods=["POST"])
    def checkin_photo_save(cohort_id, contact_id):
        if not _allowed(FULL_AREAS):
            return jsonify(ok=False, error="Not allowed"), 403
        res = process_photo(request.files.get("photo"))
        if not res:
            return jsonify(ok=False, error="That photo could not be read. Please try again."), 400
        conn = get_db()
        try:
            ok = conn.execute("SELECT 1 FROM enrollments WHERE cohort_id = ? AND contact_id = ?", (cohort_id, contact_id)).fetchone()
            if not ok:
                return jsonify(ok=False, error="That person is not in this session."), 404
            pid = cp.save_couple_photo(conn, contact_id, res[0], res[1], session.get("staff_name"))
            ts = conn.execute("SELECT updated_at FROM couple_photos WHERE contact_id = ?", (contact_id,)).fetchone()["updated_at"]
        finally:
            conn.close()
        return jsonify(ok=True, both=bool(pid), url=url_for(".checkin_photo_file", cohort_id=cohort_id, contact_id=contact_id, v=ts))

    @crm.route("/check-in/<int:cohort_id>/individual/<int:contact_id>", methods=["POST"])
    def checkin_individual_save(cohort_id, contact_id):
        """Greeter takes the person's own (individual) photo; it is saved on their contact page."""
        if not _allowed(FULL_AREAS) or upsert_photo is None:
            return jsonify(ok=False, error="Not allowed"), 403
        res = process_photo(request.files.get("photo"))
        if not res:
            return jsonify(ok=False, error="That photo could not be read. Please try again."), 400
        conn = get_db()
        try:
            ok = conn.execute("SELECT 1 FROM enrollments WHERE cohort_id = ? AND contact_id = ?", (cohort_id, contact_id)).fetchone()
            if not ok:
                return jsonify(ok=False, error="That person is not in this session."), 404
            upsert_photo(conn, contact_id, res[0], res[1])
            conn.commit()
        finally:
            conn.close()
        return jsonify(ok=True)


    # ---------- payments noted at the table (greeter notes it; Leadership / Accounting confirm it) ----------
    @crm.route("/check-in/<int:cohort_id>/pay/<int:enrollment_id>", methods=["POST"])
    def checkin_pay_note(cohort_id, enrollment_id):
        if not _allowed(FULL_AREAS):
            flash("Not allowed.")
            return redirect(url_for(".dashboard"))
        try:
            amount = float(str(request.form.get("amount") or "").replace("$", "").replace(",", "").strip())
        except ValueError:
            amount = None
        methods = hooks.get("methods") or ["Check", "Cash", "Card", "Zelle", "Other"]
        method = request.form.get("method") if request.form.get("method") in methods else None
        conn = get_db()
        try:
            _ensure_tables(conn)
            e = conn.execute("SELECT id, contact_id, partner_enrollment_id FROM enrollments WHERE id = ? AND cohort_id = ?", (enrollment_id, cohort_id)).fetchone()
            if not e:
                flash("That person is not in this session.")
            elif not amount or amount <= 0:
                flash("Please enter the amount received, for example 1299.")
            else:
                ids = [enrollment_id] + ([e["partner_enrollment_id"]] if e["partner_enrollment_id"] else [])
                dup = conn.execute("SELECT 1 FROM checkin_payments WHERE status = 'pending' AND enrollment_id IN (" + ",".join("?" for _ in ids) + ")", ids).fetchone()
                if dup:
                    flash("A payment is already noted for this couple and is waiting to be confirmed.")
                else:
                    conn.execute("INSERT INTO checkin_payments (cohort_id, enrollment_id, contact_id, amount, method, reference, noted_by) VALUES (?,?,?,?,?,?,?)",
                                 (cohort_id, enrollment_id, e["contact_id"], amount, method, (request.form.get("reference") or "").strip()[:80] or None, session.get("staff_name")))
                    conn.commit()
                    flash("Payment noted. It shows as paid at the table until it is confirmed.")
        finally:
            conn.close()
        return redirect(url_for(".checkin_session", cohort_id=cohort_id))

    @crm.route("/check-in/<int:cohort_id>/pay-cancel/<int:pay_id>", methods=["POST"])
    def checkin_pay_cancel(cohort_id, pay_id):
        if not _allowed(FULL_AREAS):
            return redirect(url_for(".dashboard"))
        conn = get_db()
        try:
            _ensure_tables(conn)
            conn.execute("UPDATE checkin_payments SET status = 'cancelled', decided_by = ?, decided_at = to_char(now(), 'YYYY-MM-DD HH24:MI:SS') WHERE id = ? AND cohort_id = ? AND status = 'pending'",
                         (session.get("staff_name"), pay_id, cohort_id))
            conn.commit()
        finally:
            conn.close()
        flash("The noted payment was removed.")
        return redirect(url_for(".checkin_session", cohort_id=cohort_id))

    @crm.route("/check-in/payments")
    def checkin_payments():
        if not _can_money():
            flash("Confirming payments is limited to Leadership and the accountant or bookkeeper.")
            return redirect(url_for(".checkin_home"))
        conn = get_db()
        try:
            _ensure_tables(conn)
            rows = conn.execute(f"""SELECT cp.*, c.session_number, c.session_date, p.name AS program, {full_name_sql('ct')} AS full_name,
                       (SELECT {full_name_sql('pc')} FROM enrollments pe JOIN contacts pc ON pc.id = pe.contact_id WHERE pe.id = e.partner_enrollment_id) AS partner_name
                FROM checkin_payments cp JOIN cohorts c ON c.id = cp.cohort_id JOIN programs p ON p.id = c.program_id
                JOIN enrollments e ON e.id = cp.enrollment_id JOIN contacts ct ON ct.id = cp.contact_id
                WHERE cp.status = 'pending' ORDER BY cp.id""").fetchall()
        finally:
            conn.close()
        return render_template("checkin_payments.html", rows=rows, methods=hooks.get("methods") or [])

    @crm.route("/check-in/payments/<int:pay_id>/confirm", methods=["POST"])
    @money_required
    def checkin_pay_confirm(pay_id):
        conn = get_db()
        try:
            _ensure_tables(conn)
            if hooks.get("ensure"):
                hooks["ensure"]()
            row = conn.execute("SELECT * FROM checkin_payments WHERE id = ? AND status = 'pending'", (pay_id,)).fetchone()
            if not row:
                flash("That payment was already handled.")
            else:
                form = {"amount": request.form.get("amount") or row["amount"], "method": request.form.get("method") or row["method"],
                        "completes": "1" if request.form.get("completes") else "", "reference": row["reference"] or "",
                        "note": f"Taken at check-in by {row['noted_by']}", "paid_on": datetime.now().strftime("%Y-%m-%d")}
                _c, msg = hooks["record"](conn, row["enrollment_id"], form)
                if msg.startswith("Please enter"):
                    flash(msg)
                else:
                    conn.execute("UPDATE checkin_payments SET status = 'confirmed', decided_by = ?, decided_at = to_char(now(), 'YYYY-MM-DD HH24:MI:SS') WHERE id = ?",
                                 (session.get("staff_name"), pay_id))
                    conn.commit()
                    flash("Confirmed. " + msg)
        finally:
            conn.close()
        return redirect(url_for(".checkin_payments"))

    @crm.route("/check-in/payments/<int:pay_id>/reject", methods=["POST"])
    @money_required
    def checkin_pay_reject(pay_id):
        conn = get_db()
        try:
            _ensure_tables(conn)
            conn.execute("UPDATE checkin_payments SET status = 'rejected', decided_by = ?, decided_at = to_char(now(), 'YYYY-MM-DD HH24:MI:SS') WHERE id = ? AND status = 'pending'",
                         (session.get("staff_name"), pay_id))
            conn.commit()
        finally:
            conn.close()
        flash("Not confirmed. The trainee shows as payment due again.")
        return redirect(url_for(".checkin_payments"))

    # ---------- greeter sends (or shows a QR for) the trainee's own questionnaire / profile link ----------
    def _link_person(conn, cohort_id, enrollment_id, kind):
        e = conn.execute(f"""SELECT e.id AS eid, e.partner_enrollment_id AS pe, ct.id AS cid, ct.first_name, ct.email, {full_name_sql('ct')} AS full_name,
                   (SELECT {full_name_sql('pc')} FROM enrollments pe2 JOIN contacts pc ON pc.id = pe2.contact_id WHERE pe2.id = e.partner_enrollment_id) AS partner_name
            FROM enrollments e JOIN contacts ct ON ct.id = e.contact_id WHERE e.id = ? AND e.cohort_id = ?""", (enrollment_id, cohort_id)).fetchone()
        if not e or kind not in ("questionnaire", "profile"):
            return None, None
        person = {"contact_id": e["cid"], "enrollment_id": e["eid"], "first_name": e["first_name"], "email": e["email"], "name": e["full_name"],
                  "roles": [], "duties": [], "partner_name": e["partner_name"]}
        link = hooks["q_link"](e["eid"]) if kind == "questionnaire" else hooks["p_link"](e["cid"])
        return person, link

    def _log_link(conn, cohort_id, contact_id, kind, how):
        conn.execute("INSERT INTO checkin_link_log (cohort_id, contact_id, kind, how, sent_by) VALUES (?,?,?,?,?)",
                     (cohort_id, contact_id, kind, how, session.get("staff_name")))
        conn.commit()

    @crm.route("/check-in/<int:cohort_id>/send-link/<int:enrollment_id>/<kind>", methods=["POST"])
    def checkin_send_link(cohort_id, enrollment_id, kind):
        if not _allowed(FULL_AREAS) or not hooks.get("q_link"):
            flash("Not allowed.")
            return redirect(url_for(".dashboard"))
        conn = get_db()
        try:
            _ensure_tables(conn)
            cohort = _cohort(conn, cohort_id)
            person, link = _link_person(conn, cohort_id, enrollment_id, kind)
            if not person or not cohort:
                flash("That person is not in this session.")
            elif not hooks["live"]():
                flash("Sending email to people is switched off for now. Use Show QR code instead.")
            elif not (person["email"] or "").strip():
                flash(f"{person['first_name']} has no email on file. Use Show QR code instead.")
            else:
                key = "questionnaire_request" if kind == "questionnaire" else "seminar_registration"
                subject, html, text = hooks["letter_for"](cohort, person, key)
                try:
                    hooks["send_email"](to_email=person["email"], to_name=person["first_name"], subject=subject, html_content=html, text_content=text)
                    _log_link(conn, cohort_id, person["contact_id"], kind, "email")
                    flash(f"Link emailed to {_mask(person['email'])}.")
                except hooks["email_err"] as ex:
                    flash(f"The email could not be sent ({ex}). Use Show QR code instead.")
        finally:
            conn.close()
        return redirect(url_for(".checkin_session", cohort_id=cohort_id))

    @crm.route("/check-in/<int:cohort_id>/qr/<int:enrollment_id>/<kind>")
    def checkin_qr(cohort_id, enrollment_id, kind):
        r = _need(FULL_AREAS)
        if r: return r
        if not hooks.get("q_link"):
            abort(404)
        conn = get_db()
        try:
            _ensure_tables(conn)
            person, link = _link_person(conn, cohort_id, enrollment_id, kind)
            if not person or not link:
                abort(404)
            _log_link(conn, cohort_id, person["contact_id"], kind, "QR")
        finally:
            conn.close()
        svg = ""
        try:
            from reportlab.graphics.barcode.qr import QrCodeWidget
            from reportlab.graphics.shapes import Drawing
            from reportlab.graphics import renderSVG
            w = QrCodeWidget(link); b = w.getBounds(); W = b[2] - b[0]; H = b[3] - b[1]
            d = Drawing(320, 320, transform=[320. / W, 0, 0, 320. / H, 0, 0]); d.add(w)
            svg = renderSVG.drawToString(d)
            svg = svg[svg.find("<svg"):]
        except Exception:
            svg = ""
        return render_template("checkin_qr.html", cohort_id=cohort_id, person=person, kind=kind, svg=svg, link=link)

    @crm.route("/check-in/<int:cohort_id>/photo-file/<int:contact_id>")
    def checkin_photo_file(cohort_id, contact_id):
        if not _allowed(VIEW_AREAS):
            abort(403)
        conn = get_db()
        try:
            row = conn.execute("""SELECT cp.data, cp.content_type FROM couple_photos cp
                                  WHERE cp.contact_id = ? AND EXISTS (SELECT 1 FROM enrollments e WHERE e.cohort_id = ? AND e.contact_id = cp.contact_id)""",
                               (contact_id, cohort_id)).fetchone()
        finally:
            conn.close()
        if not row:
            abort(404)
        resp = make_response(bytes(row["data"]))
        resp.headers["Content-Type"] = row["content_type"] or "image/jpeg"
        resp.headers["Cache-Control"] = "private, max-age=3600"
        return resp
