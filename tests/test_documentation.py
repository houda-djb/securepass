"""The documents for the project report must stay true.

If a test is renamed or removed, or a requirement is left out, these tests fail, so the
documentation can never quietly drift away from the code.
"""
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DOCS = ROOT / "docs"


def doc(name: str) -> str:
    return (DOCS / name).read_text(encoding="utf-8")


def real_test_names() -> set:
    names = set()
    for file in (ROOT / "tests").glob("*.py"):
        names.add(file.stem)
        names.update(re.findall(r"^def (test_\w+)", file.read_text(encoding="utf-8"), re.M))
    return names


def test_every_test_named_in_the_docs_exists():
    existing = real_test_names()
    for file in DOCS.glob("*.md"):
        for name in set(re.findall(r"\btest_\w+", file.read_text(encoding="utf-8"))):
            assert name in existing, f"{file.name} mentions {name}, which does not exist"


def test_traceability_covers_every_requirement():
    text = doc("TRACEABILITY.md")
    wanted = ([f"FR{n}" for n in range(1, 22)] + [f"SR{n}" for n in range(1, 14)]
              + [f"NFR{n}" for n in range(1, 8)] + [f"TR{n}" for n in range(1, 9)]
              + [f"AC{n}" for n in range(1, 9)])
    for requirement in wanted:
        assert re.search(rf"^\| {requirement} \|", text, re.M), f"{requirement} is missing"


def test_every_traceability_row_has_evidence():
    for line in doc("TRACEABILITY.md").splitlines():
        if re.match(r"^\| (FR|SR|NFR|TR|AC)\d+ \|", line):
            evidence = line.strip().strip("|").split("|")[-1]
            assert "test_" in evidence or "Manual" in evidence, f"no evidence: {line[:60]}"


def test_owasp_checklist_covers_all_ten_categories():
    text = doc("OWASP_TOP10.md")
    for number in range(1, 11):
        assert re.search(rf"^## A{number:02d} ", text, re.M), f"A{number:02d} is missing"


def test_architecture_document_has_its_diagrams():
    text = doc("ARCHITECTURE.md")
    assert text.count("```mermaid") >= 4
    for kind in ("flowchart", "erDiagram", "sequenceDiagram"):
        assert kind in text


def test_demo_script_exists_and_names_the_acceptance_criteria():
    text = doc("DEMO_SCRIPT.md")
    for criterion in ("AC1", "AC2", "AC4", "AC6", "AC7"):
        assert criterion in text