from flask_wtf import FlaskForm
from wtforms import PasswordField, StringField
from wtforms.validators import DataRequired, Email, EqualTo, Length, ValidationError

from app.auth.passwords import password_problems


class LoginForm(FlaskForm):
    email = StringField("Email", filters=[lambda v: (v or "").strip().lower()],
                        validators=[DataRequired(), Length(max=254)])
    password = PasswordField("Password", validators=[DataRequired(), Length(max=128)])


class RegisterForm(FlaskForm):
    email = StringField("Email", filters=[lambda v: (v or "").strip().lower()],
                        validators=[DataRequired(), Email(check_deliverability=False), Length(max=254)])
    password = PasswordField("Password", validators=[DataRequired(), Length(max=128)])
    confirm = PasswordField("Confirm", validators=[DataRequired(), EqualTo("password", "Passwords don't match.")])

    def validate_password(self, field):
        problems = password_problems(field.data, self.email.data or "")
        if problems:
            raise ValidationError(" ".join(problems))
