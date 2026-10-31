# Version 2 demo (about 5 minutes)

Run `flask --app wsgi db upgrade`, `flask --app wsgi seed` and `flask --app wsgi run`, then open
http://127.0.0.1:5000. Keep an authenticator app ready on a phone.

| Step | What to do | What to say |
|---|---|---|
| 1. Home | Show the hero, the search card and the destination prices | Prices come from the cheapest upcoming flight in the database. The page loads nothing from other sites. |
| 2. Search | Search LHR to CDG, then use the filters and the sort box | The filters run in the browser, but the server still checks every value. With JavaScript off, the results still work. |
| 3. Book | Log in, open a flight, choose 2 passengers, type their names | Names are checked on the server (letters only, 40 characters). The price comes from the server, never the browser. |
| 4. Seats | Open the booking, click **Choose seats**, pick seats on the map | One seat can belong to one passenger. If two people choose the same seat at once, the database refuses the second one. |
| 5. Cancel | Cancel the booking, then open the seat page again | Cancelling frees the seats, and a cancelled booking cannot pick seats. |
| 6. Account | Open **My account** | You see your own recent security events. Changing the password needs the current one and is rate limited. |
| 7. Two-factor | Turn on two-factor login, scan the QR code, save the recovery codes, log out and log in again | The code follows RFC 6238. A code works once. Five wrong codes lock the account, like wrong passwords. |
| 8. Dashboard | Log in as admin and open the security dashboard | Password changes, two-factor changes and recovery-code use appear in the audit log. |
| 9. Migrations | Show `migrations/versions` and run `flask --app wsgi db current` | The structure of the database is versioned. An older database is brought up to date without losing data. |

## Likely questions

- **Why not store the two-factor secret encrypted?** It is a known limit (see SECURITY.md). A production system would encrypt it with a managed key; here it would need the same key stored beside it.
- **What if the phone is lost?** The person uses one of the recovery codes, which work once each, then makes new ones.
- **Why can the seat map not show other airlines' passengers?** The data only counts free seats, so sold seats outside SecurePass are placed by a fixed shuffle per flight. The map is stable but those seats are not real people.
- **How do you know a migration is safe?** Tests run it on a new database, an older database with flights in it, and one created by the app itself, and check that the result matches the models exactly.
