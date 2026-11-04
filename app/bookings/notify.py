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
    to = booking.user.email
    body = confirmation_text(booking)
    if current_app.testing:
        current_app.extensions.setdefault("outbox", []).append(
            {"to": to, "body": body, "subject": f"Booking {booking.reference}"})
        return
    host = os.environ.get("SMTP_HOST")
    if not host:
        log.info("SMTP_HOST is not set: no confirmation email sent for %s.", booking.reference)
        return
    message = EmailMessage()
    message["Subject"] = f"Your SecurePass booking {booking.reference}"
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
