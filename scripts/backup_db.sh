#!/bin/sh
# Saves a full copy of the PostgreSQL database to a file you can restore later.
#
#   DATABASE_URL="postgresql://user:password@host/dbname" sh scripts/backup_db.sh
#
# On Render use the database's EXTERNAL address, and note that the free database only accepts
# outside connections if you allow your IP address in its settings. Keep the backup file private:
# it contains every account (password hashes) and booking.
set -eu

if [ -z "${DATABASE_URL:-}" ]; then
    echo "Set DATABASE_URL first (see the comment at the top of this file)." >&2
    exit 1
fi

file="securepass-backup-$(date +%Y%m%d-%H%M%S).dump"
pg_dump "$DATABASE_URL" --format=custom --no-owner --no-privileges --file="$file"
chmod 600 "$file"
echo "Saved $file"
echo "Restore with: pg_restore --clean --if-exists --no-owner --dbname \"\$NEW_DATABASE_URL\" $file"
