from flask_wtf import FlaskForm
from wtforms import PasswordField
from wtforms.validators import DataRequired, Length


class ChangePasswordForm(FlaskForm):
    """The three password boxes on the account page. The rules themselves live in
    app.auth.passwords, so registration and this form can never disagree."""

    current_password = PasswordField("Current password", validators=[DataRequired(), Length(max=128)])
    new_password = PasswordField("New password", validators=[DataRequired(), Length(max=128)])
    confirm = PasswordField("Confirm new password", validators=[DataRequired(), Length(max=128)])
