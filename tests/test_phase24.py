"""Phase 24: English, French and Arabic (right to left)."""
from datetime import date

from app.i18n import CATALOG, ROWS, clean_lang, long_date, translate_months
from tests.test_phase10 import ALICE, a_flight, login, users  # noqa: F401
from tests.test_phase20 import book_with, reference_of


def choose(client, lang, next_url="/"):
    return client.post("/language", data={"lang": lang, "next": next_url})


def test_site_is_english_by_default(client):
    page = client.get("/").get_data(as_text=True)
    assert '<html lang="en" dir="ltr">' in page and "Where to next from Alger?" in page


def test_french_page_is_translated(client):
    choose(client, "fr")
    page = client.get("/").get_data(as_text=True)
    assert '<html lang="fr" dir="ltr">' in page and "Où aller depuis Alger ?" in page
    assert "Planifier par mois" in page


def test_arabic_page_is_right_to_left(client):
    choose(client, "ar")
    page = client.get("/").get_data(as_text=True)
    assert '<html lang="ar" dir="rtl">' in page and "استكشاف الرحلات" in page


def test_language_choice_is_remembered_across_pages(client):
    choose(client, "ar")
    assert 'dir="rtl"' in client.get("/countries").get_data(as_text=True)
    assert "الجزائر" in client.get("/countries").get_data(as_text=True)


def test_unknown_language_is_ignored(client):
    choose(client, "xx")
    assert 'lang="en"' in client.get("/").get_data(as_text=True)
    assert clean_lang("<script>") == "en" and clean_lang(None) == "en"


def test_language_switch_refuses_outside_redirects(client):
    res = client.post("/language", data={"lang": "fr", "next": "https://evil.example/"})
    assert res.status_code == 302 and "evil.example" not in res.headers["Location"]


def test_language_form_carries_a_csrf_token(client):
    page = client.get("/").get_data(as_text=True)
    assert 'action="/language"' in page and 'name="csrf_token"' in page


def test_every_text_has_french_and_arabic():
    for lang in ("fr", "ar"):
        assert set(CATALOG[lang]) == set(ROWS)
        assert all(text.strip() for text in CATALOG[lang].values())


def test_placeholders_match_in_every_language():
    import re
    for english, (french, arabic) in ROWS.items():
        wanted = sorted(re.findall(r"%\(\w+\)s", english))
        assert sorted(re.findall(r"%\(\w+\)s", french)) == wanted, english
        assert sorted(re.findall(r"%\(\w+\)s", arabic)) == wanted, english


def test_dates_and_months_follow_the_language(app, client):
    choose(client, "fr")
    with client:
        client.get("/")
        assert long_date(date(2026, 11, 9)) == "lundi 09 novembre 2026"
        assert translate_months("Mar to May, Sep to Nov") == "mars à mai, sept. à nov."


def test_search_page_and_checkout_work_in_arabic(app, client, users):
    login(client)
    choose(client, "ar")
    fid = a_flight(app)
    assert client.get(f"/bookings/new/{fid}").status_code == 200
    res = book_with(client, fid, "cib")
    ref = reference_of(res)
    page = client.get(f"/bookings/{ref}/ticket").get_data(as_text=True)
    assert 'dir="rtl"' in page and ref in page


def test_every_public_page_renders_in_each_language(app, client):
    day = date.today().isoformat()
    for lang in ("fr", "ar"):
        choose(client, lang)
        for url in ("/", "/countries", "/countries/japan", "/plan?month=7", "/login", "/register",
                    f"/flights?search=1&origin=ALG&destination=IST&departure={day}&passengers=1"):
            assert client.get(url).status_code == 200, (lang, url)
