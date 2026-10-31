import re
from datetime import timedelta
from decimal import Decimal

from flask_wtf import FlaskForm
from wtforms import (DateTimeLocalField, DecimalField, IntegerField, SelectField,
                     StringField)
from wtforms.validators import DataRequired, InputRequired, NumberRange, Regexp, ValidationError

MAX_SEATS = 500
MAX_FLIGHT_HOURS = 30


def _clean_code(value):
    return value.strip().upper() if value else value


class FlightForm(FlaskForm):
    """SR3: every field is checked on the server before a flight is saved."""

    flight_no = StringField("Flight number", filters=[_clean_code], validators=[
        DataRequired(),
        Regexp(r"^[A-Z]{2}[0-9]{1,4}$", message="Use two letters and 1 to 4 digits, for example SP104.")],
        render_kw={"placeholder": "e.g., SP104", "maxlength": 6, "autocomplete": "off"})
    # Optional: "" means no operator is recorded. The choices are filled in by the route.
    airline = SelectField("Operated by", default="")
    origin = SelectField("From", validators=[DataRequired()])
    destination = SelectField("To", validators=[DataRequired()])
    # InputRequired (not DataRequired) so unreadable input gets a specific message,
    # such as "Not a valid datetime value", instead of "This field is required".
    departs_at = DateTimeLocalField("Departs (local time)", format="%Y-%m-%dT%H:%M",
                                    validators=[InputRequired()])
    arrives_at = DateTimeLocalField("Arrives (local time)", format="%Y-%m-%dT%H:%M",
                                    validators=[InputRequired()])
    price = DecimalField("Price per passenger (USD)", places=2, validators=[
        InputRequired(), NumberRange(Decimal("0.01"), Decimal("99999.99"))])
    seats_available = IntegerField("Seats available", validators=[
        InputRequired(), NumberRange(0, MAX_SEATS)])

    def validate_destination(self, field):
        if field.data == self.origin.data:
            raise ValidationError("Origin and destination must be different.")

    def validate_arrives_at(self, field):
        if not (self.departs_at.data and field.data):
            return
        length = field.data - self.departs_at.data
        if length <= timedelta(0):
            raise ValidationError("The flight must arrive after it departs.")
        if length > timedelta(hours=MAX_FLIGHT_HOURS):
            raise ValidationError(f"A flight can't be longer than {MAX_FLIGHT_HOURS} hours.")