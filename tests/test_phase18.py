"""Phase 18: the first admin can be created from the environment (hosting without a shell)."""
from app.cli import bootstrap_admin_command
from app.models import User

GOOD = "Correct-horse-42"


def run(app, **env):
    base = {"ADMIN_EMAIL": "", "ADMIN_PASSWORD": ""}
    return app.test_cli_runner().invoke(bootstrap_admin_command, env={**base, **env})


def test_bootstrap_creates_the_first_admin(app):
    result = run(app, ADMIN_EMAIL="Boss@Example.com", ADMIN_PASSWORD=GOOD)
    assert result.exit_code == 0 and "created" in result.output
    with app.app_context():
        admin = User.query.filter_by(email="boss@example.com").one()
        assert admin.role == "admin" and admin.check_password(GOOD)


def test_bootstrap_never_prints_the_password(app):
    result = run(app, ADMIN_EMAIL="boss@example.com", ADMIN_PASSWORD=GOOD)
    assert GOOD not in result.output


def test_bootstrap_does_nothing_without_both_values(app):
    assert "nothing to do" in run(app, ADMIN_EMAIL="boss@example.com").output
    assert "nothing to do" in run(app, ADMIN_PASSWORD=GOOD).output
    with app.app_context():
        assert User.query.count() == 0


def test_bootstrap_does_nothing_when_an_admin_already_exists(app):
    run(app, ADMIN_EMAIL="boss@example.com", ADMIN_PASSWORD=GOOD)
    result = run(app, ADMIN_EMAIL="other@example.com", ADMIN_PASSWORD=GOOD)
    assert "already exists" in result.output
    with app.app_context():
        assert User.query.filter_by(role="admin").count() == 1


def test_bootstrap_refuses_a_weak_password_without_stopping_the_app(app):
    result = run(app, ADMIN_EMAIL="boss@example.com", ADMIN_PASSWORD="password123")
    assert result.exit_code == 0 and "refused" in result.output
    with app.app_context():
        assert User.query.count() == 0


def test_bootstrap_refuses_a_bad_email_without_stopping_the_app(app):
    result = run(app, ADMIN_EMAIL="not-an-email", ADMIN_PASSWORD=GOOD)
    assert result.exit_code == 0 and "not a valid address" in result.output


def test_bootstrap_does_not_turn_a_normal_account_into_an_admin(app):
    with app.app_context():
        user = User(email="boss@example.com", role="user")
        user.set_password(GOOD)
        from app.extensions import db
        db.session.add(user)
        db.session.commit()
    result = run(app, ADMIN_EMAIL="boss@example.com", ADMIN_PASSWORD=GOOD)
    assert "normal account" in result.output
    with app.app_context():
        assert User.query.one().role == "user"
