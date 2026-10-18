import click

from app.extensions import db
from app.seed import seed_demo_data


@click.command("seed")
@click.option("--days", default=90, show_default=True, help="How many days of flights to create.")
def seed_command(days: int) -> None:
    """Reset the database and fill it with demo airports and flights."""
    db.drop_all()
    db.create_all()
    count = seed_demo_data(days=days)
    click.echo(f"Database reset. Created {count} flights for the next {days} days.")