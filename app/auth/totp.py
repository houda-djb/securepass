"""Two-factor login with an authenticator app (RFC 6238 time-based one-time passwords).

Written with the standard library only, so there is nothing extra to trust or install.
The app (Google Authenticator, Microsoft Authenticator, Authy, 1Password...) and the server
share a secret; both turn "the current 30-second slot" plus the secret into a 6-digit code.
"""
import base64
import hashlib
import hmac
import secrets
import struct
import time
from urllib.parse import quote

STEP_SECONDS = 30
DIGITS = 6
WINDOW = 1                      # also accept the slot before and after, for slightly wrong clocks
RECOVERY_COUNT = 8
RECOVERY_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"   # no 0/O or 1/I


def new_secret() -> str:
    """20 random bytes (160 bits) as base32, the format authenticator apps expect."""
    return base64.b32encode(secrets.token_bytes(20)).decode("ascii")


def _hotp(secret: str, counter: int) -> str:
    key = base64.b32decode(secret.upper() + "=" * (-len(secret) % 8))
    digest = hmac.new(key, struct.pack(">Q", counter), hashlib.sha1).digest()
    offset = digest[-1] & 0x0F
    number = (struct.unpack(">I", digest[offset:offset + 4])[0] & 0x7FFFFFFF) % 10 ** DIGITS
    return str(number).zfill(DIGITS)


def current_step(now: float | None = None) -> int:
    return int((time.time() if now is None else now) // STEP_SECONDS)


def code_at(secret: str, step: int) -> str:
    return _hotp(secret, step)


def verify(secret: str, code: str, last_step: int | None = None, now: float | None = None) -> int | None:
    """Return the time slot the code belongs to, or None if it is wrong or already used.

    `last_step` is the newest slot already accepted for this user: a code from that slot
    (or an older one) is refused, so a code seen over someone's shoulder can't be replayed.
    """
    code = (code or "").strip().replace(" ", "")
    if not (code.isascii() and code.isdigit() and len(code) == DIGITS):
        return None
    step_now = current_step(now)
    match = None
    for step in range(step_now - WINDOW, step_now + WINDOW + 1):
        if hmac.compare_digest(_hotp(secret, step), code):   # compare every slot: no early exit
            match = step
    if match is None or (last_step is not None and match <= last_step):
        return None
    return match


def otpauth_uri(secret: str, email: str, issuer: str = "SecurePass") -> str:
    label = quote(f"{issuer}:{email}", safe="")
    return f"otpauth://totp/{label}?secret={secret}&issuer={quote(issuer)}&digits={DIGITS}&period={STEP_SECONDS}"


def readable(secret: str) -> str:
    """The secret in groups of four, easier to type by hand."""
    return " ".join(secret[i:i + 4] for i in range(0, len(secret), 4))


# ---------------------------------------------------------------- recovery codes

def new_recovery_codes(count: int = RECOVERY_COUNT) -> list[str]:
    def one() -> str:
        raw = "".join(secrets.choice(RECOVERY_ALPHABET) for _ in range(10))
        return f"{raw[:5]}-{raw[5:]}"
    return [one() for _ in range(count)]


def normalise_recovery(code: str) -> str:
    return (code or "").strip().upper().replace(" ", "").replace("-", "")


def hash_recovery(code: str, key: str) -> str:
    """Keyed hash. The codes are long and random, so a fast hash is enough, and the key
    (the app's SECRET_KEY) means a stolen database alone can't be used to check guesses."""
    return hmac.new(key.encode(), normalise_recovery(code).encode(), hashlib.sha256).hexdigest()


def qr_svg(uri: str) -> str | None:
    """The QR code as inline SVG, or None if the optional `segno` package is missing."""
    try:
        import segno
    except ImportError:
        return None
    return segno.make(uri, error="m").svg_inline(
        scale=5, border=2, dark="#0a1226", light="#ffffff", omitsize=True,
        title="QR code for your authenticator app", desc="")
