"""
One-off: sends a single test email to khres53@gmail.com with links to both
the short form (/discovery) and the long form (/complete-profile), so Kent
can click through and test them end-to-end.

This is NOT wired into any route -- just a script to run by hand, once,
from the Render shell (where BREVO_API_KEY is actually set):

    python3 send_test_form_invite.py

Safe to run more than once -- it just sends another copy of the same email.
"""
from email_utils import send_email, EmailSendError

TO_EMAIL = "khres53@gmail.com"
SITE_BASE = "https://sojourn.blueskyusa.net"
SHORT_FORM_URL = f"{SITE_BASE}/discovery"
LONG_FORM_URL = f"{SITE_BASE}/complete-profile"

SUBJECT = "Test invite: Dallas Discovery short + long form"

HTML_CONTENT = f"""
    <p>Hi Kent,</p>
    <p>Here are both forms to test:</p>
    <p><strong>Short form</strong> (the volunteer/TA sign-up page):<br>
    <a href="{SHORT_FORM_URL}">{SHORT_FORM_URL}</a></p>
    <p><strong>Long form</strong> (the full self-service profile):<br>
    <a href="{LONG_FORM_URL}">{LONG_FORM_URL}</a></p>
"""

TEXT_CONTENT = f"""Hi Kent,

Here are both forms to test:

Short form (the volunteer/TA sign-up page):
{SHORT_FORM_URL}

Long form (the full self-service profile):
{LONG_FORM_URL}
"""


def main():
    try:
        message_id = send_email(
            to_email=TO_EMAIL,
            subject=SUBJECT,
            html_content=HTML_CONTENT,
            text_content=TEXT_CONTENT,
        )
    except EmailSendError as e:
        print(f"FAILED to send: {e}")
        return
    print(f"Sent to {TO_EMAIL} -- Brevo message id: {message_id}")


if __name__ == "__main__":
    main()
