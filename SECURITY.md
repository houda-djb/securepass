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
| Sessions | HttpOnly, SameSite=Lax cookies; new session on login; 30 minute lifetime; Secure `__Host-` cookie in production |
| Browser | Content-Security-Policy (own site and Google Fonts only), HSTS, no framing, no caching of private pages |
| Forms | CSRF token on every POST; server-side validation of all input |
| Access | Server-side role checks on every admin route; bookings are private to their owner |
| Data | Parameterized queries only (SQLAlchemy); database constraints as a second line of defence |
| Bookings | Seats claimed with one atomic update, so the last seat can never be sold twice |
| Monitoring | Audit log of security events, shown on the admin dashboard |
| Pipeline | Tests with a coverage gate, Bandit, pip-audit, Dependabot |

## Known limits (see the project report, "Future work")

- Rate-limit counters are kept in memory and reset when the server restarts.
- No email verification, password reset or two-factor authentication yet.
- Payments are simulated; no card data is ever collected.