"""Passwords that are far too easy to guess."""
COMMON = {
    "password123", "password1234", "passw0rd123", "qwerty12345", "qwertyuiop1", "1qaz2wsx3edc",
    "abcdefg123", "abcd123456", "letmein1234", "welcome1234", "iloveyou123", "admin12345",
    "azerty12345", "azertyuiop1", "securepass1", "securepass123", "football123", "123456789a",
}


def is_too_common(password: str) -> bool:
    """True for well-known passwords, and for ones that repeat only a few different characters."""
    return password.lower() in COMMON or len(set(password.lower())) < 5
