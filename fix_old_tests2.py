"""One-off: update old tests that checked the old home page and the old 10-airport seed."""
import ast
import re
from pathlib import Path

NEW_TESTS = {
    "tests/test_phase1.py": {
        "test_home_page_loads": '''def test_home_page_loads(client):
    res = client.get("/")
    assert res.status_code == 200
    assert "Where to next from Alger?" in res.get_data(as_text=True)
''',
        "test_navbar_and_auth_links_present": '''def test_navbar_and_auth_links_present(client):
    text = client.get("/").get_data(as_text=True)
    for label in ("Explore Flights", "Countries", "Plan by month", "Log in", "Register"):
        assert label in text
''',
    },
    "tests/test_phase2.py": {
        "test_homepage_featured_cards_come_from_database": '''def test_homepage_featured_cards_come_from_database(client):
    text = client.get("/").get_data(as_text=True)
    assert "Top trips from" in text
    assert "Istanbul" in text and "Paris" in text
''',
    },
}


def replace_function(text, name, new_source):
    tree = ast.parse(text)
    for node in tree.body:
        if isinstance(node, ast.FunctionDef) and node.name == name:
            start = (node.decorator_list[0].lineno if node.decorator_list else node.lineno) - 1
            lines = text.splitlines(keepends=True)
            return "".join(lines[:start]) + new_source + "".join(lines[node.end_lineno:]), True
    return text, False


for filename, tests in NEW_TESTS.items():
    path = Path(filename)
    text = path.read_text(encoding="utf-8")
    for name, source in tests.items():
        text, found = replace_function(text, name, source)
        print(f"{filename}::{name}: {'replaced' if found else 'NOT FOUND'}")
    path.write_text(text, encoding="utf-8", newline="")

path = Path("tests/test_phase3.py")
text = path.read_text(encoding="utf-8")
fixed, n = re.subn(r"Airport\.query\.count\(\)\s*==\s*10\b", "Airport.query.count() >= 10", text)
path.write_text(fixed, encoding="utf-8", newline="")
print(f"tests/test_phase3.py: {n} airport count checks relaxed")
