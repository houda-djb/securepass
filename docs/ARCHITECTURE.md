# SecurePass architecture

SecurePass is a server-rendered Flask application. The browser receives finished HTML pages,
so sessions, validation and access control all stay on the server.

## System overview

```mermaid
flowchart LR
    B[Browser] -->|HTTPS| H[Security headers and HTTPS redirect<br/>Flask-Talisman]
    H --> C[CSRF check and rate limits]
    C --> R[Routes<br/>main, flights, auth, bookings, admin]
    R --> V[Validation and booking rules<br/>forms and service layer]
    V --> D[(SQLite database<br/>via SQLAlchemy)]
    R --> A[Audit log]
    A --> D
```

| Part | Technology | Responsibility |
|---|---|---|
| Frontend | HTML, CSS, a little JavaScript, Jinja templates | Pages, forms, small helpers such as upper-casing airport codes |
| Web layer | Flask with blueprints | One blueprint per area: `main`, `flights`, `auth`, `bookings`, `admin` |
| Security layer | Flask-Talisman, Flask-WTF, Flask-Limiter, Flask-Login | Headers, CSRF, rate limits, sessions |
| Rules | `app/bookings/service.py`, `app/flights/validation.py`, forms | Business rules kept out of the route functions |
| Data | SQLite through Flask-SQLAlchemy, structure changes recorded with Flask-Migrate | Nine tables, with database constraints as a second line of defence |

## Data model

```mermaid
erDiagram
    USER ||--o{ BOOKING : makes
    USER ||--o{ RECOVERY_CODE : owns
    FLIGHT ||--o{ BOOKING : receives
    AIRLINE |o--o{ FLIGHT : operates
    BOOKING ||--o{ PASSENGER : carries
    PASSENGER |o--o| SEAT_ASSIGNMENT : sits
    FLIGHT ||--o{ SEAT_ASSIGNMENT : seats
    AIRPORT ||--o{ FLIGHT : origin
    AIRPORT ||--o{ FLIGHT : destination
    USER |o--o{ AUDIT_LOG : triggers

    USER {
        int id PK
        string email UK
        string password_hash
        string role
        int failed_logins
        datetime locked_until
        bool totp_enabled
        string totp_secret
    }
    RECOVERY_CODE {
        int id PK
        int user_id FK
        string code_hash
        datetime used_at
    }
    AIRLINE {
        string code PK
        string name
    }
    PASSENGER {
        int id PK
        int booking_id FK
        int position
        string first_name
        string last_name
    }
    SEAT_ASSIGNMENT {
        int id PK
        int passenger_id FK
        int flight_id FK
        string label
    }
    AIRPORT {
        string code PK
        string city
        string country
        int featured_rank
    }
    FLIGHT {
        int id PK
        string flight_no
        string origin_code FK
        string destination_code FK
        datetime departs_at
        datetime arrives_at
        int price_cents
        int seats_available
        string airline_code FK
    }
    BOOKING {
        int id PK
        string reference UK
        int user_id FK
        int flight_id FK
        int passengers
        int total_cents
        string status
    }
    AUDIT_LOG {
        int id PK
        int user_id FK
        string event_type
        string ip
        string detail
        datetime created_at
    }
```

Database rules that hold even if application code has a bug: seats can never be negative,
a flight cannot start and end at the same airport, a booking has 1 to 9 passengers and a valid
status, a role is only `user` or `admin`, a flight number can depart only once at a given time,
and a seat on a flight can belong to only one passenger (`uq_seat_per_flight`).

### How the seat map works

Every flight uses the same cabin: 30 rows with seats A to C and D to F. The database only
counts free seats, so the seats chosen inside SecurePass are known exactly (`SEAT_ASSIGNMENT`),
and the remaining sold seats are picked by a fixed shuffle that depends only on the flight. The
map therefore looks the same on every visit. A seat is checked on the server, and the unique
constraint is the last line of defence if two people choose the same seat at the same moment.

### Database migrations

The structure of the database is recorded in `migrations/versions/`. `flask db upgrade` brings
any database, new or old, to the latest structure without losing data. The two history steps
are described in [DATABASE.md](DATABASE.md).

## How a booking is made safely

The last seat must never be sold twice, even when two people press the button at the same
moment. The seat count is changed with one conditional `UPDATE`, so the database itself does
"check and subtract" as a single step.

