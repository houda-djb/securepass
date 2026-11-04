"""Phase 21: admin sales reports and the CSV export."""
import csv
import io

import pytest

from app.admin.reports import clean_range, safe_cell
from app.extensions import db
from app.models import AuditLog, User
from tests.test_phase10 import ALICE, PASSWORD, a_flight, login, users  # noqa: F401
from tests.test_phase20 import book_with, reference_of


@pytest.fixture()
def admin_client(app):
    with app.app_context():
        user = User(email="boss@example.com", role="admin")
        user.set_password(PASSWORD)
        db.session.add(user)
        db.session.commit()
    client = app.test_client()
    client.post("/login", data={"email": "boss@example.com", "password": PASSWORD})
    return client


def make_booking(app, method="cib"):
    client = app.test_client()
    login(client)
    return reference_of(book_with(client, a_flight(app), method))


def test_reports_need_an_admin(app, client, users):
    assert client.get("/admin/reports").status_code in (302, 401, 403)
    assert client.get("/admin/reports/bookings.csv").status_code in (302, 401, 403)
    login(client)
    assert client.get("/admin/reports").status_code == 403
    assert client.get("/admin/reports/bookings.csv").status_code == 403


def test_report_page_counts_bookings(app, admin_client, users):
    make_booking(app, "cib")
    make_booking(app, "cash")
    page = admin_client.get("/admin/reports?days=7").get_data(as_text=True)
    assert "CIB card" in page and "Cash at an agency" in page and "LHR to CDG" in page


def test_empty_period_still_renders(admin_client):
    assert admin_client.get("/admin/reports").status_code == 200


def test_bad_range_falls_back_to_default():
    assert clean_range("999") == "30" and clean_range(None) == "30" and clean_range("7") == "7"


def test_csv_lists_bookings_and_is_audited(app, admin_client, users):
    ref = make_booking(app)
    res = admin_client.get("/admin/reports/bookings.csv?days=30")
    assert res.status_code == 200 and res.mimetype == "text/csv"
    assert "attachment" in res.headers["Content-Disposition"]
    rows = list(csv.reader(io.StringIO(res.get_data(as_text=True))))
    assert rows[0][0] == "reference" and any(r[0] == ref and r[3] == "cib" for r in rows[1:])
    with app.app_context():
        assert AuditLog.query.filter_by(event_type="report_exported").count() == 1


def test_csv_cells_cannot_run_as_formulas():
    for risky in ("=1+1", "+cmd", "-2", "@SUM(A1)"):
        assert safe_cell(risky).startswith("'")
    assert safe_cell("ok@example.com") == "ok@example.com" and safe_cell(None) == ""
