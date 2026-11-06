# SecurePass v3.1: languages, privacy and photos

Version 3.1 adds three things on top of v3.0 (`V3_RELEASE.md`). Each row names the automated test that proves it.

## 1. What is new

| Area | Change | Evidence |
|---|---|---|
| Languages | English, French and Arabic, with right-to-left layout for Arabic; the choice is kept for the visit | test_french_page_is_translated, test_arabic_page_is_right_to_left, test_language_choice_is_remembered_across_pages |
| Language quality | Every phrase has both translations and the same placeholders | test_every_text_has_french_and_arabic, test_placeholders_match_in_every_language |
| Dates | Days and months follow the language | test_dates_and_months_follow_the_language |
| Your data | A signed-in user can download everything held about them as a JSON file | test_export_contains_my_data_and_no_secrets, test_export_only_has_my_bookings |
| Account deletion | The owner can delete the account with the word "delete" and the current password; future seats go back to the flight | test_delete_needs_the_word_and_the_password, test_delete_removes_account_bookings_and_gives_seats_back |
| Disclosure | A `security.txt` file says where to report a vulnerability | test_security_txt_is_published |
| Photos | Real photos for cities and countries, prepared by a helper script (see `PHOTOS.md`) | Manual: checked on the home and country pages |

## 2. Security decisions

| Risk | Decision | Evidence |
|---|---|---|
| Forged language value | Only `en`, `fr` and `ar` are accepted; anything else is ignored | test_unknown_language_is_ignored |
| Open redirect on the language switch | The return address must be a local path | test_language_switch_refuses_outside_redirects |
| CSRF on the language switch | The form carries a token | test_language_form_carries_a_csrf_token |
| Secrets in the data download | The file never holds the password hash, the two-factor secret or recovery codes | test_export_contains_my_data_and_no_secrets |
| Someone else's data | The download only lists the signed-in user's own bookings | test_export_only_has_my_bookings |
| Deleting by mistake or by someone at an open screen | The word "delete" and the current password are both required, and every refusal is logged | test_delete_needs_the_word_and_the_password |
| Leaving the site without an administrator | The only administrator cannot delete their own account | test_only_admin_cannot_delete_account |
| Personal data left in logs | After deletion the audit lines stay but are no longer linked to a person | test_delete_removes_account_bookings_and_gives_seats_back |

## 3. Known limits

- Only the interface is translated. Server error messages, emails, the admin area and the place descriptions stay in English.
- Payments are still a demo, and there is no seat hold with a countdown yet.
- Arabic numerals in prices follow the browser, and dinar amounts keep the code `DZD`.

## 4. Release checklist

1. All tests green in CI on SQLite and on PostgreSQL.
2. Render shows "Live" and `/healthz` says `ok`.
3. Click `FR` then `ع` in the header and check the home page and a flight search.
4. Open My account, download the data file, and check it holds no password.
5. Open `/.well-known/security.txt`.
6. Tag the release: `git tag v3.1 && git push origin v3.1`.
