import time
from datetime import datetime, timedelta

from flask import current_app, flash, redirect, render_template, request, session, url_for
from flask_login import current_user, login_required, login_user, logout_user
from sqlalchemy import delete, func, select
from sqlalchemy.orm import joinedload
from sqlalchemy.exc import IntegrityError
from werkzeug.security import check_password_hash, generate_password_hash

from app.auth import bp
from app.auth import totp
from app.auth.account_forms import ChangePasswordForm, ForgotPasswordForm, ResetPasswordForm
from app.auth.reset import send_reset_email, user_for_token
from app.auth.forms import LoginForm, RegisterForm
from app.auth.passwords import password_problems
from app.extensions import db, limiter
from app.models import AuditLog, Booking, RecoveryCode, User, utcnow
from app.security import audit, is_safe_next

# Used when the email is unknown, so "unknown email" takes as long as "wrong password"
# and an attacker can't tell the two apart by timing.
_DUMMY_HASH = generate_password_hash("not-a-real-password")

NEEDS_CODE = "needs_code"      # the password was right, the authenticator code is still to come
PENDING_SECONDS = 300          # how long a half-finished login stays open
CODE_ERROR = "That code is not right. Use the 6-digit code from your app, or a recovery code."

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
            outcome = _attempt_login(form.email.data, form.password.data)
            if outcome == NEEDS_CODE:
                return redirect(url_for("auth.verify_login", next=next_url) if next_url
                                else url_for("auth.verify_login"))
            if outcome:
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

    if user.totp_enabled:
        # Right password, but this account also needs its authenticator code. Nobody is logged
        # in yet: the signed session only remembers who is half-way through, and for how long.
        session.clear()
        session["2fa_user"] = user.id
        session["2fa_at"] = time.time()
        audit("login_password_ok", user, "waiting for the authenticator code")
        return NEEDS_CODE

    _finish_login(user)
    return True


def _finish_login(user: User, detail: str = "") -> None:
    user.failed_logins = 0
    user.locked_until = None
    session.clear()  # start a fresh session on login (prevents session fixation)
    login_user(user)
    session.permanent = True
    audit("login_success", user, detail)


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
    "password_reset_requested": "Password reset link requested",
    "password_reset": "Password reset with an emailed link",
    "password_change_failed": "Password change refused",
    "booking_created": "Booking made",
    "booking_cancelled": "Booking cancelled",
    "login_password_ok": "Password accepted, waiting for the authenticator code",
    "two_factor_failed": "Wrong authenticator code",
    "two_factor_enabled": "Two-factor login turned on",
    "two_factor_disabled": "Two-factor login turned off",
    "two_factor_change_failed": "Two-factor change refused",
    "recovery_code_used": "Recovery code used to log in",
    "recovery_codes_renewed": "New recovery codes made",
    "seats_selected": "Seats chosen",
    "data_exported": "Personal data downloaded",
    "cancel_refused": "Cancellation refused (wrong password or code)",
    "cancel_burst_blocked": "Cancellation blocked: too many in a short time",
    "cancel_burst_alert": "Several bookings cancelled in a few minutes",
    "account_delete_refused": "Account deletion refused",
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
        "recovery_left": _recovery_left(current_user) if current_user.totp_enabled else 0,
        "stats": {"total": len(bookings), "upcoming": sum(1 for b in confirmed if b.flight.departs_at > now),
                  "cancelled": len(bookings) - len(confirmed)},
        "history": [(EVENT_LABELS.get(e.event_type, e.event_type.replace("_", " ").capitalize()), e)
                    for e in history],
    }


@bp.route("/account")
@login_required
def account():
    return render_template("auth/account.html", form=ChangePasswordForm(), errors={}, tf_error=None,
                           **_account_context())


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
                               tf_error=None, **_account_context()), 400

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


# ---------------------------------------------------------------- second factor at login

def _pending_user() -> User | None:
    """The person who has typed a correct password and now owes an authenticator code."""
    user_id, started = session.get("2fa_user"), session.get("2fa_at")
    if not isinstance(user_id, int) or not isinstance(started, (int, float)):
        return None
    if time.time() - started > PENDING_SECONDS:
        session.clear()
        return None
    user = db.session.get(User, user_id)
    return user if user is not None and user.totp_enabled else None


