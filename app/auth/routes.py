from datetime import datetime, timedelta

from flask import current_app, flash, redirect, render_template, request, session, url_for
from flask_login import current_user, login_required, login_user, logout_user
from sqlalchemy import select
from sqlalchemy.orm import joinedload
from sqlalchemy.exc import IntegrityError
from werkzeug.security import check_password_hash, generate_password_hash

from app.auth import bp
from app.auth.account_forms import ChangePasswordForm
from app.auth.forms import LoginForm, RegisterForm
from app.auth.passwords import password_problems
from app.extensions import db, limiter
from app.models import AuditLog, Booking, User, utcnow
from app.security import audit, is_safe_next

# Used when the email is unknown, so "unknown email" takes as long as "wrong password"
# and an attacker can't tell the two apart by timing.
_DUMMY_HASH = generate_password_hash("not-a-real-password")

LOGIN_ERROR = ("Invalid email or password. After 5 failed attempts "
               "an account is locked for 15 minutes.")


@bp.route("/register", methods=["GET", "POST"])
@limiter.limit("20 per hour", methods=["POST"])
def register():
    if current_user.is_authenticated:
        return redirect(url_for("main.index"))

    form = RegisterForm()
    status = 200
    if form.is_submitted():
        status = 400
        if form.validate():
            email = form.email.data
            user = User(email=email, role="user")
            user.set_password(form.password.data)
            db.session.add(user)
            try:
                db.session.commit()
            except IntegrityError:  # unique email: also covers two sign-ups at the same moment
                db.session.rollback()
                form.email.errors = [*form.email.errors, "An account with this email already exists."]
            else:
                audit("register", user)
                flash("Account created. You can log in now.", "success")
                return redirect(url_for("auth.login"))
    return render_template("auth/register.html", form=form), status


@bp.route("/login", methods=["GET", "POST"])
@limiter.limit("10 per minute", methods=["POST"])
def login():
    if current_user.is_authenticated:
        return redirect(url_for("main.index"))

    form = LoginForm()
    next_url = request.args.get("next")
    next_url = next_url if is_safe_next(next_url) else None
    error = None
    status = 200

    if form.is_submitted():
        status = 400
        if form.validate():
            status = 401
            error = LOGIN_ERROR
            if _attempt_login(form.email.data, form.password.data):
                return redirect(next_url or url_for("main.index"))
    return render_template("auth/login.html", form=form, error=error, next_url=next_url), status


def _attempt_login(email: str, password: str) -> bool:
    """Check the credentials, apply the lockout policy, and log the outcome."""
    now = utcnow()
    max_failures = current_app.config["MAX_FAILED_LOGINS"]
    lock_for = timedelta(minutes=current_app.config["LOCKOUT_MINUTES"])

    user = db.session.scalar(select(User).where(User.email == email))
    if user is None:
        check_password_hash(_DUMMY_HASH, password)
        audit("login_failed", detail=f"unknown email: {email}")
        return False

    if user.locked_until is not None and user.locked_until <= now:  # lock has run out
        user.failed_logins = 0
        user.locked_until = None

    if user.is_locked(now):
        audit("login_blocked", user, "account is locked")
        return False

    if not user.check_password(password):
        user.failed_logins += 1
        if user.failed_logins >= max_failures:
            user.locked_until = now + lock_for
            audit("account_locked", user, f"{user.failed_logins} failed attempts")
        else:
            audit("login_failed", user, f"failed attempt {user.failed_logins}")
        return False

    user.failed_logins = 0
    user.locked_until = None
    session.clear()  # start a fresh session on login (prevents session fixation)
    login_user(user)
    session.permanent = True
    audit("login_success", user)
    return True


@bp.route("/logout", methods=["POST"])  # POST + CSRF token: a link on another site can't log you out
@login_required
def logout():
    audit("logout", current_user)
    logout_user()
    session.clear()
    flash("You have been logged out.", "info")
    return redirect(url_for("main.index"))

# ---------------------------------------------------------------- account page

# Plain-English names for the events a person may see in their own history.
EVENT_LABELS = {
    "login_success": "Logged in",
    "login_failed": "Failed login attempt",
    "login_blocked": "Login blocked (account locked)",
    "account_locked": "Account locked after failed attempts",
    "logout": "Logged out",
    "register": "Account created",
    "password_changed": "Password changed",
    "password_change_failed": "Password change refused",
    "booking_created": "Booking made",
    "booking_cancelled": "Booking cancelled",
}
HISTORY_LENGTH = 8


def _account_context():
    now = datetime.now()  # flight times are plain local times in this demo
    bookings = db.session.scalars(
        select(Booking).join(Booking.flight).options(joinedload(Booking.flight))
        .where(Booking.user_id == current_user.id)
    ).all()
    confirmed = [b for b in bookings if b.status == "confirmed"]
    history = db.session.scalars(
        select(AuditLog).where(AuditLog.user_id == current_user.id)
        .order_by(AuditLog.created_at.desc(), AuditLog.id.desc()).limit(HISTORY_LENGTH)
    ).all()
    return {
        "stats": {"total": len(bookings), "upcoming": sum(1 for b in confirmed if b.flight.departs_at > now),
                  "cancelled": len(bookings) - len(confirmed)},
        "history": [(EVENT_LABELS.get(e.event_type, e.event_type.replace("_", " ").capitalize()), e)
                    for e in history],
    }


@bp.route("/account")
@login_required
def account():
    return render_template("auth/account.html", form=ChangePasswordForm(), errors={}, **_account_context())


@bp.route("/account/password", methods=["POST"])
@login_required
@limiter.limit("10 per hour", methods=["POST"])
def change_password():
    form = ChangePasswordForm()
    errors: dict[str, str] = {}
    if not form.validate():
        for field, messages in form.errors.items():
            if field in ("current_password", "new_password", "confirm"):
                errors[field] = "This field is required." if field != "confirm" else "Repeat the new password."
        if not errors:  # e.g. a missing or expired CSRF token
            errors["current_password"] = "Please try again."
    else:
        user = current_user._get_current_object()
        new, current = form.new_password.data, form.current_password.data
        if not user.check_password(current):
            errors["current_password"] = "That is not your current password."
            audit("password_change_failed", user, "wrong current password")
        else:
            problems = password_problems(new, user.email)
            if problems:
                errors["new_password"] = " ".join(problems)
            elif new == current:
                errors["new_password"] = "Choose a password different from the current one."
            elif new != form.confirm.data:
                errors["confirm"] = "The two new passwords don't match."
    if errors:
        return render_template("auth/account.html", form=ChangePasswordForm(formdata=None), errors=errors,
                               **_account_context()), 400

    user = current_user._get_current_object()
    user.set_password(new)
    user.failed_logins = 0
    user.locked_until = None
    db.session.commit()
    session.clear()  # a fresh session after a credential change (same idea as at login)
    login_user(user)
    session.permanent = True
    audit("password_changed", user)
    flash("Your password has been changed.", "success")
    return redirect(url_for("auth.account"))
