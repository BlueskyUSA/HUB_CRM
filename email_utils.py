"""
Outbound email, sent through Brevo's transactional email API.

Why Brevo: free tier (300 emails/day, no expiration, no credit card) is
enough for both the "Excitement is Building" blast and the automated
follow-up emails triggered by the short/long form flow. See BREVO_API_KEY
in Render's Environment settings -- never hardcoded here.

This module is deliberately just a thin wrapper around Brevo's API. It
doesn't know anything about contacts, templates, or the send queue --
those live in app.py and the (future) blast-queue logic, and call
send_email() one message at a time.
"""
import os
import time
import requests

BREVO_API_URL = "https://api.brevo.com/v3/smtp/email"

# Render's outbound connections to Brevo occasionally drop ("connection reset",
# "SSL EOF"). Those are connection-level blips, so we retry them a couple of
# times before giving up. We do NOT retry read timeouts or Brevo error replies.
SEND_ATTEMPTS = 3
RETRY_DELAY_SECONDS = 2

# The address/name every CRM email is sent from. Brevo requires this
# address to be a "verified sender" (either the whole blueskyusa.net domain,
# or this specific address) before it will actually deliver -- see the
# Senders & IP section of the Brevo dashboard.
DEFAULT_FROM_EMAIL = os.environ.get("EMAIL_FROM_ADDRESS", "kent@blueskyusa.net")
DEFAULT_FROM_NAME = os.environ.get("EMAIL_FROM_NAME", "Kent Hafemann")


class EmailSendError(Exception):
    """Raised when Brevo rejects or fails to send a message."""


def _send_email_raw(to_email, subject, html_content, to_name=None, text_content=None,
                from_email=None, from_name=None, reply_to=None, attachments=None, bcc=None, headers=None):
    """Sends one email through Brevo. Returns Brevo's message id on success.
    Raises EmailSendError on any failure (missing API key, bad request,
    Brevo-side error, network problem) -- callers decide how to handle
    that (e.g. leave a contact's "email sent" timestamp unset so a daily
    queue retries them later)."""
    api_key = os.environ.get("BREVO_API_KEY")
    if not api_key:
        raise EmailSendError("BREVO_API_KEY is not set in the environment.")

    payload = {
        "sender": {"email": from_email or DEFAULT_FROM_EMAIL, "name": from_name or DEFAULT_FROM_NAME},
        "to": [{"email": to_email, **({"name": to_name} if to_name else {})}],
        "subject": subject,
        "htmlContent": html_content,
    }
    if text_content:
        payload["textContent"] = text_content
    if reply_to:
        payload["replyTo"] = {"email": reply_to}
    if bcc:  # a copy to the sender, so it also shows in their own inbox
        payload["bcc"] = [{"email": bcc}]
    if headers:  # extra mail headers (for example List-Unsubscribe)
        payload["headers"] = dict(headers)
    if attachments:  # list of (filename, bytes)
        import base64
        payload["attachment"] = [{"name": n, "content": base64.b64encode(b).decode("ascii")} for n, b in attachments]

    resp = None
    for attempt in range(1, SEND_ATTEMPTS + 1):
        try:
            resp = requests.post(
                BREVO_API_URL,
                json=payload,
                headers={
                    "api-key": api_key,
                    "Content-Type": "application/json",
                    "Accept": "application/json",
                },
                timeout=15,
            )
            break
        except requests.ConnectionError as e:  # includes SSL errors and resets
            if attempt < SEND_ATTEMPTS:
                print(f"Brevo connection problem (attempt {attempt}/{SEND_ATTEMPTS}), retrying: {e}", flush=True)
                time.sleep(RETRY_DELAY_SECONDS * attempt)
                continue
            raise EmailSendError(f"Network error contacting Brevo: {e}") from e
        except requests.RequestException as e:
            raise EmailSendError(f"Network error contacting Brevo: {e}") from e

    if resp.status_code == 400 and payload.get("headers"):
        # if Brevo does not accept the extra headers, send the same email without them rather than not at all
        payload.pop("headers", None)
        try:
            resp = requests.post(BREVO_API_URL, json=payload, headers={"api-key": api_key, "Content-Type": "application/json", "Accept": "application/json"}, timeout=15)
        except requests.RequestException as e2:
            raise EmailSendError(f"Network error contacting Brevo: {e2}") from e2
    if resp.status_code not in (200, 201):
        raise EmailSendError(f"Brevo rejected the send ({resp.status_code}): {resp.text}")

    return resp.json().get("messageId")


# ---- a record of every email the app sends (set up by app.py) ----
_SEND_LOGGER = {"fn": None}


def set_send_logger(fn):
    """fn(to_email, subject, html, message_id, bcc, status) is called after every send attempt."""
    _SEND_LOGGER["fn"] = fn


def _note_send(to_email, subject, html_content, message_id, bcc, status):
    fn = _SEND_LOGGER["fn"]
    if not fn:
        return
    try:
        fn(to_email, subject, html_content, message_id, bcc, status)
    except Exception as e:  # recording must never break a send
        print(f"Couldn't record outgoing email to {to_email}: {e}", flush=True)


def send_email(to_email, subject, html_content, to_name=None, text_content=None,
               from_email=None, from_name=None, reply_to=None, attachments=None, bcc=None, headers=None):
    """Sends one email through Brevo (see _send_email_raw) and keeps a record of the attempt."""
    try:
        message_id = _send_email_raw(to_email, subject, html_content, to_name=to_name, text_content=text_content,
                                     from_email=from_email, from_name=from_name, reply_to=reply_to,
                                     attachments=attachments, bcc=bcc, headers=headers)
    except Exception as e:
        _note_send(to_email, subject, html_content, None, bcc, "Failed: " + str(e)[:300])
        raise
    _note_send(to_email, subject, html_content, message_id, bcc, "Accepted by Brevo")
    return message_id
