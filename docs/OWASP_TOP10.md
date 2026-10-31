# OWASP Top 10 (2021) checklist

For each category: what SecurePass does, where the proof is, and what is **not** covered.
Tests are named so you can run any of them: `pytest -k <name>`.

## A01 Broken Access Control

| Control | Evidence |
|---|---|
| One guard runs before every admin route, so a new admin page cannot be left open | `test_every_admin_route_blocks_anonymous_visitors`, `test_every_admin_route_blocks_normal_users` |
| A normal user gets 403 on the admin area, and the attempt is logged | `test_normal_user_gets_403_on_admin` |
| Bookings are found by owner and reference; someone else's booking looks missing (404) | `test_booking_page_is_private_to_its_owner`, `test_cannot_cancel_someone_elses_booking` |
| State changes are POST-only with a CSRF token | `test_post_without_csrf_token_is_rejected`, `test_booking_and_cancel_need_a_csrf_token`, `test_admin_actions_need_a_csrf_token` |
| Login redirects can only stay on this site, also after the second login step | `test_next_redirect_only_stays_on_this_site`, `test_next_page_survives_the_second_step` |
| Seats and passenger names can be changed only by the booking's owner | `test_only_the_owner_can_open_or_change_seats`, `test_only_the_owner_can_see_passenger_names` |
| Account pages need a login | `test_account_page_needs_a_login`, `test_setup_needs_a_login` |

**Not covered:** there are only two roles, so there is no finer permission model.

## A02 Cryptographic Failures

| Control | Evidence |
|---|---|
| Passwords are stored as salted scrypt hashes | `test_register_creates_user_with_hashed_password` |
| HTTPS is forced in production and HSTS is sent | `test_production_redirects_http_to_https`, `test_production_sends_hsts_over_https` |
| The session cookie is Secure, HttpOnly, SameSite and `__Host-` prefixed in production | `test_production_session_cookie_is_locked_down` |
| No card data exists anywhere; payment is a clearly labelled demo step | `test_checkout_page_shows_total_and_demo_notice` |
| Recovery codes are stored only as keyed hashes | `test_recovery_codes_are_unique_and_hashed_with_a_key`, `test_turning_it_on_saves_the_secret_and_shows_recovery_codes_once` |
| Secrets come from the environment and a weak production key is refused | `test_missing_secret_key_is_refused`, `test_production_refuses_a_weak_secret_key` |

**Not covered:** the SQLite file is not encrypted at rest, and the two-factor secret is stored as plain text in it.

## A03 Injection

| Control | Evidence |
|---|---|
| Parameterized queries only (SQLAlchemy) | `test_sql_injection_attempt_is_harmless`, `test_flight_search_rejects_odd_input_politely` |
| Filter values are checked against a fixed list before use | `test_unknown_filter_values_are_ignored_not_executed` |
| Output is escaped, so injected HTML is shown as text | `test_script_in_search_is_escaped`, `test_event_details_are_escaped_on_the_dashboard` |
| The Content-Security-Policy would block an injected script anyway | `test_csp_only_allows_this_site`, `test_templates_work_with_the_strict_csp` |
| The only subprocess calls use a fixed argument list | `test_bandit_gate_rejects_insecure_code_and_accepts_safe_code` |

## A04 Insecure Design

| Control | Evidence |
|---|---|
| The last seat cannot be sold twice (one atomic update) | `test_two_simultaneous_bookings_for_the_last_seat`, `test_a_stale_page_cannot_oversell` |
| The price comes from the server, never the browser | `test_the_price_comes_from_the_server_not_the_browser` |
| The database refuses impossible data as a second line of defence | `test_seats_can_never_go_negative`, `test_database_rejects_impossible_bookings`, `test_user_roles_are_limited_by_the_database` |
| Cancelling twice returns seats only once | `test_cancelling_twice_returns_seats_only_once` |
| There is no default admin account | `test_create_admin_command` |
| A seat can never belong to two passengers, even in a race: the database refuses it | `test_the_database_itself_refuses_a_double_booked_seat`, `test_a_seat_taken_by_another_booking_is_refused_and_looks_taken` |
| Cancelling frees the seats, and a cancelled or departed booking cannot pick seats | `test_cancelling_frees_the_seats`, `test_a_departed_flight_cannot_change_seats` |
| Database changes are repeatable and reversible | `test_migrations_build_exactly_the_schema_the_models_describe`, `test_a_migration_can_be_undone_and_redone` |

## A05 Security Misconfiguration

