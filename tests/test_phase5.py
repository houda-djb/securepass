import json
import re
import subprocess
from datetime import date, datetime, time, timedelta

import pytest
from sqlalchemy.exc import IntegrityError

from app import create_app
from app.admin import queries, scans
from app.cli import security_scan_command
from app.extensions import db
from app.models import Airport, AuditLog, Booking, Flight, User, utcnow
from app.seed import seed_demo_data

PASSWORD = "Correct-horse-42"
ALICE, ADMIN = "alice@example.com", "admin@example.com"


@pytest.fixture()
def users(app):
    with app.app_context():
        for email, role in ((ALICE, "user"), (ADMIN, "admin")):
            user = User(email=email, role=role)
            user.set_password(PASSWORD)
            db.session.add(user)
        db.session.commit()


@pytest.fixture()
def admin(app, client, users):
    client.post("/login", data={"email": ADMIN, "password": PASSWORD})
    return client


def login(client, email):
    return client.post("/login", data={"email": email, "password": PASSWORD})


def log_event(event_type, minutes_ago=1, user_email=None, detail="", ip="127.0.0.1"):
    user = User.query.filter_by(email=user_email).first() if user_email else None
    db.session.add(AuditLog(event_type=event_type, user_id=user.id if user else None, ip=ip,
                            detail=detail, created_at=utcnow() - timedelta(minutes=minutes_ago)))
    db.session.commit()


def a_flight(app, offset=5):
    start = datetime.combine(date.today() + timedelta(days=offset), time.min)
    with app.app_context():
        return Flight.query.filter(Flight.origin_code == "LHR", Flight.destination_code == "CDG",
                                   Flight.departs_at >= start,
                                   Flight.departs_at < start + timedelta(days=1)).one().id


def flight_payload(**overrides):
    day = date.today() + timedelta(days=40)
    data = {"flight_no": "SP900", "origin": "LHR", "destination": "FCO",
            "departs_at": f"{day}T09:30", "arrives_at": f"{day}T12:45",
            "price": "123.45", "seats_available": "150"}
    data.update(overrides)
    return data


# ---------------- Access control (SR5) ----------------

def admin_rules(app):
    return [r for r in app.url_map.iter_rules() if r.endpoint.startswith("admin.")]


def admin_url(rule):
    values = {name: 1 for name in rule.arguments}
    return rule.rule.replace("<int:flight_id>", "1").replace("<int:user_id>", "1") \
        if values else rule.rule


def test_there_are_admin_routes_to_check(app):
    assert len(admin_rules(app)) >= 6


def test_every_admin_route_blocks_anonymous_visitors(app, client):
    for rule in admin_rules(app):
        method = "POST" if "POST" in rule.methods and "GET" not in rule.methods else "GET"
        res = client.open(admin_url(rule), method=method)
        assert res.status_code == 302 and "/login" in res.headers["Location"], rule.rule


def test_every_admin_route_blocks_normal_users(app, client, users):
    login(client, ALICE)
    for rule in admin_rules(app):
        method = "POST" if "POST" in rule.methods and "GET" not in rule.methods else "GET"
        assert client.open(admin_url(rule), method=method).status_code == 403, rule.rule
    with app.app_context():
        assert AuditLog.query.filter_by(event_type="access_denied").count() == len(admin_rules(app))


def test_admin_pages_open_for_admins(admin):
    for path in ("/admin/", "/admin/flights", "/admin/flights/new"):
        assert admin.get(path).status_code == 200


# ---------------- Dashboard numbers (FR17-FR20) ----------------

def test_failed_logins_count_only_the_last_24_hours(app, admin):
    with app.app_context():
        log_event("login_failed", minutes_ago=5)
        log_event("login_blocked", minutes_ago=60)
        log_event("account_locked", minutes_ago=600)
        log_event("login_failed", minutes_ago=60 * 25)    # too old
        log_event("login_success", minutes_ago=5)         # not a failure
        stats = queries.dashboard_stats()
    assert stats["failed_logins"] == 3


