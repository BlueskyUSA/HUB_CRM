"""One switch for the program name shown to people.

Everything in the Hub and the public site is written with the name Sojourn. Setting BRAND_NAME=Discovery in
Render's Environment makes every page, letter and email show Discovery instead (same layout, waves and colors),
using the Discovery logo pictures. Remove the setting (or set it to Sojourn) to go back. Nothing is lost either way."""
import hashlib
import os

_SPAN_BANG = '<span style="color:#FF0000">!</span>'


def current():
    return (os.environ.get("BRAND_NAME", "") or "Sojourn").strip() or "Sojourn"


def active():
    """True when the name is being swapped (anything other than Sojourn)."""
    return current().lower() != "sojourn"


def _sojourn_logo_token():
    try:
        p = os.path.join(os.path.dirname(os.path.abspath(__file__)), "static", "sojourn-logo-email.png")
        with open(p, "rb") as f:
            return hashlib.sha256(f.read()).hexdigest()[:32]
    except Exception:
        return None


def swap(text):
    """Rewrites text (a page, a letter or an email) for the chosen name. Does nothing when the name is Sojourn."""
    if not text or not active():
        return text
    name = current()
    # sentences that only make sense for the Sojourn name
    text = text.replace("when our former program closed", "when " + name + _SPAN_BANG + " closed")
    text = text.replace("our former training closed in 2020", "the " + name + " training closed in 2020")
    # "Discovery" is a longer word than "Sojourn": give the waves under it a matching length
    text = text.replace("width: 3.1em; height: .3em; margin: .06em 0 .02em .32em;", "width: 3.9em; height: .3em; margin: .06em 0 .02em .3em;")
    # logo pictures
    text = text.replace("sojourn-logo-email.png", "discovery-logo-email.png").replace("sojourn-logo.svg", "discovery-logo.svg")
    tok = _sojourn_logo_token()
    if tok and ("/email-images/" + tok) in text:
        text = text.replace("/email-images/" + tok, "/static/discovery-logo-email.png")
    # the name itself (capital S only: web addresses such as sojourn.blueskyusa.net stay as they are)
    return text.replace("Sojourn", name)
