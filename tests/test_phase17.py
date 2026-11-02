"""Phase 17: PostgreSQL support, the health check and the deployment files."""
from pathlib import Path

import pytest
from sqlalchemy.exc import OperationalError

import config
from app import create_app
from app.extensions import db

ROOT = Path(__file__).resolve().parent.parent


def read(name):
    return (ROOT / name).read_text(encoding="utf-8")


# ---------------- The database address ----------------

@pytest.mark.parametrize("given, expected", [
    ("postgres://u:p@host/db", "postgresql+psycopg://u:p@host/db"),
    ("postgresql://u:p@host:5432/db", "postgresql+psycopg://u:p@host:5432/db"),
    ("postgresql+psycopg://u:p@host/db", "postgresql+psycopg://u:p@host/db"),
    ("sqlite:///other.db", "sqlite:///other.db"),
])
def test_database_url_is_made_ready_for_sqlalchemy(monkeypatch, given, expected):
    monkeypatch.setenv("DATABASE_URL", given)
    assert config.database_url() == expected


@pytest.mark.parametrize("value", [None, "", "   "])
def test_database_url_defaults_to_a_local_sqlite_file(monkeypatch, value):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    if value is not None:
        monkeypatch.setenv("DATABASE_URL", value)
    assert config.database_url() == "sqlite:///securepass.db"


# ---------------- Health check ----------------

def test_health_check_says_ok(client):
    res = client.get("/healthz")
    assert res.status_code == 200
    assert res.get_json() == {"status": "ok"}
    assert res.headers["Cache-Control"] == "no-store"
    assert "Set-Cookie" not in res.headers


def test_health_check_says_unavailable_without_details(app, client, monkeypatch):
    def broken(*args, **kwargs):
        raise OperationalError("SELECT 1", {}, Exception("password=secret host=db.internal"))
    monkeypatch.setattr(db.session, "execute", broken)
    res = client.get("/healthz")
    assert res.status_code == 503
    assert res.get_json() == {"status": "unavailable"}
    assert b"secret" not in res.data and b"db.internal" not in res.data


def test_health_check_works_over_plain_http_in_production():
    app = create_app("production", {"SECRET_KEY": "x" * 40, "SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:"})
    client = app.test_client()
    plain = "http://localhost"
    assert client.get("/healthz", base_url=plain).status_code == 200     # no redirect to https
    assert client.get("/login", base_url=plain).status_code in (301, 302)  # other pages still redirect


# ---------------- Deployment files ----------------

def test_dockerfile_does_not_run_as_root():
    lines = [line.strip() for line in read("Dockerfile").splitlines()]
    users = [line for line in lines if line.startswith("USER ")]
    assert users and users[-1] not in ("USER root", "USER 0")


def test_docker_ignore_keeps_secrets_and_junk_out_of_the_image():
    ignored = read(".dockerignore").split()
    for name in (".env", ".git", ".venv", "instance", "*.db"):
        assert name in ignored


def test_the_database_port_is_not_published_by_compose():
    compose = read("docker-compose.yml")
    db_part = compose.split("web:")[0]
    assert "ports:" not in db_part


def test_compose_requires_secrets_instead_of_hard_coding_them():
    compose = read("docker-compose.yml")
    assert "${SECRET_KEY:?" in compose and "${POSTGRES_PASSWORD:?" in compose


def test_env_example_holds_no_real_secret():
    for line in read(".env.example").splitlines():
        if "=" in line and not line.startswith("#"):
            name, value = line.split("=", 1)
            if "KEY" in name or "PASSWORD" in name:
                assert value.startswith("change-me") or value == ""


def test_the_real_env_file_is_never_committed():
    assert ".env" in read(".gitignore").split()


def test_render_blueprint_generates_the_secret_key_and_keeps_the_database_private():
    blueprint = read("render.yaml")
    assert "generateValue: true" in blueprint
    assert "ipAllowList: []" in blueprint
    assert "healthCheckPath: /healthz" in blueprint
    assert "FLASK_ENV" in blueprint and "production" in blueprint


def test_entrypoint_applies_migrations_before_starting_the_server():
    script = read("docker-entrypoint.sh")
    assert script.index("db upgrade") < script.index("gunicorn")
    assert "set -e" in script