def test_locked_accounts_are_listed_and_expired_locks_are_not(app, admin):
    with app.app_context():
        alice = User.query.filter_by(email=ALICE).one()
        alice.failed_logins, alice.locked_until = 5, utcnow() + timedelta(minutes=10)
        db.session.commit()
    html = admin.get("/admin/").get_data(as_text=True)
    assert ALICE in html and "Unlock" in html
    with app.app_context():
        alice = User.query.filter_by(email=ALICE).one()
        alice.locked_until = utcnow() - timedelta(minutes=1)
        db.session.commit()
    assert "No accounts are locked" in admin.get("/admin/").get_data(as_text=True)


def test_admin_can_unlock_an_account_and_it_is_audited(app, admin):
    with app.app_context():
        alice = User.query.filter_by(email=ALICE).one()
        alice.failed_logins, alice.locked_until = 5, utcnow() + timedelta(minutes=10)
        db.session.commit()
        uid = alice.id
    assert admin.get(f"/admin/users/{uid}/unlock").status_code == 405
    assert admin.post(f"/admin/users/{uid}/unlock").status_code == 302
    with app.app_context():
        alice = db.session.get(User, uid)
        assert alice.failed_logins == 0 and alice.locked_until is None
        assert AuditLog.query.filter_by(event_type="account_unlocked").count() == 1
    assert login(app.test_client(), ALICE).status_code == 302   # she can log in again


def test_unlock_unknown_user_is_404(admin):
    assert admin.post("/admin/users/99999/unlock").status_code == 404
    assert admin.post("/admin/users/99999999999999999999/unlock").status_code == 404


def test_events_table_shows_newest_first_with_user_email(app, admin):
    with app.app_context():
        log_event("booking_created", minutes_ago=30, user_email=ALICE, detail="OLDER1")
        log_event("access_denied", minutes_ago=1, user_email=ALICE, detail="NEWER1")
    html = admin.get("/admin/").get_data(as_text=True)
    assert html.index("NEWER1") < html.index("OLDER1")
    assert ALICE in html


def test_events_can_be_filtered_by_type(app, admin):
    with app.app_context():
        log_event("access_denied", detail="DENIED_ROW")
        log_event("booking_created", detail="BOOKING_ROW")
    html = admin.get("/admin/?type=access_denied").get_data(as_text=True)
    assert "DENIED_ROW" in html and "BOOKING_ROW" not in html


def test_unknown_filter_values_are_ignored_not_executed(app, admin):
    with app.app_context():
        log_event("access_denied", detail="STILL_SHOWN")
    res = admin.get("/admin/", query_string={"type": "x' OR '1'='1"})
    assert res.status_code == 200 and "STILL_SHOWN" in res.get_data(as_text=True)


def test_event_details_are_escaped_on_the_dashboard(app, admin):
    with app.app_context():
        log_event("login_failed", detail='unknown email: <script>alert("x")</script>')
    html = admin.get("/admin/").get_data(as_text=True)
    assert "<script>alert" not in html and "&lt;script&gt;" in html


def test_bookings_per_day_fills_in_zero_days(app, users):
    with app.app_context():
        alice = User.query.filter_by(email=ALICE).one().id
        fid = Flight.query.first().id
        today = utcnow().date()
        for days_ago, ref in ((0, "AAAAAAA2"), (0, "AAAAAAA3"), (3, "AAAAAAA4"), (30, "AAAAAAA5")):
            db.session.add(Booking(reference=ref, user_id=alice, flight_id=fid, passengers=1,
                                   total_cents=100, created_at=datetime.combine(
                                       today - timedelta(days=days_ago), time(12, 0))))
        db.session.commit()
        points = queries.bookings_per_day(14, today)
    assert len(points) == 14
    counts = dict(points)
    assert counts[today] == 2 and counts[today - timedelta(days=3)] == 1
    assert sum(counts.values()) == 3                      # the 30-day-old booking is outside the window
    assert counts[today - timedelta(days=1)] == 0


def test_chart_geometry_is_sane_even_with_no_data():
    chart = queries.build_chart([(date(2026, 1, d), 0) for d in range(1, 15)])
    assert len(chart["bars"]) == 14 and all(bar["h"] == 0 for bar in chart["bars"])
    busy = queries.build_chart([(date(2026, 1, d), d) for d in range(1, 15)])
    tallest = max(busy["bars"], key=lambda b: b["h"])
    assert tallest["count"] == 14 and all(0 <= b["x"] <= busy["width"] for b in busy["bars"])


