# Requirements traceability

Every requirement from the project specification, how it is met, and the proof. "Manual" means
the evidence is a screenshot or a setting you can show, not an automated test.

## Functional requirements

| ID | Requirement | How it is met | Evidence |
|---|---|---|---|
| FR1 | Register with email and password | `/register`, validated form | `test_register_creates_user_with_hashed_password` |
| FR2 | Log in and out | Flask-Login, POST-only logout | `test_login_success_shows_account_in_navbar`, `test_logout_needs_post_and_ends_the_session` |
| FR3 | Lock after 5 failed logins for 15 minutes | Counter and `locked_until` on the user | `test_account_locks_after_five_failures` |
| FR4 | Two roles, user and admin | `role` column, navbar and routes depend on it | `test_navbar_links_depend_on_role`, `test_normal_user_gets_403_on_admin` |
| FR5 | Search by route, date and passengers | `/flights` with server-side validation | `test_search_returns_matching_flights`, `test_return_trip_shows_both_legs` |
| FR6 | Results show number, times, price, seats | Results page | `test_search_returns_matching_flights` |
| FR7 | Flight details page | `/flights/<id>` | `test_flight_detail_page` |
| FR8 | Featured destination cards | Cards read from the database | `test_homepage_featured_cards_come_from_database` |
| FR9 | Book 1 to 9 passengers | Checkout and booking service | `test_successful_booking_reduces_seats_and_is_audited`, `test_invalid_passenger_counts_are_rejected` |
| FR10 | Random booking reference | 8 characters from `secrets` | `test_references_are_random_and_not_the_row_number` |
| FR11 | My Bookings lists only my bookings | Query filtered by user | `test_my_bookings_lists_only_my_own` |
| FR12 | Cancel own booking, seats returned | Cancel service | `test_cancel_returns_the_seats` |
| FR13 | No overbooking, even at the same moment | One atomic conditional update | `test_two_simultaneous_bookings_for_the_last_seat`, `test_last_seat_goes_to_the_first_person_only` |
| FR14 | Simulated payment, no card data | Labelled demo step | `test_checkout_page_shows_total_and_demo_notice` |
| FR15 | Admin adds, edits, removes flights | Admin flight pages | `test_admin_can_add_a_flight`, `test_admin_can_change_price_and_seats`, `test_delete_flight_without_bookings` |
| FR16 | Admin sees the security dashboard | `/admin/` | `test_admin_pages_open_for_admins` |
| FR17 | Failed logins in the last 24 hours | Counted from the audit log | `test_failed_logins_count_only_the_last_24_hours` |
| FR18 | Currently locked accounts | Listed with an Unlock button | `test_locked_accounts_are_listed_and_expired_locks_are_not` |
| FR19 | Recent audit events | Filterable events table | `test_events_table_shows_newest_first_with_user_email`, `test_events_can_be_filtered_by_type` |
| FR20 | Bookings per day chart | Server-drawn SVG | `test_bookings_per_day_fills_in_zero_days`, `test_dashboard_contains_the_chart` |
| FR21 | Latest Bandit and pip-audit summary | `security-scan` command saves it, dashboard shows it | `test_security_scan_command_counts_findings`, `test_dashboard_shows_a_saved_scan` |

## Security requirements

| ID | Requirement | How it is met | Evidence |
|---|---|---|---|
| SR1 | Salted password hashes only | scrypt via Werkzeug | `test_register_creates_user_with_hashed_password` |
| SR2 | CSRF token on every POST | Flask-WTF `CSRFProtect` | `test_post_without_csrf_token_is_rejected`, `test_booking_and_cancel_need_a_csrf_token` |
| SR3 | Server-side input validation | Forms and `validate_search` | `test_invalid_search_is_rejected_with_a_message`, `test_invalid_registration_is_rejected`, `test_bad_flight_data_is_rejected` |
| SR4 | Parameterized queries only | SQLAlchemy everywhere | `test_sql_injection_attempt_is_harmless` |
| SR5 | Server-side access control on every route | Admin guard, `login_required` | `test_every_admin_route_blocks_normal_users`, `test_role_required_decorator_protects_a_single_view` |
| SR6 | Users reach only their own bookings | Lookup by user and reference | `test_booking_page_is_private_to_its_owner` |
| SR7 | Rate-limited login | Flask-Limiter | `test_login_attempts_are_rate_limited` |
| SR8 | Secure session cookies, expiring sessions | Config and `__Host-` cookie name | `test_session_cookie_is_http_only_and_same_site`, `test_production_session_cookie_is_locked_down` |
| SR9 | Security headers: CSP, HSTS, frame and type options | Flask-Talisman | `test_security_headers_are_on_every_response`, `test_csp_only_allows_this_site`, `test_production_sends_hsts_over_https` |
| SR10 | Auto-escaped templates, nothing marked safe | Jinja defaults | `test_script_in_search_is_escaped`, `test_event_details_are_escaped_on_the_dashboard` |
| SR11 | Secrets from the environment, never committed | `config.py`, `.gitignore` | `test_missing_secret_key_is_refused`, `test_secrets_and_databases_are_never_committed` |
| SR12 | Error pages that reveal nothing | Custom 400, 403, 404, 413, 429 and 500 pages | `test_404_page_does_not_leak_details`, `test_an_unexpected_error_shows_a_safe_500_page` |
| SR13 | Security events in an audit log | `audit()` helper and `audit_log` table | `test_login_events_are_audited_without_secrets` |

## Non-functional requirements

