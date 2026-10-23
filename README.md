# SecurePass

A secure flight booking website (final-year project). Flask + SQLite + HTML/CSS/JavaScript,
with a DevSecOps pipeline: GitHub Actions, Bandit, pip-audit and Dependabot.

![CI](https://github.com/houda-djb/securepass/actions/workflows/ci.yml/badge.svg)

## Quick start

```bash
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements-dev.txt

cp .env.example .env               # Windows: copy .env.example .env
python -c "import secrets; print(secrets.token_hex(32))"   # paste into SECRET_KEY in .env

flask --app wsgi seed              # demo airports and flights
flask --app wsgi create-admin      # asks for an email and a password
flask --app wsgi run --debug       # open http://127.0.0.1:5000
```

## Commands

| Command | What it does |
|---|---|
| `flask --app wsgi seed` | Adds demo airports and flights (does nothing if they exist) |
| `flask --app wsgi reset-db` | Deletes everything, including accounts, and rebuilds the demo data |
| `flask --app wsgi create-admin` | Creates an admin account (no default admin exists) |
| `flask --app wsgi security-scan` | Runs Bandit and pip-audit and saves a summary for the admin dashboard |

## Run the same checks as CI

```bash
pytest -q --cov=app --cov-report=term-missing --cov-fail-under=90
bandit -r app config.py -ll
pip-audit -r requirements.txt
```

## Features

- Flight search with server-side validation, results and details pages
- Registration, login, logout, roles (`user`, `admin`)
- Bookings: checkout (demo payment), My Bookings, cancellation
- Admin area: security dashboard, account unlock, flight management

## Security controls

| Requirement | Control | Where |
|---|---|---|
| SR1 | Salted scrypt password hashes | `app/models.py` |
| SR2 | CSRF token on every POST | `app/extensions.py` (CSRFProtect) |
| SR3 | Server-side input validation | `app/flights/validation.py`, `app/*/forms.py` |
| SR4 | Parameterized queries only | SQLAlchemy everywhere |
| SR5 | Role checks on the server, admin guard on the whole blueprint | `app/security.py`, `app/admin/__init__.py` |
| SR6 | Bookings looked up by user and reference | `app/bookings/routes.py` |
| SR7 | Login and registration rate limits | `app/auth/routes.py` |
| SR8 | Secure, HttpOnly, SameSite `__Host-` cookie in production, 30 minute sessions | `config.py` |
| SR9 | Content-Security-Policy, HSTS, frame, referrer and permissions headers | `app/security_headers.py` |
| SR10 | Auto-escaped templates, no `\|safe` | `app/templates/` |
| SR11 | Secrets from environment variables, weak production key refused | `config.py`, `app/__init__.py` |
| SR12 | Custom error pages without internals | `app/templates/errors/` |
| SR13 | Audit log of security events | `app/security.py`, dashboard |
| FR13 | One atomic UPDATE claims seats | `app/bookings/service.py` |
| TR5, TR6 | Tests, Bandit, pip-audit on every pull request | `.github/workflows/` |

## Documentation

| Document | What it is for |
|---|---|
| [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) | Diagrams: system, data model, safe booking, delivery pipeline, production setup |
| [docs/OWASP_TOP10.md](docs/OWASP_TOP10.md) | The OWASP Top 10 checklist: controls, proof and what is not covered |
| [docs/TRACEABILITY.md](docs/TRACEABILITY.md) | Every requirement mapped to how it is met and the test that proves it |
| [docs/DEMO_SCRIPT.md](docs/DEMO_SCRIPT.md) | A 10 minute demo and likely questions |
| [SECURITY.md](SECURITY.md) | Reporting policy and known limits |

Tests check these documents, so a renamed test or a missing requirement fails the build.

## Running in production

| Setting | Value |
|---|---|
| `FLASK_ENV` | `production` (HTTPS redirect, HSTS, Secure cookies) |
| `SECRET_KEY` | Random, at least 32 characters. The app refuses to start otherwise. |
| `PROXY_HOPS` | Number of reverse proxies in front of the app, for example `1`. Leave `0` if none. |

Use a production server (Waitress on Windows, Gunicorn on Linux) behind a proxy that handles TLS.
`flask run` is for development only. Details are in [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md).

## Project layout

```
app/
  __init__.py          create_app() factory, error handlers, production checks
  models.py            Airport, Flight, User, AuditLog, Booking
  security.py          audit log, role checks, safe redirects
  security_headers.py  Content-Security-Policy and the other browser headers
  auth/                register, login, logout, password rules
  flights/             search, results, details
  bookings/            checkout, My Bookings, cancel (rules in service.py)
  admin/               dashboard, flight management, scan summary
  templates/ static/
config.py              settings; secrets come from the environment
docs/                  architecture, OWASP checklist, traceability, demo script
tests/                 unit, security, pipeline and documentation tests
.github/               CI workflow, Dependabot
```

## Git workflow (one branch per phase)

```bash
git checkout -b phase-7-hardening
# ... work, commit ...
git push -u origin phase-7-hardening   # then open a pull request; merge when CI is green
```

## Roadmap

| Phase | Scope | Status |
|---|---|---|
| 0 | Setup, app factory, tests, CI | Done |
| 1 | Frontend shell from the reference image | Done |
| 2 | Database, flight search and details | Done |
| 3 | Authentication and roles | Done |
| 4 | Secure bookings | Done |
| 5 | Audit log and security dashboard | Done |
| 6 | CI hardening | Done |
| 7 | Security headers, production hardening, documentation | Done |

## Future work

Two-factor authentication, email verification and password reset, a real payment provider,
PostgreSQL with migrations, alerting on the audit log, a Docker image, and a second static
analysis tool such as Semgrep.

## Adding real destination photos

Put `tokyo.jpg`, `santorini.jpg` and `serengeti.jpg` in `app/static/img/destinations/`.
They appear automatically; until then the cards show a coloured gradient.