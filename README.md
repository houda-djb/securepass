# SecurePass

A secure flight booking website (final-year project). Flask + SQLite + HTML/CSS/JavaScript,
with GitHub Actions CI, Bandit and pip-audit.

**Status:** Phase 0 (setup) and Phase 1 (frontend shell) complete.

## Quick start

```bash
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements-dev.txt

cp .env.example .env               # Windows: copy .env.example .env
python -c "import secrets; print(secrets.token_hex(32))"   # paste into SECRET_KEY in .env

flask --app wsgi run               # open http://127.0.0.1:5000
```

## Run the checks (same as CI)

```bash
pytest -q
bandit -r app config.py -ll
pip-audit -r requirements.txt
```

## Project layout

```
app/
  __init__.py        create_app() factory, error handlers
  main/routes.py     home page, placeholder routes
  templates/         base.html, index.html, errors/
  static/            css/, js/, img/
config.py            config classes; secrets from environment (SR11)
tests/               pytest suite
.github/workflows/   CI: pytest + Bandit + pip-audit
```

## Git workflow (one branch per phase)

```bash
git init -b main
git add . && git commit -m "Phase 0-1: project skeleton and frontend shell"
git remote add origin <your-github-repo-url>
git push -u origin main
git checkout -b phase-2-flights    # next phase
```

After the first push, enable **Settings > Branches > Branch protection** on `main` and require
the `test-and-scan` check before merging (TR8).

## Adding real destination photos

The destination cards use CSS gradients as placeholders. To use photos, put images in
`app/static/img/` and add to `style.css`, for example:

```css
.dest-tokyo { background-image: url("../img/tokyo.jpg"); }
```

## Roadmap

| Phase | Scope | Status |
|---|---|---|
| 0 | Setup, app factory, tests, CI | Done |
| 1 | Frontend shell from the reference image | Done |
| 2 | Database, flight search and details | Next |
| 3 | Authentication and roles | |
| 4 | Secure bookings | |
| 5 | Audit log and security dashboard | |
| 6 | Full CI hardening | |
| 7 | Security headers, write-up | |

## Security notes so far

- SR11: `SECRET_KEY` read from the environment; the app refuses to start without one (tests cover this).
- SR8: session cookies are `HttpOnly` and `SameSite=Lax`; `Secure` is on in `ProductionConfig`.
- SR10: Jinja auto-escaping is on; no `|safe` is used anywhere.
- SR12: custom 404/500 pages, no stack traces.
- Phase 7 will add a Content-Security-Policy; it must allow `fonts.googleapis.com` and
  `fonts.gstatic.com` (or self-host the fonts).