| ID | Requirement | How it is met | Evidence |
|---|---|---|---|
| NFR1 | Reference look, desktop and mobile | One stylesheet with breakpoints; the version 2 design system (dark navy and blue, self-hosted Inter font) | Manual: screenshots at desktop and phone width |
| NFR2 | Maintainable code | App factory, blueprints, service layer, README | Manual: project layout in the README |
| NFR3 | Automated tests for the key rules | More than 300 tests, 90 percent coverage gate | `test_ci_runs_every_gate` |
| NFR4 | Search under 2 seconds | Indexed query | `test_search_stays_fast_with_three_months_of_flights` |
| NFR5 | Transactional booking and cancellation | Conditional updates in one transaction | `test_cancelling_twice_returns_seats_only_once`, `test_a_stale_page_cannot_oversell` |
| NFR6 | Runs anywhere with Python 3.12 | CI installs from `requirements.txt` on a clean machine | `test_every_dependency_has_a_version_rule` |
| NFR7 | One branch and pull request per phase | GitHub history | Manual: the closed pull requests on GitHub |

## Technical requirements

| ID | Requirement | How it is met | Evidence |
|---|---|---|---|
| TR1 | HTML, CSS, JavaScript, Jinja | `app/templates`, `app/static` | `test_home_page_loads` |
| TR2 | Flask and its extensions | `requirements.txt` | `test_home_page_loads` |
| TR3 | SQLite through SQLAlchemy | `app/models.py` | `test_featured_airports_are_seeded` |
| TR4 | Git and GitHub, branch per phase | Repository history | Manual: commit and pull request history |
| TR5 | GitHub Actions on every push and pull request | `.github/workflows/ci.yml` | `test_ci_runs_on_pull_requests_and_main` |
| TR6 | Bandit and pip-audit | CI steps and `security-scan` | `test_ci_runs_every_gate`, `test_bandit_gate_rejects_insecure_code_and_accepts_safe_code` |
| TR7 | pytest | `tests/` | The whole suite, run on every pull request (`test_ci_runs_every_gate`) |
| TR8 | Branch protection: merge needs a green build | GitHub setting | Manual: screenshot of the branch protection rule |

## Acceptance criteria

| ID | Criterion | Evidence |
|---|---|---|
| AC1 | A normal user gets 403 on the admin area | `test_normal_user_gets_403_on_admin` |
| AC2 | User A cannot view or cancel user B's booking | `test_booking_page_is_private_to_its_owner`, `test_cannot_cancel_someone_elses_booking` |
| AC3 | A POST without a CSRF token is rejected | `test_post_without_csrf_token_is_rejected`, `test_a_wrong_csrf_token_is_rejected` |
| AC4 | The 6th login attempt after 5 failures is refused | `test_account_locks_after_five_failures` |
| AC5 | Two simultaneous bookings for the last seat: one succeeds | `test_two_simultaneous_bookings_for_the_last_seat` |
| AC6 | An insecure commit fails the pipeline | `test_bandit_gate_rejects_insecure_code_and_accepts_safe_code`; Manual: red-cross screenshot of the demo pull request |
| AC7 | A failed login shows up on the dashboard | `test_a_failed_login_shows_up_on_the_security_dashboard` |
| AC8 | Passwords in the database are hashes | `test_register_creates_user_with_hashed_password` |

## Version 2 additions

Features added after version 1. They extend the requirements above; they do not replace them.

| ID | Addition | How it is met | Evidence |
|---|---|---|---|
| V2-1 | Passenger names on a booking, checked on the server | Checkout fields, `app/bookings/passengers.py`, `passengers` table | `test_names_are_saved_with_the_booking_in_order`, `test_bad_names_are_refused_and_nothing_is_booked`, `test_names_are_not_written_to_the_audit_log` |
| V2-2 | Seat map: one seat per passenger, never two passengers on one seat | `app/bookings/seats.py`, unique constraint per flight | `test_seats_are_saved_and_shown_on_the_booking`, `test_two_passengers_cannot_share_a_seat`, `test_the_database_itself_refuses_a_double_booked_seat`, `test_cancelling_frees_the_seats` |
| V2-3 | Account page with change password and recent activity | `/account`, `/account/password` | `test_account_page_shows_profile_stats_and_history`, `test_password_can_be_changed_and_is_audited`, `test_bad_password_changes_are_refused`, `test_password_change_is_rate_limited` |
| V2-4 | Two-factor login with an authenticator app and recovery codes | `app/auth/totp.py`, `/login/verify`, `/account/2fa` | `test_codes_match_the_published_test_vectors`, `test_login_then_needs_the_code`, `test_a_code_can_only_be_used_once`, `test_too_many_wrong_codes_lock_the_account`, `test_a_recovery_code_logs_in_once`, `test_turning_it_off_needs_password_and_code` |
| V2-5 | Every demo flight names its operating airline | `airlines` table, `flights.airline_code` | `test_demo_data_has_five_airlines_and_every_flight_has_one`, `test_search_results_name_the_operator`, `test_a_flight_without_an_airline_still_works` |
| V2-6 | Database changes through migrations that keep data | `migrations/`, `docs/DATABASE.md` | `test_migrations_build_exactly_the_schema_the_models_describe`, `test_an_older_database_gets_airlines_without_losing_flights`, `test_migrations_also_work_on_a_database_the_app_created_itself`, `test_a_migration_can_be_undone_and_redone` |
| V2-7 | No request to any other site (self-hosted font) | Policy lists only this site | `test_csp_only_allows_this_site`, `test_templates_load_nothing_from_unexpected_sites` |
| V2-8 | Results filters, booking steps and the redesigned pages | `static/js/main.js`, `static/css/style.css`, templates | Manual: screenshots of the home page, results with filters, checkout, seat map and account page |