def _recovery_left(user: User) -> int:
    return db.session.scalar(select(func.count(RecoveryCode.id)).where(
        RecoveryCode.user_id == user.id, RecoveryCode.used_at.is_(None))) or 0


def _use_recovery_code(user: User, code: str) -> bool:
    cleaned = totp.normalise_recovery(code)
    if len(cleaned) != 10 or not cleaned.isalnum():
        return False
    row = db.session.scalar(select(RecoveryCode).where(
        RecoveryCode.user_id == user.id, RecoveryCode.used_at.is_(None),
        RecoveryCode.code_hash == totp.hash_recovery(cleaned, current_app.config["SECRET_KEY"])))
    if row is None:
        return False
    row.used_at = utcnow()   # each recovery code works exactly once
    return True


def _second_factor_ok(user: User, code: str) -> bool:
    """A 6-digit app code (never accepted twice) or an unused recovery code."""
    digits = (code or "").replace(" ", "")
    if digits.isascii() and digits.isdigit() and len(digits) == totp.DIGITS:
        step = totp.verify(user.totp_secret, digits, user.last_totp_step)
        if step is None:
            return False
        user.last_totp_step = step
        return True
    if _use_recovery_code(user, code):
        audit("recovery_code_used", user, f"{_recovery_left(user)} unused codes left")
        return True
    return False


@bp.route("/login/verify", methods=["GET", "POST"])
@limiter.limit("10 per minute", methods=["POST"])
def verify_login():
    if current_user.is_authenticated:
        return redirect(url_for("main.index"))
    user = _pending_user()
    if user is None:
        flash("Please log in again.", "info")
        return redirect(url_for("auth.login"))

    next_url = request.args.get("next")
    next_url = next_url if is_safe_next(next_url) else None
    error, status = None, 200

    if request.method == "POST":
        now = utcnow()
        if user.locked_until is not None and user.locked_until <= now:
            user.failed_logins, user.locked_until = 0, None
        if user.is_locked(now):
            audit("login_blocked", user, "account is locked")
            session.clear()
            flash("This account is temporarily locked. Try again later.", "error")
            return redirect(url_for("auth.login"))

        if _second_factor_ok(user, request.form.get("code", "")[:40]):
            db.session.commit()
            _finish_login(user, "two-factor")
            return redirect(next_url or url_for("main.index"))

        status, error = 401, CODE_ERROR
        user.failed_logins += 1
        if user.failed_logins >= current_app.config["MAX_FAILED_LOGINS"]:
            user.locked_until = now + timedelta(minutes=current_app.config["LOCKOUT_MINUTES"])
            audit("account_locked", user, f"{user.failed_logins} failed attempts")
            session.clear()
            flash("Too many wrong codes. This account is locked for a while.", "error")
            return redirect(url_for("auth.login"))
        audit("two_factor_failed", user, f"failed attempt {user.failed_logins}")
    return render_template("auth/verify.html", error=error, next_url=next_url), status


# ---------------------------------------------------------------- managing two-factor

def _password_and_code_problem(user: User) -> str | None:
    """Changes to two-factor need the password AND a current code, so a borrowed laptop
    that is already logged in can't switch it off."""
    if not user.check_password(request.form.get("password", "")[:128]):
        return "That is not your current password."
    if not _second_factor_ok(user, request.form.get("code", "")[:40]):
        return CODE_ERROR
    return None


def _show_codes(user: User, headline: str):
    codes = totp.new_recovery_codes()
    db.session.execute(delete(RecoveryCode).where(RecoveryCode.user_id == user.id))
    key = current_app.config["SECRET_KEY"]
    db.session.add_all(RecoveryCode(user_id=user.id, code_hash=totp.hash_recovery(c, key)) for c in codes)
    db.session.commit()
    return render_template("auth/recovery_codes.html", codes=codes, headline=headline)


