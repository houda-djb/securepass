import click
from email_validator import EmailNotValidError, validate_email
from flask.cli import with_appcontext
from sqlalchemy import select

from app.auth.passwords import password_problems
from app.extensions import db
from app.models import Airport, User
from app.seed import seed_demo_data


@click.command("seed")
@with_appcontext
@click.option("--days", default=90, show_default=True, help="How many days of flights to create.")
def seed_command(days: int) -> None:
    """Add demo airports and flights. Does nothing if they already exist."""
    if db.session.scalar(select(Airport).limit(1)) is not None:
        click.echo("Demo data is already there. Use 'flask reset-db' to start over.")
        return
    count = seed_demo_data(days=days)
    click.echo(f"Created {count} flights for the next {days} days.")


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