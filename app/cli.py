import os
import click
from email_validator import EmailNotValidError, validate_email
from flask.cli import with_appcontext
from sqlalchemy import select

from app.admin.scans import run_scans, save_summary
from app.auth.passwords import password_problems
from app.extensions import db
from app.models import Airport, User
from app.seed import seed_demo_data


@click.command("seed")
@with_appcontext
@click.option("--days", default=90, show_default=True, help="How many days of flights to create.")
def seed_command(days: int) -> None:
    """Add any missing demo airports and flights. Existing data is kept, so it is safe to repeat."""
    count = seed_demo_data(days=days)
    click.echo(f"Created {count} new flights for the next {days} days." if count
               else "Nothing to add: the flights are already there.")


@click.command("reset-db")
@with_appcontext
@click.confirmation_option(prompt="This deletes ALL data, including user accounts. Continue?")
@click.option("--days", default=90, show_default=True)
def reset_db_command(days: int) -> None:
    """Delete everything and rebuild the database with fresh demo data."""
    db.drop_all()
    db.create_all()
    count = seed_demo_data(days=days)
    click.echo(f"Database reset. Created {count} flights for the next {days} days.")


@click.command("create-admin")
@with_appcontext
@click.option("--email", prompt=True, help="Email address for the admin account.")
@click.password_option(help="Password (typed twice, not shown on screen).")
def create_admin_command(email: str, password: str) -> None:
    """Create an admin account. There is no built-in default admin."""
    try:
        email = validate_email(email.strip(), check_deliverability=False).normalized.lower()
    except EmailNotValidError as error:
        raise click.ClickException(f"Invalid email: {error}")

    problems = password_problems(password, email)
    if problems:
        raise click.ClickException(" ".join(problems))
    if db.session.scalar(select(User).where(User.email == email)) is not None:
        raise click.ClickException("An account with that email already exists.")

    admin = User(email=email, role="admin")
    admin.set_password(password)
    db.session.add(admin)
    db.session.commit()
    click.echo(f"Admin account created for {email}.")


@click.command("bootstrap-admin")
@with_appcontext
def bootstrap_admin_command() -> None:
    """Create the first admin from ADMIN_EMAIL and ADMIN_PASSWORD, only if there is no admin yet.

    For hosting plans without a shell (Render's free plan). It never changes an existing
    admin, never prints the password, and never stops the app from starting: any problem is
    only reported. Remove ADMIN_PASSWORD from the environment after the first start.
    """
    email = os.environ.get("ADMIN_EMAIL", "").strip()
    password = os.environ.get("ADMIN_PASSWORD", "")
    if not email or not password:
        click.echo("bootstrap-admin: ADMIN_EMAIL and ADMIN_PASSWORD are not both set, nothing to do.")
        return
    if db.session.scalar(select(User).where(User.role == "admin").limit(1)) is not None:
        click.echo("bootstrap-admin: an admin account already exists, nothing to do.")
        return
    try:
        email = validate_email(email, check_deliverability=False).normalized.lower()
    except EmailNotValidError as error:
        click.echo(f"bootstrap-admin: ADMIN_EMAIL is not a valid address ({error}).")
        return
    problems = password_problems(password, email)
    if problems:
        click.echo("bootstrap-admin: ADMIN_PASSWORD was refused. " + " ".join(problems))
        return
    if db.session.scalar(select(User).where(User.email == email)) is not None:
        click.echo("bootstrap-admin: that email already belongs to a normal account, nothing changed.")
        return
    admin = User(email=email, role="admin")
    admin.set_password(password)
    db.session.add(admin)
    db.session.commit()
    click.echo(f"bootstrap-admin: admin account created for {email}. Now remove ADMIN_PASSWORD from the environment.")


@click.command("security-scan")
@with_appcontext
def security_scan_command() -> None:
    """Run Bandit and pip-audit and save a summary for the admin dashboard."""
    click.echo("Running Bandit and pip-audit (this can take a minute)...")
    summary = run_scans()
    save_summary(summary)
    bandit, audit = summary["bandit"], summary["pip_audit"]
    click.echo("Bandit:    " + (bandit["error"] or
               f"{bandit['high']} high, {bandit['medium']} medium, {bandit['low']} low"))
    click.echo("pip-audit: " + (audit["error"] or
               f"{audit['vulnerable_packages']} vulnerable of {audit['packages_checked']} packages"))
    click.echo("Summary saved. Open the admin dashboard to see it.")