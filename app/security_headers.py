"""SR9: browser-side defences. Every response carries the same strict set of headers.

The most important one is the Content-Security-Policy (CSP). It tells the browser which
places a page may load things from, so even if an attacker managed to inject HTML, the
browser would refuse to run their script. This site needs very little:
  - its own scripts, styles, fonts and images ('self').
Since v2 the Inter font is served from static/fonts, so no third party is trusted at all.
There are no inline scripts or styles anywhere, so 'unsafe-inline' is never needed.
"""
from flask import Flask, request
from flask_login import current_user
from flask_talisman import Talisman

CSP = {
    "default-src": "'self'",
    "script-src": "'self'",
    "style-src": "'self'",
    "font-src": "'self'",
    "img-src": "'self'",
    "object-src": "'none'",         # no Flash, Java or other plugins
    "base-uri": "'self'",           # an injected <base> tag can't redirect relative links
    "form-action": "'self'",        # forms can only be sent to this site
    "frame-ancestors": "'none'",    # nobody may put this site in a frame (clickjacking)
}

# Browser features the site never uses are switched off.
PERMISSIONS_POLICY = {
    "geolocation": "()", "camera": "()", "microphone": "()",
    "payment": "()", "usb": "()", "interest-cohort": "()",
}

# Pages whose content is personal or holds a form token must never be kept in a cache,
# so the browser's Back button can't show them after logging out.
PRIVATE_AREAS = ("auth.", "bookings.", "admin.")

talisman = Talisman()


def init_security_headers(app: Flask) -> None:
    talisman.init_app(
        app,
        force_https=app.config["FORCE_HTTPS"],
        strict_transport_security=True,
        strict_transport_security_max_age=31_536_000,   # one year
        strict_transport_security_include_subdomains=True,
        content_security_policy=CSP,
        frame_options="DENY",
        referrer_policy="strict-origin-when-cross-origin",
        permissions_policy=PERMISSIONS_POLICY,
        session_cookie_secure=app.config["SESSION_COOKIE_SECURE"],
        session_cookie_http_only=app.config["SESSION_COOKIE_HTTPONLY"],
        session_cookie_samesite=app.config["SESSION_COOKIE_SAMESITE"],
    )
    app.after_request(add_extra_headers)


def add_extra_headers(response):
    response.headers.setdefault("Cross-Origin-Opener-Policy", "same-origin")
    response.headers.setdefault("Cross-Origin-Resource-Policy", "same-origin")

    endpoint = request.endpoint or ""
    if endpoint != "static" and (endpoint.startswith(PRIVATE_AREAS) or current_user.is_authenticated):
        response.headers["Cache-Control"] = "no-store"
    return response
