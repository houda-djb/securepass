# Database and migrations

SecurePass uses SQLite through SQLAlchemy. The tables are described by the classes in
`app/models.py`. When the models change after a database already exists, the change is
recorded in a **migration** (a small script in `migrations/versions/`) so that every
database, new or old, can be brought up to date with one command.

## Everyday commands

| Task | Command |
| --- | --- |
| Bring a database up to date | `flask --app wsgi db upgrade` |
| See which version a database is at | `flask --app wsgi db current` |
| Record a model change | `flask --app wsgi db migrate -m "what changed"` |
| Undo the latest migration | `flask --app wsgi db downgrade` |
| Start over with fresh demo data | `flask --app wsgi reset-db` |

After `db migrate`, open the new file in `migrations/versions/` and read it before
committing: automatic detection is a draft, not a promise.

## History

| Version | What it adds |
| --- | --- |
| `0001` | Every table up to passenger names and seat choices. Creates only the tables that are missing. |
| `0002` | The `airlines` table and the optional `flights.airline_code` column. Gives existing demo flights (SP100 to SP125) the same carrier a fresh database would. |

Both migrations check what already exists before changing anything. The application also
creates missing tables when it starts, so a database may be partly up to date already;
running `db upgrade` is always safe.

## Why `reset-db` is not enough in real life

`reset-db` deletes accounts and bookings. Migrations change the structure and keep the data,
which is what a live system needs.

## PostgreSQL

Production uses PostgreSQL. Set `DATABASE_URL` to `postgresql://user:password@host/dbname`; the app rewrites the
prefix to `postgresql+psycopg://` itself, so addresses handed out by hosting services work unchanged. Without
`DATABASE_URL` the app keeps using a local SQLite file, which is the quickest way to run it on a laptop.

The same migrations (`flask --app wsgi db upgrade`) build both databases, and continuous integration runs the whole
test suite on both. See `docs/DEPLOYMENT.md` for running, deploying and backing up.
