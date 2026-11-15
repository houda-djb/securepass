from app.auth.breach import is_breached
from app.auth.common_passwords import is_too_common


def password_problems(password, email=""):
    problems = []
    if len(password) < 10:
        problems.append("Use at least 10 characters.")
    if not any(c.isalpha() for c in password) or not any(c.isdigit() for c in password):
        problems.append("Use at least one letter and one number.")
    if is_too_common(password):
        problems.append("That password is too easy to guess. Choose something less common.")
    if email and password.lower() == email.lower():
        problems.append("Your password can't be the same as your email.")
    elif email and email.split("@")[0].lower() in password.lower():
        problems.append("Don't use your email name in the password.")
    if not problems and is_breached(password):  # last, so a weak password never costs a network call
        problems.append("This password appears in known data breaches. Choose a different one.")
    return problems
