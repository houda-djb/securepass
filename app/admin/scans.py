"""FR21: run Bandit and pip-audit on demand and keep a short summary for the dashboard.

`flask --app wsgi security-scan` writes instance/scan_summary.json. The dashboard only ever
READS that file. The web app never starts a scan itself.
"""
import json
# subprocess is used only by the command-line scan, always with a fixed argument list.
import subprocess  # nosec B404
import sys
from datetime import datetime, timezone
from pathlib import Path

from flask import current_app

SUMMARY_FILE = "scan_summary.json"


def _run(args: list[str]) -> subprocess.CompletedProcess:
    root = Path(current_app.root_path).parent
    # Fixed argument list, no shell, no user input: nothing here can be injected into.
    return subprocess.run(  # nosec B603
        args, cwd=root, capture_output=True, text=True, timeout=300, check=False)


def run_bandit() -> dict:
    try:
        proc = _run([sys.executable, "-m", "bandit", "-r", "app", "config.py", "-f", "json", "-q"])
    except (OSError, subprocess.TimeoutExpired) as error:
        return {"error": f"Bandit could not run ({type(error).__name__})."}
    if "No module named" in proc.stderr:
        return {"error": "Bandit is not installed. Run: pip install -r requirements-dev.txt"}
    try:
        results = json.loads(proc.stdout).get("results", [])
    except (json.JSONDecodeError, AttributeError):
        return {"error": "Bandit did not return a readable result."}
    counts = {"high": 0, "medium": 0, "low": 0}
    for item in results:
        severity = str(item.get("issue_severity", "")).lower()
        if severity in counts:
            counts[severity] += 1
    return {**counts, "error": None}


def run_pip_audit() -> dict:
    try:
        proc = _run([sys.executable, "-m", "pip_audit", "-r", "requirements.txt", "-f", "json"])
    except (OSError, subprocess.TimeoutExpired) as error:
        return {"error": f"pip-audit could not run ({type(error).__name__})."}
    if "No module named" in proc.stderr:
        return {"error": "pip-audit is not installed. Run: pip install -r requirements-dev.txt"}
    try:
        packages = json.loads(proc.stdout).get("dependencies", [])
    except (json.JSONDecodeError, AttributeError):
        return {"error": "pip-audit did not return a readable result (is the internet reachable?)."}
    vulnerable = [p for p in packages if p.get("vulns")]
    return {"packages_checked": len(packages), "vulnerable_packages": len(vulnerable), "error": None}


def run_scans() -> dict:
    return {
        "ran_at": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
        "bandit": run_bandit(),
        "pip_audit": run_pip_audit(),
    }


def _summary_path() -> Path:
    return Path(current_app.instance_path) / SUMMARY_FILE


def save_summary(summary: dict) -> None:
    path = _summary_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(summary, indent=2), encoding="utf-8")


def load_summary() -> dict | None:
    """The last saved scan summary, or None if there is none (or the file is damaged)."""
    try:
        data = json.loads(_summary_path().read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if not isinstance(data, dict) or not isinstance(data.get("bandit"), dict) \
            or not isinstance(data.get("pip_audit"), dict):
        return None
    return data