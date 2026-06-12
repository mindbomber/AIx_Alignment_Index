#!/usr/bin/env bash
set -euo pipefail

: "${PGHOST:?PGHOST is required}"
: "${PGUSER:?PGUSER is required}"
: "${PGDATABASE:?PGDATABASE is required}"

RESTORE_DATABASE="${RESTORE_DATABASE:-${PGDATABASE}_restore_drill}"
BACKUP_FILE="$(mktemp --suffix=.dump)"

cleanup() {
  rm -f "$BACKUP_FILE"
  dropdb --if-exists "$RESTORE_DATABASE" >/dev/null 2>&1 || true
}
trap cleanup EXIT

pg_dump --format=custom --file="$BACKUP_FILE" "$PGDATABASE"
dropdb --if-exists "$RESTORE_DATABASE"
createdb "$RESTORE_DATABASE"
pg_restore --exit-on-error --no-owner --dbname="$RESTORE_DATABASE" "$BACKUP_FILE"

version_count="$(
  psql --tuples-only --no-align --dbname="$RESTORE_DATABASE" \
    --command="select count(*) from alembic_version"
)"
table_count="$(
  psql --tuples-only --no-align --dbname="$RESTORE_DATABASE" \
    --command="select count(*) from information_schema.tables where table_schema='public'"
)"
organization_count="$(
  psql --tuples-only --no-align --dbname="$RESTORE_DATABASE" \
    --command="select count(*) from organizations"
)"
assessment_count="$(
  psql --tuples-only --no-align --dbname="$RESTORE_DATABASE" \
    --command="select count(*) from assessments"
)"

test "$version_count" = "1"
test "$table_count" -ge "10"
test "$organization_count" -ge "1"
test "$assessment_count" -ge "1"
echo "Restore drill passed: ${table_count} tables, ${organization_count} organizations, ${assessment_count} assessments."