| Control | Evidence |
|---|---|
| Strict security headers on every response, including error pages | `test_security_headers_are_on_every_response`, `test_error_pages_carry_the_headers_too` |
| Debug mode is off in production, and the start-up checks refuse weak settings | `test_production_never_runs_in_debug_mode`, `test_production_refuses_to_start_without_a_secret_key` |
| Errors never show a stack trace or file paths | `test_an_unexpected_error_shows_a_safe_500_page`, `test_404_page_does_not_leak_details` |
| Oversized requests are refused | `test_oversized_requests_are_refused` |
| The site loads nothing from other sites, so the policy lists only its own origin | `test_csp_only_allows_this_site`, `test_templates_load_nothing_from_unexpected_sites` |
| Forwarded IP headers are ignored unless a proxy is configured | `test_forwarded_addresses_are_ignored_unless_a_proxy_is_configured` |
| Private pages are never cached | `test_login_and_account_pages_are_never_cached`, `test_admin_pages_are_never_cached` |

**Not covered:** the development server prints a warning and is not meant for production.

## A06 Vulnerable and Outdated Components

| Control | Evidence |
|---|---|
| pip-audit runs on every pull request | `test_ci_runs_every_gate` |
| Dependabot proposes updates every week | `test_dependabot_watches_python_and_actions` |
| Every dependency has a version rule | `test_every_dependency_has_a_version_rule` |
| The dashboard shows the latest scan result | `test_security_scan_command_counts_findings` |

## A07 Identification and Authentication Failures

| Control | Evidence |
|---|---|
| Password rules: 10+ characters, a letter and a number, not the email | `test_invalid_registration_is_rejected`, `test_password_equal_to_email_is_rejected` |
| Lockout after 5 failures, which expires after 15 minutes | `test_account_locks_after_five_failures`, `test_lock_expires_and_counter_resets` |
| Login attempts are rate limited | `test_login_attempts_are_rate_limited` |
| Wrong password and unknown email look the same | `test_wrong_password_and_unknown_email_look_identical` |
| Optional two-factor login with standard time-based codes | `test_codes_match_the_published_test_vectors`, `test_login_then_needs_the_code` |
| A one-time code cannot be replayed, and a half-finished login expires | `test_a_code_can_only_be_used_once`, `test_unfinished_logins_expire` |
| Wrong codes lock the account like wrong passwords | `test_too_many_wrong_codes_lock_the_account` |
| Recovery codes work once | `test_a_recovery_code_logs_in_once` |
| Turning two-factor off needs the password and a code | `test_turning_it_off_needs_password_and_code` |
| Changing the password needs the current one, is rate limited and audited | `test_bad_password_changes_are_refused`, `test_password_change_is_rate_limited`, `test_password_can_be_changed_and_is_audited` |
| A fresh session starts at login; logout ends it | `test_logout_needs_post_and_ends_the_session` |

**Not covered:** no password reset, email verification or breached-password check. Changing a password does not end sessions on other devices.

## A08 Software and Data Integrity Failures

| Control | Evidence |
|---|---|
| A change cannot be merged unless tests, coverage, Bandit and pip-audit pass | `test_ci_runs_every_gate` |
| The pipeline uses least privilege and no dangerous triggers | `test_ci_uses_least_privilege_and_has_a_timeout`, `test_no_workflow_uses_dangerous_settings` |
| Every action is pinned to a version | `test_every_action_is_pinned_to_a_version` |
| Insecure code is rejected by the scan | `test_bandit_gate_rejects_insecure_code_and_accepts_safe_code` |

**Not covered:** actions are pinned to version tags, not commit hashes, and build artifacts are not signed.

## A09 Security Logging and Monitoring Failures

| Control | Evidence |
|---|---|
| Logins, lockouts, bookings, cancellations and denied access are logged | `test_login_events_are_audited_without_secrets`, `test_successful_booking_reduces_seats_and_is_audited` |
| Passwords and tokens never reach the log | `test_login_events_are_audited_without_secrets` |
| Passenger names and two-factor codes never reach the log | `test_names_are_not_written_to_the_audit_log`, `test_password_can_be_changed_and_is_audited` |
| Each person can see their own recent security events | `test_account_page_shows_profile_stats_and_history`, `test_history_shows_only_my_own_events` |
| Admins can see failed logins and locked accounts, and unlock them | `test_a_failed_login_shows_up_on_the_security_dashboard`, `test_admin_can_unlock_an_account_and_it_is_audited` |
| The real client address is recorded when a proxy is configured | `test_forwarded_address_is_used_when_one_proxy_is_configured` |

**Not covered:** there are no alerts or emails, the log lives only in the database, and it is not tamper-evident.

## A10 Server-Side Request Forgery

SecurePass never fetches a URL on a visitor's behalf, so there is nothing to forge. The only outgoing
requests are the command-line scan, which runs Bandit and
pip-audit with fixed arguments.