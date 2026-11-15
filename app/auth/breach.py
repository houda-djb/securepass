"""Is this password known from a data breach? (Phase 32)

Uses the free "Have I Been Pwned" range service. Only the first 5 characters of the password's
SHA-1 hash leave this server, never the password and never the full hash, and the answer is
matched here. If the service can't be reached the check is skipped: signing up must not break
because a third-party site is down.
"""
import hashlib
import urllib.request

from flask import current_app, has_app_context

RANGE_URL = "https://api.pwnedpasswords.com/range/"
TIMEOUT_SECONDS = 3


def _fetch_range(prefix: str) -> str:
    request = urllib.request.Request(RANGE_URL + prefix, headers={"Add-Padding": "true", "User-Agent": "SecurePass"})
    with urllib.request.urlopen(request, timeout=TIMEOUT_SECONDS) as reply:  # nosec B310
        return reply.read().decode("ascii", "replace")


def is_breached(password: str) -> bool:
    if not has_app_context() or not current_app.config.get("BREACH_CHECK"):
        return False
    # SHA-1 is what the service uses to look passwords up; it is not used to protect anything here.
    digest = hashlib.sha1(password.encode(), usedforsecurity=False).hexdigest().upper()
    prefix, suffix = digest[:5], digest[5:]
    try:
        body = _fetch_range(prefix)
    except Exception:  # noqa: BLE001 - any network problem means "could not check", never a failure
        current_app.logger.warning("Breach check skipped: the service could not be reached.")
        return False
    for line in body.splitlines():
        found, _, count = line.partition(":")
        if found.strip() == suffix and count.strip() not in ("", "0"):  # padded lines have count 0
            return True
    return False
