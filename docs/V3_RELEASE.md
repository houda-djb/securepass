# SecurePass v3.0: what changed and how it is checked

Version 3 turns the v2 flight-booking project into a deployed, Algeria-first product. This page lists each change, the security reasoning behind it, and the automated test that proves it. Nothing here relies on a manual check except the photo and visual review at the end.

## 1. What is new

| Area | Change | Evidence |
|---|---|---|
| Destinations | 19 countries and 28 cities, each with a page, best months and trip styles | test_countries_page_lists_every_country, test_country_page_shows_best_time_and_cities, test_unknown_country_is_404 |
| Flight coverage | Algiers is the hub: every city has flights to and from it, plus domestic and original routes, for 90 days | test_every_pair_of_airports_has_a_flight, test_istanbul_to_tokyo_can_be_searched |
| Seasonal advice | The home page and `/plan` suggest countries for a season or month and a trip style | test_plan_page_filters_by_month_and_style, test_home_shows_a_season_and_ignores_a_bad_one, test_season_helpers |
| Prices | Dinar by default, with a euro and dollar switch. Prices are stored once in dollar cents; other currencies are display only | test_money_formats_each_currency, test_currency_switch_is_remembered |
| Payment choice | Bank card, CIB, BaridiMob or cash at an agency (demo only, no card data) | test_checkout_offers_every_method, test_chosen_method_is_saved_and_shown |
| E-ticket | A printable boarding pass with a barcode, for the owner of a confirmed booking | test_ticket_shows_reference_and_barcode, test_cancelled_booking_has_no_ticket |
| Email | A confirmation email after each booking | test_confirmation_email_is_queued |
| Account recovery | Forgot password and reset by a signed, expiring, single-use link | test_reset_flow_changes_the_password, test_a_link_works_only_once |
| Admin | Airline picker on the flight form, sales reports and a CSV export | test_report_page_counts_bookings, test_csv_lists_bookings_and_is_audited |
| Operations | PostgreSQL, Docker, a Render Blueprint, a health check and a first-admin bootstrap | test_dockerfile_does_not_run_as_root, test_health_check_says_ok, test_bootstrap_creates_the_first_admin |
| Design | New visual identity, boarding-pass results and a mobile layout | Manual: reviewed on desktop and phone widths |

## 2. Security decisions made in v3

| Risk | Decision | Evidence |
|---|---|---|
| Weak passwords | At least 10 characters, a letter and a number, not a common password, not the email name | test_common_passwords_are_refused, test_a_good_password_is_still_accepted |
| Account guessing through reset | The same answer is given for known and unknown emails, and the link never reaches the audit log | test_known_and_unknown_emails_get_the_same_answer, test_the_link_never_appears_in_the_audit_log |
| Forged or old reset links | Links expire and work once | test_expired_and_forged_links_are_refused |
| Forged payment option | Only keys from a fixed list are accepted; anything else becomes "card" | test_clean_method_accepts_only_known_options, test_forged_method_falls_back_to_card |
| Someone else's ticket | Tickets are looked up by owner and reference; others get a 404 | test_ticket_belongs_to_its_owner_only |
| Open redirect on the currency switch | The return address must be a local path | test_currency_switch_rejects_unknown_codes_and_outside_redirects |
| CSRF on the currency switch | The form carries a token | test_currency_form_carries_a_csrf_token |
| Spreadsheet formula injection | Every CSV cell that starts with `=`, `+`, `-` or `@` is defused | test_csv_cells_cannot_run_as_formulas |
| Data export without a trace | Every export is written to the audit log | test_csv_lists_bookings_and_is_audited |
| Reports open to users | The whole admin area requires the admin role | test_reports_need_an_admin |
| Secrets in the repository | The real env file is never committed and compose requires secrets | test_the_real_env_file_is_never_committed, test_compose_requires_secrets_instead_of_hard_coding_them |
| Container running as root | The image uses a non-root user | test_dockerfile_does_not_run_as_root |

## 3. Data and deployment

- The database is PostgreSQL in production and SQLite on a laptop. Migrations `0004` (countries) and `0005` (payment method) are safe to run twice.
- Seeding is repeatable: running it again adds nothing (test_seeding_twice_adds_nothing, test_seed_adds_countries_and_hub_flights_once).
- The first deploy after this release adds about 8,600 flights, 18 airports and 19 countries to the live database.
- Render free tier limits: no shell, outgoing mail on port 587 is blocked (use 2525 with your mail provider), and the free database expires after 30 days, so export or recreate it in time. See `DEPLOYMENT.md` and `DATABASE.md`.

## 4. Known limits (honest list)

- Payments are a demo. No money or card data is handled anywhere.
- Rates for dinar and euro are fixed and indicative, not live.
- There is no seat hold with a countdown yet: seats are claimed when the booking is confirmed.
- The site is in English only. Arabic and French with right-to-left layout are planned.
- Photos are optional. Without them the pages show coloured placeholders (see `PHOTOS.md`).

## 5. Release checklist

1. All tests green on SQLite and on PostgreSQL in CI.
2. Pull request merged to `main`; Render shows "Live".
3. Open `/healthz` on the live site and see `ok`.
4. Log in as the admin, open Reports, download a CSV.
5. Make one demo booking with each payment method and open its e-ticket.
6. Remove `ADMIN_PASSWORD` from Render after the first admin login.
7. Tag the release: `git tag v3.0 && git push origin v3.0`.