@bp.route("/account/2fa", methods=["GET", "POST"])
@login_required
@limiter.limit("20 per hour", methods=["POST"])
def two_factor_setup():
    user = current_user._get_current_object()
    if user.totp_enabled:
        return redirect(url_for("auth.account"))
    secret = session.get("totp_setup")
    if not isinstance(secret, str) or len(secret) != 32:
        secret = session["totp_setup"] = totp.new_secret()

    error, status = None, 200
    if request.method == "POST":
        step = totp.verify(secret, request.form.get("code", "")[:12])
        if step is None:
            error, status = "That code is not right. Check the app and try the new code.", 400
        else:
            user.totp_secret, user.totp_enabled, user.last_totp_step = secret, True, step
            db.session.commit()
            session.pop("totp_setup", None)
            audit("two_factor_enabled", user)
            return _show_codes(user, "Two-factor login is on")
    uri = totp.otpauth_uri(secret, user.email)
    return render_template("auth/two_factor_setup.html", secret=totp.readable(secret),
                           qr=totp.qr_svg(uri), error=error), status


@bp.route("/account/2fa/disable", methods=["POST"])
@login_required
@limiter.limit("10 per hour", methods=["POST"])
def two_factor_disable():
    user = current_user._get_current_object()
    if not user.totp_enabled:
        return redirect(url_for("auth.account"))
    problem = _password_and_code_problem(user)
    if problem:
        db.session.commit()   # keeps a recovery code marked used, if one was just tried
        audit("two_factor_change_failed", user, "disable refused")
        return render_template("auth/account.html", form=ChangePasswordForm(formdata=None), errors={},
                               tf_error=problem, **_account_context()), 400
    user.totp_secret, user.totp_enabled, user.last_totp_step = None, False, None
    db.session.execute(delete(RecoveryCode).where(RecoveryCode.user_id == user.id))
    db.session.commit()
    audit("two_factor_disabled", user)
    flash("Two-factor login is now off.", "info")
    return redirect(url_for("auth.account"))


@bp.route("/account/2fa/recovery", methods=["POST"])
@login_required
@limiter.limit("10 per hour", methods=["POST"])
def two_factor_new_codes():
    user = current_user._get_current_object()
    if not user.totp_enabled:
        return redirect(url_for("auth.account"))
    problem = _password_and_code_problem(user)
    if problem:
        db.session.commit()
        audit("two_factor_change_failed", user, "new recovery codes refused")
        return render_template("auth/account.html", form=ChangePasswordForm(formdata=None), errors={},
                               tf_error=problem, **_account_context()), 400
    audit("recovery_codes_renewed", user)
    return _show_codes(user, "New recovery codes")


# ------------------------------------------------------------ forgot password

@bp.route("/forgot-password", methods=["GET", "POST"])
@limiter.limit("5 per hour", methods=["POST"])
def forgot_password():
    if current_user.is_authenticated:
        return redirect(url_for("auth.account"))
    form = ForgotPasswordForm()
    if form.validate_on_submit():
        user = db.session.scalar(select(User).where(User.email == form.email.data))
        if user is not None:
            audit("password_reset_requested", user)
            send_reset_email(user)
        # The same answer whether or not the account exists, so this page can't be used
        # to find out who has an account.
        return render_template("auth/forgot_sent.html")
    return render_template("auth/forgot_password.html", form=form), (400 if form.is_submitted() else 200)


@bp.route("/reset-password/<token>", methods=["GET", "POST"])
@limiter.limit("20 per hour", methods=["POST"])
def reset_password(token: str):
    user = user_for_token(token[:500])
    if user is None:
        flash("That reset link is not valid any more. Ask for a new one.", "error")
        return redirect(url_for("auth.forgot_password"))

    form = ResetPasswordForm()
    problem = None
    if form.validate_on_submit():
        if form.password.data != form.confirm.data:
            problem = "The two passwords do not match."
        elif user.check_password(form.password.data):
            problem = "Choose a password you have not used before on this account."
        else:
            problems = password_problems(form.password.data, user.email)
            if problems:
                problem = " ".join(problems)
        if problem is None:
            user.set_password(form.password.data)
            user.failed_logins = 0
            user.locked_until = None
            audit("password_reset", user)  # also saves the change above
            flash("Your password was changed. You can log in now.", "success")
            return redirect(url_for("auth.login"))
    status = 400 if form.is_submitted() else 200
    return render_template("auth/reset_password.html", form=form, problem=problem), status