def test_dashboard_contains_the_chart(admin):
    html = admin.get("/admin/").get_data(as_text=True)
    assert "<svg" in html and "Bar chart of bookings" in html


# ---------------- Scan summary (FR21) ----------------

def test_dashboard_without_a_scan(admin):
    assert "No scan recorded yet" in admin.get("/admin/").get_data(as_text=True)


def test_dashboard_shows_a_saved_scan(app, admin, tmp_path):
    app.instance_path = str(tmp_path)
    with app.app_context():
        scans.save_summary({"ran_at": "2026-10-20 10:00 UTC",
                            "bandit": {"high": 0, "medium": 1, "low": 4, "error": None},
                            "pip_audit": {"packages_checked": 30, "vulnerable_packages": 2, "error": None}})
    html = admin.get("/admin/").get_data(as_text=True)
    assert "1 medium" in html and "2 vulnerable of 30" in html and "2026-10-20 10:00 UTC" in html


def test_a_damaged_scan_file_does_not_break_the_dashboard(app, admin, tmp_path):
    app.instance_path = str(tmp_path)
    (tmp_path / scans.SUMMARY_FILE).write_text("{not json", encoding="utf-8")
    res = admin.get("/admin/")
    assert res.status_code == 200 and "No scan recorded yet" in res.get_data(as_text=True)


def fake_run(bandit_out=None, audit_out=None, bandit_err="", audit_err=""):
    def run(args, **kwargs):
        tool = "bandit" if "bandit" in args else "pip_audit"
        out, err = (bandit_out, bandit_err) if tool == "bandit" else (audit_out, audit_err)
        return subprocess.CompletedProcess(args, 1, stdout=out or "", stderr=err)
    return run


def test_security_scan_command_counts_findings(app, monkeypatch, tmp_path):
    app.instance_path = str(tmp_path)
    bandit_json = json.dumps({"results": [{"issue_severity": "HIGH"}, {"issue_severity": "LOW"},
                                          {"issue_severity": "LOW"}]})
    audit_json = json.dumps({"dependencies": [{"name": "a", "vulns": [{"id": "X"}]},
                                              {"name": "b", "vulns": []}, {"name": "c"}]})
    monkeypatch.setattr(scans, "_run", fake_run(bandit_json, audit_json))
    result = app.test_cli_runner().invoke(security_scan_command)
    assert result.exit_code == 0
    assert "1 high, 0 medium, 2 low" in result.output and "1 vulnerable of 3" in result.output
    with app.app_context():
        saved = scans.load_summary()
    assert saved["bandit"]["high"] == 1 and saved["pip_audit"]["vulnerable_packages"] == 1


def test_security_scan_reports_missing_tools_and_bad_output(app, monkeypatch, tmp_path):
    app.instance_path = str(tmp_path)
    monkeypatch.setattr(scans, "_run", fake_run(bandit_err="No module named bandit",
                                                audit_out="<html>offline</html>"))
    result = app.test_cli_runner().invoke(security_scan_command)
    assert result.exit_code == 0
    assert "not installed" in result.output and "readable result" in result.output


# ---------------- Flight list ----------------

def test_flight_list_shows_only_upcoming_flights(app, admin):
    with app.app_context():
        past = Flight.query.first()
        past.departs_at = datetime.now() - timedelta(days=2)
        past.arrives_at = past.departs_at + timedelta(hours=2)
        past_no, past_when = past.flight_no, past.departs_at.strftime("%d %b %Y")
        db.session.commit()
    html = admin.get("/admin/flights").get_data(as_text=True)
    assert past_when not in html


def test_flight_search_by_number_and_by_airport(admin):
    by_number = admin.get("/admin/flights?q=sp104").get_data(as_text=True)
    assert "SP104" in by_number and "SP110" not in by_number
    by_airport = admin.get("/admin/flights?q=jtr").get_data(as_text=True)
    assert "JTR" in by_airport


def test_flight_search_rejects_odd_input_politely(admin):
    res = admin.get("/admin/flights", query_string={"q": "'; DROP TABLE flights; --"})
    assert res.status_code == 200 and "Search by flight number" in res.get_data(as_text=True)
    assert admin.get("/admin/flights?q=LHR").status_code == 200       # table still there


