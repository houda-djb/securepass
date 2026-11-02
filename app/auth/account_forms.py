from flask_wtf import FlaskForm
from wtforms import PasswordField, StringField
from wtforms.validators import DataRequired, Length


class ChangePasswordForm(FlaskForm):
    """The three password boxes on the account page. The rules themselves live in
    app.auth.passwords, so registration and this form can never disagree."""

    current_password = PasswordField("Current password", validators=[DataRequired(), Length(max=128)])
    new_password = PasswordField("New password", validators=[DataRequired(), Length(max=128)])
    confirm = PasswordField("Confirm new password", validators=[DataRequired(), Length(max=128)])


class ForgotPasswordForm(FlaskForm):
    email = StringField("Email", filters=[lambda v: (v or "").strip().lower()],
                        validators=[DataRequired(), Length(max=254)])


class ResetPasswordForm(FlaskForm):
    password = PasswordField("New password", validators=[DataRequired(), Length(max=128)])
    confirm = PasswordField("Confirm new password", validators=[DataRequired(), Length(max=128)])
