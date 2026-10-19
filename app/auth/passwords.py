MIN_LENGTH = 10
MAX_LENGTH = 128  # also stops people sending huge strings to the (slow) hash function


def password_problems(password: str, email: str = "") -> list[str]:
    """Return a list of reasons the password is not acceptable (empty list = fine)."""
    problems = []
    if len(password) < MIN_LENGTH:
        problems.append(f"Use at least {MIN_LENGTH} characters.")
    if not any(c.isalpha() for c in password) or not any(c.isdigit() for c in password):
        problems.append("Include at least one letter and one number.")
    if email and password.lower() == email.strip().lower():
        problems.append("The password can't be the same as your email.")
    return problems