def test_flight_list_pages(admin):
    first = admin.get("/admin/flights").get_data(as_text=True)
    assert "Page 1 of" in first and "Next" in first
    assert "Page 2 of" in admin.get("/admin/flights?page=2").get_data(as_text=True)
    for bad in ("0", "-3", "abc", "99999"):
        assert admin.get(f"/admin/flights?page={bad}").status_code == 200


# ---------------- Create, edit, delete flights ----------------

def test_admin_can_add_a_flight(app, admin):
    res = admin.post("/admin/flights/new", data=flight_payload())
    assert res.status_code == 302
    with app.app_context():
        flight = Flight.query.filter_by(flight_no="SP900").one()
        assert flight.price_cents == 12345 and flight.seats_available == 150
        assert flight.origin_code == "LHR" and flight.destination_code == "FCO"
        assert AuditLog.query.filter_by(event_type="flight_created").count() == 1


def test_flight_number_is_normalised(app, admin):
    admin.post("/admin/flights/new", data=flight_payload(flight_no="  sp901 "))
    with app.app_context():
        assert Flight.query.filter_by(flight_no="SP901").count() == 1


@pytest.mark.parametrize("override, message", [
    ({"flight_no": "SPECIAL1"}, "two letters"),
    ({"flight_no": ""}, "required"),
    ({"destination": "LHR"}, "must be different"),
    ({"origin": "ZZZ"}, "valid choice"),
    ({"origin": ""}, "required"),
    ({"destination": ""}, "required"),
    ({"departs_at": "tomorrow"}, "Not a valid datetime"),
    ({"price": "0"}, "between"),
    ({"price": "-5"}, "between"),
    ({"price": "100000"}, "between"),
    ({"price": "cheap"}, "Not a valid decimal"),
    ({"seats_available": "-1"}, "between"),
    ({"seats_available": "501"}, "between"),
    ({"seats_available": ""}, "required"),
])
def test_bad_flight_data_is_rejected(app, admin, override, message):
    res = admin.post("/admin/flights/new", data=flight_payload(**override))
    assert res.status_code == 400 and message in res.get_data(as_text=True)
    with app.app_context():
        assert Flight.query.filter_by(flight_no="SP900").count() == 0


def test_flight_cannot_arrive_before_it_departs_or_last_too_long(app, admin):
    day = date.today() + timedelta(days=40)
    early = admin.post("/admin/flights/new", data=flight_payload(arrives_at=f"{day}T08:00"))
    assert early.status_code == 400 and b"must arrive after" in early.data
    long = admin.post("/admin/flights/new",
                      data=flight_payload(arrives_at=f"{day + timedelta(days=3)}T09:30"))
    assert long.status_code == 400 and b"longer than" in long.data


def test_duplicate_flight_number_and_time_is_rejected(app, admin):
    admin.post("/admin/flights/new", data=flight_payload())
    res = admin.post("/admin/flights/new", data=flight_payload())
    assert res.status_code == 400 and b"already departs at that time" in res.data
    with app.app_context():
        assert Flight.query.filter_by(flight_no="SP900").count() == 1


def test_edit_page_is_prefilled(app, admin):
    fid = a_flight(app)
    html = admin.get(f"/admin/flights/{fid}/edit").get_data(as_text=True)
    assert 'value="SP104"' in html and "Save changes" in html


def test_admin_can_change_price_and_seats(app, admin):
    fid = a_flight(app)
    payload = flight_payload()
    with app.app_context():
        f = db.session.get(Flight, fid)
        payload.update(flight_no=f.flight_no, origin=f.origin_code, destination=f.destination_code,
                       departs_at=f.departs_at.strftime("%Y-%m-%dT%H:%M"),
                       arrives_at=f.arrives_at.strftime("%Y-%m-%dT%H:%M"))
    payload.update(price="49.99", seats_available="7")
    assert admin.post(f"/admin/flights/{fid}/edit", data=payload).status_code == 302
    with app.app_context():
        f = db.session.get(Flight, fid)
        assert f.price_cents == 4999 and f.seats_available == 7
        assert AuditLog.query.filter_by(event_type="flight_updated").count() == 1


