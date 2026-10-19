from flask_wtf import FlaskForm
from wtforms import IntegerField
from wtforms.validators import InputRequired, NumberRange
from wtforms.widgets import HiddenInput

from app.bookings.service import MAX_PASSENGERS


class BookingForm(FlaskForm):
    """Carries the CSRF token and the passenger count. The price is NOT part of the form:
    the server always works it out itself from the flight."""

    passengers = IntegerField("Passengers", widget=HiddenInput(),
                              validators=[InputRequired(), NumberRange(1, MAX_PASSENGERS)])