"""
The ONE place for the program's public name and web address.

To rename the program or move it to a new web address you do NOT need to edit
code. Set these in Render -> your service -> Environment, then redeploy:

    PROGRAM_NAME      e.g.  Bluesky Life Training Seminars
    PUBLIC_BASE_URL   e.g.  https://www.example.org   (no trailing slash needed)

If they aren't set, the defaults below are used (the current name and address).

Used by: every page title / header / footer (as {{ program_name }}), the email
subjects and copy, and the link people are given to the sign-up page.

NOT changed automatically (these need a human rewrite if the name changes):
sentences that talk about the program's HISTORY under its old name, e.g. "In
2020 when the Dallas Discovery program closed...", and the stored volunteer
role labels like "Dallas Discovery Volunteer" in saved records.
"""
import os

PROGRAM_NAME = os.environ.get("PROGRAM_NAME", "Sojourn").strip() or "Sojourn"
PUBLIC_BASE_URL = (
    os.environ.get("PUBLIC_BASE_URL", "https://dallas-discovery-crm.onrender.com").strip().rstrip("/")
)
# The public sign-up page people are sent to from the emails.
DISCOVERY_URL = PUBLIC_BASE_URL + "/discovery"
