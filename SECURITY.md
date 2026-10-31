# Security policy

SecurePass is a final-year project that uses demo data only. It is not deployed with real
customers, but vulnerabilities are still taken seriously.

## Reporting a vulnerability

Please do **not** open a public issue for a security problem.

Contact the maintainer privately instead (GitHub: **houda-djb**), or use the **Report a
vulnerability** button in the repository's **Security** tab if it is available. Include the
steps to reproduce the problem and what you expected to happen.

## What is protected

| Area | Control |
|---|---|
| Passwords | Salted scrypt hashes, 10+ characters, lockout after 5 failures, rate limiting |
| Two-factor login | Optional authenticator-app codes; a code works once; wrong codes count toward the lockout; recovery codes are single-use and stored only as keyed hashes |
| Sessions | HttpOnly, SameSite=Lax cookies; new session on login; 30 minute lifetime; Secure `__Host-` cookie in production |
| Browser | Content-Security-Policy (own site only; the font is self-hosted), HSTS, no framing, no caching of private pages |
| Forms | CSRF token on every POST; server-side validation of all input |
| Access | Server-side role checks on every admin route; bookings are private to their owner |
| Data | Parameterized queries only (SQLAlchemy); database constraints as a second line of defence |
| Bookings | Seats claimed with one atomic update, so the last seat can never be sold twice; a chosen seat is unique per flight in the database itself |
| Monitoring | Audit log of security events (including password changes and two-factor changes), shown on the admin dashboard; each person sees their own recent activity on the account page |
| Pipeline | Tests with a coverage gate, Bandit, pip-audit, Dependabot |

## Known limits (see the project report, "Future work")

- Rate-limit counters are kept in memory and reset when the server restarts.
- No email verification or password reset yet. A forgotten password with two-factor login on needs a recovery code and a password the person still knows.
- The two-factor secret is stored as plain text in the database (common for authenticator codes). A production system would encrypt it with a managed key.
- Changing a password does not end the person's other sessions on other devices.
- Payments are simulated; no card data is ever collected.