"""Guards for the delivery pipeline (Phase 6).

These tests read the pipeline files as text, so nobody can weaken a security gate by accident
without a test failing, and a pull request that does it is visibly red.
"""
import re
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
WORKFLOWS = ROOT / ".github" / "workflows"


def read(path) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def workflow_texts() -> dict:
    return {p.name: p.read_text(encoding="utf-8") for p in WORKFLOWS.glob("*.yml")}


# ---------------- The CI workflow ----------------

def test_ci_runs_every_gate():
    ci = read(".github/workflows/ci.yml")
    assert "pytest" in ci and "--cov-fail-under=90" in ci   # tests + coverage gate
    assert "bandit -r app config.py -ll" in ci               # static analysis gate
    assert "pip-audit -r requirements.txt" in ci             # dependency vulnerability gate


def test_ci_runs_on_pull_requests_and_main():
    ci = read(".github/workflows/ci.yml")
    assert "pull_request:" in ci and "branches: [main]" in ci


def test_ci_uses_least_privilege_and_has_a_timeout():
    ci = read(".github/workflows/ci.yml")
    assert re.search(r"^permissions:\s*\n\s+contents: read", ci, re.M)
    assert "timeout-minutes:" in ci
    assert "persist-credentials: false" in ci


def test_ci_keeps_reports_even_when_a_gate_fails():
    ci = read(".github/workflows/ci.yml")
    assert "upload-artifact" in ci and "if: always()" in ci


# ---------------- Safe workflow habits ----------------

def test_no_workflow_uses_dangerous_settings():
    for name, text in workflow_texts().items():
        assert "pull_request_target" not in text, name      # runs untrusted code with secrets
        assert "write-all" not in text, name
        assert "secrets." not in text, f"{name} uses a secret; review it before allowing this"


def test_every_action_is_pinned_to_a_version():
    for name, text in workflow_texts().items():
        for action in re.findall(r"uses:\s*(\S+)", text):
            assert "@" in action, f"{name}: {action} has no version"
            assert not action.endswith(("@main", "@master")), f"{name}: {action} follows a moving branch"


def test_dependabot_watches_python_and_actions():
    dependabot = read(".github/dependabot.yml")
    assert 'package-ecosystem: "pip"' in dependabot
    assert 'package-ecosystem: "github-actions"' in dependabot


# ---------------- Repository hygiene ----------------

def test_secrets_and_databases_are_never_committed():
    ignore = read(".gitignore").splitlines()
    for pattern in (".env", "*.db", "instance/", ".venv/"):
        assert pattern in ignore, f"{pattern} must be in .gitignore"


def test_example_env_holds_no_real_secret():
    example = read(".env.example")
    assert "SECRET_KEY=change-me" in example


def test_every_dependency_has_a_version_rule():
    for filename in ("requirements.txt", "requirements-dev.txt"):
        for line in read(filename).splitlines():
            line = line.strip()
            if line and not line.startswith(("#", "-r")):
                assert re.search(r"[<>=!~]=?", line), f"{filename}: '{line}' has no version rule"


def test_source_code_has_no_obvious_hard_coded_secrets():
    patterns = [r"-----BEGIN [A-Z ]*PRIVATE KEY-----", r"AKIA[0-9A-Z]{16}", r"ghp_[A-Za-z0-9]{36}",
                r"sk_live_[A-Za-z0-9]{10,}"]
    files = list((ROOT / "app").rglob("*.py")) + [ROOT / "config.py", ROOT / "wsgi.py"]
    for file in files:
        text = file.read_text(encoding="utf-8")
        for pattern in patterns:
            assert not re.search(pattern, text), f"{file.name} looks like it contains a secret"


def test_security_policy_exists():
    policy = read("SECURITY.md")
    assert "Reporting a vulnerability" in policy


# ---------------- AC6: an insecure commit fails the scan ----------------

def run_bandit(path: Path) -> int:
    return subprocess.run([sys.executable, "-m", "bandit", "-ll", "-q", str(path)],
                          capture_output=True, text=True, check=False).returncode


def test_bandit_gate_rejects_insecure_code_and_accepts_safe_code(tmp_path):
    pytest.importorskip("bandit")
    insecure = tmp_path / "insecure.py"
    insecure.write_text("import subprocess\n\n\ndef run(folder):\n"
                        "    return subprocess.call('ls ' + folder, shell=True)\n")
    safe = tmp_path / "safe.py"
    safe.write_text("def add(a, b):\n    return a + b\n")
    assert run_bandit(insecure) != 0   # the pipeline would turn red
    assert run_bandit(safe) == 0       # clean code passes