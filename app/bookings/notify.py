"""The confirmation email sent after a booking. A mail problem never breaks the booking."""
import logging
import os
import smtplib
from email.message import EmailMessage

from flask import current_app, url_for

from app.bookings.payment import method_outcome
from app.currency import money

log = logging.getLogger(__name__)


def confirmation_text(booking) -> str:
    flight = booking.flight
    link = url_for("bookings.ticket", reference=booking.reference, _external=True)
    names = ", ".join(t.full_name for t in booking.travellers) or "your passengers"
    return (f"Your SecurePass booking {booking.reference} is confirmed.\n\n"
            f"{flight.origin.city} ({flight.origin.code}) to {flight.destination.city} ({flight.destination.code})\n"
            f"Flight {flight.flight_no}, {flight.departs_at.strftime('%A %d %B %Y at %H:%M')}\n"
            f"Passengers: {names}\n"
            f"Total: {money(booking.total_cents, 2)} (demo). {method_outcome(booking.payment_method)}\n\n"
            f"Your e-ticket: {link}\n\n"
            "SecurePass is a final-year demo project: no real payment was taken.\n")


def send_confirmation(booking) -> None:
    _deliver(booking.user.email, f"Your SecurePass booking {booking.reference}", confirmation_text(booking))


def _deliver(to: str, subject: str, body: str) -> None:
    if current_app.testing:
        current_app.extensions.setdefault("outbox", []).append({"to": to, "body": body, "subject": subject})
        return
    host = os.environ.get("SMTP_HOST")
    if not host:
        log.info("SMTP_HOST is not set: no email sent (%s).", subject)
        return
    message = EmailMessage()
    message["Subject"] = subject
    message["From"] = os.environ.get("MAIL_FROM", "no-reply@securepass.local")
    message["To"] = to
    message.set_content(body)
    try:
        with smtplib.SMTP(host, int(os.environ.get("SMTP_PORT", "587")), timeout=10) as smtp:
            smtp.starttls()
            if os.environ.get("SMTP_USER"):
                smtp.login(os.environ["SMTP_USER"], os.environ.get("SMTP_PASSWORD", ""))
            smtp.send_message(message)
    except (OSError, smtplib.SMTPException):
        log.exception("Could not send the confirmation email.")


def send_cancellation_notice(booking, ip: str) -> None:
    """Tell the owner at once, so a cancellation they did not make is noticed within minutes."""
    from app.bookings.cancellation import reason_label
    body = (f"Your SecurePass booking {booking.reference} "
            f"({booking.flight.origin.city} to {booking.flight.destination.city}, "
            f"{booking.flight.departs_at.strftime('%d %B %Y')}) was cancelled.\n\n"
            f"Reason given: {reason_label(booking.cancel_reason)}\n"
            f"Network address: {ip}\n\n"
            "If this was you, nothing else is needed. If it was not you, change your password now "
            f"({url_for('auth.forgot_password', _external=True)}) and turn on two-factor login.\n")
    _deliver(booking.user.email, f"Booking {booking.reference} was cancelled", body)
