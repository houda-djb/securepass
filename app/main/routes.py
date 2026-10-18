from flask import render_template
from sqlalchemy import select

from app.extensions import db
from app.main import bp
from app.models import Airport


@bp.route("/")
def index():
    airports = db.session.scalars(select(Airport).order_by(Airport.city)).all()
    featured = db.session.scalars(
        select(Airport).where(Airport.featured_rank.is_not(None)).order_by(Airport.featured_rank)
    ).all()
    return render_template("index.html", featured=featured, airports=airports, values={}, errors={})


@bp.route("/login")
def login():
    return render_template("coming_soon.html", title="Log in", phase="Phase 3")


@bp.route("/register")
def register():
    return render_template("coming_soon.html", title="Create an account", phase="Phase 3")