```mermaid
sequenceDiagram
    participant U as User
    participant F as Flask route
    participant S as Booking service
    participant D as Database
    U->>F: POST booking form with CSRF token
    F->>F: check login, CSRF token and passenger count
    F->>S: create_booking
    S->>D: UPDATE seats = seats - n WHERE seats >= n
    alt one row changed
        S->>D: INSERT booking with random reference
        D-->>S: commit seats and booking together
        S-->>F: booking
        F->>D: write audit event booking_created
        F-->>U: redirect to the booking page
    else no row changed
        S-->>F: BookingError, seats were just taken
        F-->>U: 400 page with a clear message
    end
```

The price is never read from the browser: the server works out the total from the flight.

## How two-factor login works

A person who turned on two-factor login must prove two things: the password and a code from an
authenticator app. After the correct password nobody is logged in yet. The signed session only
remembers who is half-way through, and for five minutes.

```mermaid
sequenceDiagram
    participant U as User
    participant F as Flask route
    participant D as Database
    U->>F: POST /login with email and password
    F->>D: check the password hash and the lockout
    alt password wrong
        F-->>U: 401, same message as an unknown email
    else password right and two-factor on
        F->>F: remember the half-finished login in the signed session
        F-->>U: redirect to /login/verify
        U->>F: POST the 6-digit code or a recovery code
        F->>D: check the code, refuse one already used, count wrong tries
        alt code right
            F->>F: clear the session, log the user in
            F-->>U: redirect to the page asked for
        else code wrong
            F-->>U: 401, and after 5 failures the account locks
        end
    end
```

The codes follow RFC 6238 (30 second time slots, 6 digits) and are written with the Python
standard library only. A code from a time slot that was already accepted is refused, so a code
seen over someone's shoulder cannot be replayed. Recovery codes work once and are stored only as
keyed hashes.

## Layers of defence on a request

1. **Transport.** In production, HTTP is redirected to HTTPS and HSTS tells browsers to
   stay on HTTPS. The session cookie is `Secure`, `HttpOnly`, `SameSite=Lax` and named
   `__Host-session`.
2. **Browser rules.** The Content-Security-Policy allows only this site; fonts, styles and scripts are all served from its own static folder. Framing,
   plugins and injected `<base>` tags are blocked. Private pages are sent with `Cache-Control: no-store`.
3. **Request checks.** Every POST needs a CSRF token. Login and registration are rate limited.
   Request bodies are limited to 100 KB.
4. **Identity and access.** Flask-Login sessions, a lockout after 5 failed logins, an optional second
   step with an authenticator code, a guard on the whole admin blueprint, and booking and seat lookups
   by owner and reference.
5. **Input.** Every field is validated on the server. Database access uses SQLAlchemy only, and
   templates auto-escape output.
6. **Evidence.** Security events are written to the audit log and shown on the admin dashboard.

## Delivery pipeline

```mermaid
flowchart LR
    DEV[Developer] --> BR[Feature branch]
    BR --> PR[Pull request]
    PR --> CI[GitHub Actions]
    CI --> T[Tests and 90 percent coverage gate]
    CI --> S[Bandit static analysis]
    CI --> P[pip-audit dependency check]
    T --> G{All green?}
    S --> G
    P --> G
    G -->|yes| M[Merge to main]
    G -->|no| X[Merge blocked]
```

Dependabot opens a weekly pull request for newer Python packages and GitHub Actions, and each
of those goes through the same gates.

## Running it in production

| Setting | Value |
|---|---|
| `FLASK_ENV` | `production` (turns on HTTPS redirect, HSTS, Secure cookies) |
| `SECRET_KEY` | A random value of at least 32 characters. The app refuses to start otherwise. |
| `DATABASE_URL` | Optional. Defaults to `instance/securepass.db`. |
| `PROXY_HOPS` | Number of reverse proxies in front of the app (for example `1`). Leave at `0` when there is none. |

Run it with a production server, not `flask run`: Waitress on Windows, Gunicorn on Linux, with a
reverse proxy that handles the TLS certificate. Run
`flask --app wsgi db upgrade` after every update, then create the first admin with
`flask --app wsgi create-admin`. Back up the `instance/` folder.

## Known limits

SQLite suits a demo, not heavy traffic (PostgreSQL would be the next step). Rate-limit counters live
in memory. There is no email verification or password reset yet, the two-factor secret is stored unencrypted,
and payments are simulated.