def test_route_and_times_are_locked_once_someone_has_booked(app, admin):
    fid = a_flight(app)
    with app.app_context():
        alice = User.query.filter_by(email=ALICE).one().id
        db.session.add(Booking(reference="BBBBBBB2", user_id=alice, flight_id=fid,
                               passengers=1, total_cents=100))
        db.session.commit()
        f = db.session.get(Flight, fid)
        base = dict(flight_no=f.flight_no, origin=f.origin_code, destination=f.destination_code,
                    departs_at=f.departs_at.strftime("%Y-%m-%dT%H:%M"),
                    arrives_at=f.arrives_at.strftime("%Y-%m-%dT%H:%M"))
    # Changing the destination is refused...
    moved = admin.post(f"/admin/flights/{fid}/edit",
                       data=flight_payload(**{**base, "destination": "FCO", "price": "10", "seats_available": "5"}))
    assert moved.status_code == 400 and b"confirmed booking" in moved.data
    with app.app_context():
        assert db.session.get(Flight, fid).destination_code == "CDG"
    # ...but price and seats can still change.
    ok = admin.post(f"/admin/flights/{fid}/edit",
                    data=flight_payload(**{**base, "price": "10", "seats_available": "5"}))
    assert ok.status_code == 302


def test_delete_flight_without_bookings(app, admin):
    admin.post("/admin/flights/new", data=flight_payload())
    with app.app_context():
        fid = Flight.query.filter_by(flight_no="SP900").one().id
    assert admin.get(f"/admin/flights/{fid}/delete").status_code == 405
    assert admin.post(f"/admin/flights/{fid}/delete").status_code == 302
    with app.app_context():
        assert db.session.get(Flight, fid) is None
        assert AuditLog.query.filter_by(event_type="flight_deleted").count() == 1


def test_a_flight_with_bookings_can_not_be_deleted(app, admin):
    fid = a_flight(app)
    with app.app_context():
        alice = User.query.filter_by(email=ALICE).one().id
        db.session.add(Booking(reference="CCCCCCC2", user_id=alice, flight_id=fid, passengers=1,
                               total_cents=100, status="cancelled"))   # even cancelled ones count
        db.session.commit()
    res = admin.post(f"/admin/flights/{fid}/delete", follow_redirects=True)
    assert b"has bookings" in res.data
    with app.app_context():
        assert db.session.get(Flight, fid) is not None


def test_unknown_flight_ids_are_404(admin):
    for path in ("/admin/flights/999999/edit", "/admin/flights/99999999999999999999/edit"):
        assert admin.get(path).status_code == 404
    assert admin.post("/admin/flights/999999/delete").status_code == 404


# ---------------- CSRF on admin actions (SR2) ----------------

def test_admin_actions_need_a_csrf_token():
    app = create_app("testing", {"WTF_CSRF_ENABLED": True})
    with app.app_context():
        seed_demo_data(days=3)
        admin_user = User(email=ADMIN, role="admin")
        admin_user.set_password(PASSWORD)
        db.session.add(admin_user)
        db.session.commit()
    client = app.test_client()
    page = client.get("/login").get_data(as_text=True)
    token = re.search(r'name="csrf_token"[^>]*value="([^"]+)"', page).group(1)
    client.post("/login", data={"email": ADMIN, "password": PASSWORD, "csrf_token": token})

    assert client.post("/admin/flights/new", data=flight_payload()).status_code == 400
    assert client.post("/admin/flights/1/delete").status_code == 400
    assert client.post("/admin/users/1/unlock").status_code == 400
    with app.app_context():
        assert Flight.query.filter_by(flight_no="SP900").count() == 0


# ---------------- The single-view decorator (SR5) ----------------

def test_role_required_decorator_protects_a_single_view(app, users):
    from app.security import role_required

    @app.route("/only-admins")
    @role_required("admin")
    def only_admins():
        return "top secret"

    anonymous = app.test_client()
    assert anonymous.get("/only-admins").status_code == 302

    alice = app.test_client()
    login(alice, ALICE)
    assert alice.get("/only-admins").status_code == 403

    boss = app.test_client()
    login(boss, ADMIN)
    assert boss.get("/only-admins").data == b"top secret"