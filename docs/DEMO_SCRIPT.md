# Demo script (about 10 minutes)

A walk through SecurePass that shows the features and the security controls, in the order
that tells the best story. Each step names the requirement it proves.

## Before you start

```powershell
pytest -q --cov=app --cov-fail-under=90      # everything green, coverage above 90 percent
bandit -r app config.py -ll                  # no issues
flask --app wsgi reset-db                    # fresh demo data (type y)
flask --app wsgi create-admin                # make the admin account
flask --app wsgi security-scan               # fills the scan panel on the dashboard
flask --app wsgi run --debug
```

Open two browser windows: a normal one for the **admin** and a private one for the **visitor**.
Have the GitHub Actions page and the closed "insecure commit" pull request ready in a third tab.

## The story

| # | Do this | Say this | Proves |
|---|---|---|---|
| 1 | Show the homepage, then search `LHR` to `CDG` with a return date | "Server-rendered pages, validated search, outbound and return flights." | FR5, FR6 |
| 2 | Search with `L1` and yesterday's date | "The server validates everything. The browser checks are only a convenience." | SR3 |
| 3 | Register a visitor account with a short password, then a good one | "Password rules, and the password is stored only as a salted hash." | FR1, SR1 |
| 4 | Log in, open a flight, book 2 seats, read the demo-payment note | "No card data is ever collected. The server works out the price." | FR9, FR14 |
| 5 | Show the booking reference, then **My Bookings** | "The reference is random, not a row number." | FR10, FR11 |
| 6 | Cancel the booking, then show the seat count on the flight page | "Cancelling twice can only return the seats once." | FR12, NFR5 |
| 7 | Log in as a second visitor and open the first visitor's booking address | "It looks like it doesn't exist. The attempt is logged." | SR6, AC2 |
| 8 | Try `/admin/` as a normal visitor | "Server-side check: 403, and it is logged." | SR5, AC1 |
| 9 | Enter a wrong password 5 times, then the right one | "Lockout, and the message never says which emails exist." | FR3, AC4 |
| 10 | In the admin window, open **Admin**: show the failed-login count, the locked account, the chart and the event table | "Everything the visitor just did is evidence here." | FR17 to FR20, AC7 |
| 11 | Click **Unlock** | "Admins can recover an account, and that action is logged too." | FR18 |
| 12 | Open **Flights**: add a flight, edit its price, try to delete a flight that has a booking | "Admin rules protect existing bookings." | FR15 |
| 13 | Point at the scan panel | "The latest Bandit and pip-audit results." | FR21 |
| 14 | Show the GitHub Actions run and the red-cross pull request | "An insecure commit cannot be merged." | AC6, TR5, TR8 |
| 15 | Open the browser developer tools, Network tab, and show the response headers | "CSP, frame protection, no sniffing, no caching of private pages." | SR9 |

## Questions you may be asked

**How do you stop two people booking the last seat?** One conditional `UPDATE ... WHERE seats >= n`.
The database does the check and the subtract in a single step, and the booking is saved in the
same transaction. A test runs two real database connections at the same moment.

**Why not store the card number?** It would bring the whole project into payment-card rules
(PCI DSS) for no benefit in a demo. Production would hand the card to a payment provider.

**What stops someone changing the price in the browser?** The price is not in the form. The server
reads it from the flight and works out the total itself.

**What if the secret key leaks?** It lives in an environment variable, never in the repository, and
a test checks the code for secret patterns. Production refuses to start with a weak key.

**What is not covered?** Two-factor authentication, password reset, email verification, alerting and
tamper-evident logs. They are listed under future work.

## If something goes wrong

| Problem | Fix |
|---|---|
| The login is locked from practice runs | Admin dashboard, **Unlock** |
| The data looks messy | `flask --app wsgi reset-db`, then `create-admin` again |
| The scan panel is empty | `flask --app wsgi security-scan` (needs the internet for pip-audit) |
| A page looks unstyled | Press Ctrl+F5. The fonts need the internet. |