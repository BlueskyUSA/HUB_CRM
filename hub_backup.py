"""Download a backup (Owner and Administrators): one ZIP with every table in the Hub as a spreadsheet (CSV) file.
Left out on purpose: password hashes, private login links and tokens, and uploaded files (photos, videos, music)."""
import csv
import io
import zipfile
from datetime import datetime
from flask import request, session, make_response, redirect, url_for, flash

SKIP_TABLES = {"import_staging"}           # temporary working data
SKIP_COL_WORDS = ("password", "token", "secret")


def register(app, crm, owner_required, get_db):
    @crm.route("/download-backup", methods=["POST"])
    @owner_required
    def download_backup():
        conn = get_db()
        try:
            tables = [r["table_name"] for r in conn.execute(
                "SELECT table_name FROM information_schema.tables WHERE table_schema = 'public' AND table_type = 'BASE TABLE' ORDER BY table_name").fetchall()]
            buf = io.BytesIO()
            counts, skipped_cols = [], []
            with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
                for t in tables:
                    if t in SKIP_TABLES or t.startswith("pg_"):
                        continue
                    cols = []
                    for r in conn.execute("SELECT column_name, data_type FROM information_schema.columns WHERE table_schema = 'public' AND table_name = ? ORDER BY ordinal_position", (t,)).fetchall():
                        name, typ = r["column_name"], r["data_type"]
                        if typ == "bytea" or any(w in name.lower() for w in SKIP_COL_WORDS):
                            skipped_cols.append(f"{t}.{name}")
                        else:
                            cols.append(name)
                    if not cols:
                        continue
                    rows = conn.execute("SELECT " + ", ".join(f'"{c}"' for c in cols) + f' FROM "{t}"').fetchall()
                    out = io.StringIO(); w = csv.writer(out)
                    w.writerow(cols)
                    for row in rows:
                        w.writerow(["" if row[c] is None else row[c] for c in cols])
                    z.writestr(f"{t}.csv", out.getvalue())
                    counts.append((t, len(rows)))
                stamp = datetime.now().strftime("%Y-%m-%d %H:%M")
                readme = [f"Hub backup made {stamp} by {session.get('staff_name')}", "",
                          "Each file is one table of the Hub, as a spreadsheet (CSV). Open them in Excel or Numbers.", "",
                          "KEEP THIS FILE SAFE. It contains private information about contacts, donors and volunteers.",
                          "Store it somewhere private (for example a locked Dropbox folder), not in email.", "",
                          "NOT included on purpose:", "  - password hashes, private login links and tokens",
                          "  - uploaded files (photos, videos, music)", "  - Render's settings and secret keys", "",
                          "Rows per table:"] + [f"  {t}: {n}" for t, n in counts] + ["", "Columns left out: " + (", ".join(skipped_cols) or "none")]
                z.writestr("README.txt", "\n".join(readme))
        except Exception as e:
            print(f"Backup failed: {e}", flush=True)
            try: conn.rollback()
            except Exception: pass
            conn.close()
            flash("The backup could not be made. Nothing was changed. Please tell Claude.")
            return redirect(url_for(".owner_instructions") + "#backup")
        finally:
            try: conn.close()
            except Exception: pass
        resp = make_response(buf.getvalue())
        resp.headers["Content-Type"] = "application/zip"
        resp.headers["Content-Disposition"] = f"attachment; filename=Hub-backup-{datetime.now().strftime('%Y-%m-%d')}.zip"
        resp.headers["Cache-Control"] = "no-store"
        return resp
