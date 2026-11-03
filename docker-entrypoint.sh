#!/bin/sh
# Starts SecurePass in a container: bring the database up to date, add any missing demo data,
# then run the web server. "set -e" stops everything if a step fails, so a broken database is
# never served.
set -e

flask --app wsgi db upgrade
flask --app wsgi seed
# Creates the first admin from ADMIN_EMAIL / ADMIN_PASSWORD when no admin exists yet (does nothing otherwise).
flask --app wsgi bootstrap-admin

# One worker with several threads: the rate limits live in this process's memory (see
# docs/DEPLOYMENT.md). X-Forwarded-* headers are handled by the app itself (PROXY_HOPS).
exec gunicorn wsgi:app \
    --bind "0.0.0.0:${PORT:-8000}" \
    --workers "${WEB_CONCURRENCY:-1}" \
    --threads 4 \
    --timeout 30 \
    --access-logfile -
