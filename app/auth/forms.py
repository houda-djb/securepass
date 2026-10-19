from flask_wtf import FlaskForm
from wtforms import PasswordField, StringField
from wtforms.validators import DataRequired, Email, EqualTo, Length, ValidationError

from app.auth.passwords import MAX_LENGTH, password_problems


def _clean_email(value):
    return value.strip().lower() if value else value


def strong_password(form, field):
    problems = password_problems(field.data or "", form.email.data or "")
    if problems:
        raise ValidationError(problems[0])


class RegisterForm(FlaskForm):
    email = StringField("Email", filters=[_clean_email],
                        validators=[DataRequired(), Length(max=254), Email()])
    password = PasswordField("Password",
                             validators=[DataRequired(), Length(max=MAX_LENGTH), strong_password])
    confirm = PasswordField("Confirm password", validators=[
        DataRequired(), EqualTo("password", message="The two passwords don't match.")])


class LoginForm(FlaskForm):
    # No format check on login: we never reveal whether an address is registered.
    email = StringField("Email", filters=[_clean_email],
                        validators=[DataRequired(), Length(max=254)])
    password = PasswordField("Password", validators=[DataRequired(), Length(max=MAX_LENGTH)])