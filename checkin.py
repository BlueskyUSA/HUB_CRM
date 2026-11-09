"""Greeter check-in table: the greeter logs in, opens the session, taps a couple, takes the couple photo with the computer's or
iPad's camera, and it is saved on both partners' pages. Also shows what is still missing (payment, questionnaire, profile).
A 'Photo board' page shows every couple's photo for the session so TAs can remember who they are visiting with."""
import re
from datetime import datetime, timedelta
from flask import render_template, request, session, redirect, url_for, flash, jsonify, abort, make_response

FULL_AREAS = ("checkin", "contacts")                      # may take photos
VIEW_AREAS = ("checkin", "contacts", "trainee_roster", "session_team")   # may see the photo board


def register(app, crm, get_db, has_area_access, auto_link, full_name_sql, process_photo, cp, upsert_photo=None):
    def _allowed(areas):
        return bool(session.get("is_owner")) or any(has_area_access(a) for a in areas)

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
            cp.ensure(conn)          # the couple-photo table is created the first time it is needed
        except Exception:
            try: conn.rollback()
            except Exception: pass
        try:
            auto_link(conn, cohort_id)
        except Exception:
            try: conn.rollback()
            except Exception: pass
        rows = conn.execute(f"""SELECT e.id AS eid, e.partner_enrollment_id AS pe, e.questionnaire_completed_at AS quest, e.payment_completed_at AS paid,
                   ct.id AS cid, ct.first_name, ct.last_name, {full_name_sql('ct')} AS full_name,
                   (SELECT 1 FROM training_profiles tp WHERE tp.enrollment_id = e.id LIMIT 1) AS has_profile,
                   (SELECT 1 FROM contact_photos cph WHERE cph.contact_id = ct.id LIMIT 1) AS has_photo,
                   cpx.updated_at AS photo_ts
            FROM enrollments e JOIN contacts ct ON ct.id = e.contact_id
            LEFT JOIN couple_photos cpx ON cpx.contact_id = ct.id
            WHERE e.cohort_id = ? ORDER BY ct.last_name, ct.first_name""", (cohort_id,)).fetchall()
        byid = {r["eid"]: r for r in rows}
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
            couple_paid = any(m["paid"] for m in mates)      # a couple makes one payment
            for m in mates:
                bits = [w for w, ok in (("individual photo", m["has_photo"]), ("questionnaire", m["quest"]), ("payment", m["paid"] or couple_paid)) if not ok]
                if bits:
                    missing.append((m["first_name"] or "?") + ": " + ", ".join(bits))
            for m in mates:
                m["paid"] = m["paid"] or (couple_paid and "yes")
            groups.append(dict(people=mates, photo_ts=ts, missing=missing, ready=not missing, photo_cid=next((m["cid"] for m in mates if m["photo_ts"]), mates[0]["cid"]),
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
        return render_template("checkin_home.html", rows=rows, can_photo=_allowed(FULL_AREAS))

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
        return render_template("checkin_session.html", cohort=cohort, groups=groups, is_couples=(cohort["code"] == "D4"))


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
