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

flask --app wsgi db upgrade        # create or update the database tables
flask --app wsgi seed              # demo airports, airlines and flights
flask --app wsgi create-admin      # asks for an email and a password
flask --app wsgi run --debug       # open http://127.0.0.1:5000
```

## Commands

| Command | What it does |
|---|---|
| `flask --app wsgi db upgrade` | Brings any database up to date with the latest migrations (safe to repeat) |
| `flask --app wsgi db migrate -m "text"` | Records a model change as a new migration (read it before committing) |
| `flask --app wsgi seed` | Adds demo airports, airlines and flights (does nothing if they exist) |
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
- Results filters (sort, price, time of day, airline) that work on the page without reloading
- Airlines: every demo flight names the carrier that operates it
- Registration, login, logout, roles (`user`, `admin`)
- Two-factor login with an authenticator app (QR code, one-time recovery codes)
- My account: profile, trip counts, your own recent security activity, change password
- Bookings: passenger names, seat map, checkout (demo payment), My Bookings, cancellation
- Admin area: security dashboard, account unlock, flight management
- Database migrations (Flask-Migrate), so the structure can change without losing data

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
| SR1, SR7 (v2) | Two-factor login: time-based codes (RFC 6238), no code reuse, lockout on wrong codes, keyed-hash recovery codes | `app/auth/totp.py`, `app/auth/routes.py` |
| SR3 (v2) | Passenger names and seat labels checked on the server | `app/bookings/passengers.py`, `app/bookings/seats.py` |
| FR13 (v2) | A seat can go to one passenger only, enforced by the database | `app/models.py` (`uq_seat_per_flight`) |
| SR9 (v2) | The page loads nothing from other sites: the font is served from `static/fonts` | `app/security_headers.py` |
| FR13 | One atomic UPDATE claims seats | `app/bookings/service.py` |
| TR5, TR6 | Tests, Bandit, pip-audit on every pull request | `.github/workflows/` |

## Documentation

| Document | What it is for |
|---|---|
| [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) | Diagrams: system, data model, safe booking, delivery pipeline, production setup |
| [docs/OWASP_TOP10.md](docs/OWASP_TOP10.md) | The OWASP Top 10 checklist: controls, proof and what is not covered |
| [docs/TRACEABILITY.md](docs/TRACEABILITY.md) | Every requirement mapped to how it is met and the test that proves it |
| [docs/DATABASE.md](docs/DATABASE.md) | Migrations: the commands and the history of the database structure |
| [docs/DEMO_V2.md](docs/DEMO_V2.md) | A 5 minute walk through the version 2 features |
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
  models.py            Airport, Airline, Flight, User, AuditLog, Booking, Passenger,
                       SeatAssignment, RecoveryCode
  security.py          audit log, role checks, safe redirects
  security_headers.py  Content-Security-Policy and the other browser headers
  auth/                register, login, logout, password rules, account page, two-factor (totp.py)
  flights/             search, results, details
  bookings/            checkout, My Bookings, cancel (rules in service.py),
                       passenger names (passengers.py), seat map (seats.py)
  admin/               dashboard, flight management, scan summary
  templates/ static/   one stylesheet (style.css), one script (main.js), self-hosted font
migrations/            database migrations (Flask-Migrate)
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
| 8 | Version 2: new design system, search filters, booking steps | Done |
| 9 | Passenger names and the account page | Done |
| 10 | Seat map | Done |
| 11 | Airlines and database migrations | Done |
| 12 | Two-factor login | Done |
| 13 | Version 2 documentation | Done |

## Future work

Email verification and password reset, a real payment provider, PostgreSQL (migrations are
already in place), alerting on the audit log, encrypting the two-factor secret at rest, choosing
the airline in the admin flight form, multi-city search, a Docker image, and a second static
analysis tool such as Semgrep.

## Adding real destination photos

The destination cards use illustrated scenes (`app/static/img/destinations/<name>.svg`). To use a
real photo instead, add a file with the same name and a `.jpg` ending, for example `tokyo.jpg`
in that folder. It is used automatically. Only files from this site are allowed by the
Content-Security-Policy, so photos must be stored here, not linked from another site.