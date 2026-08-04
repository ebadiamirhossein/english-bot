#!/usr/bin/env bash
# S4b — restore a pg_dump custom-format file into a target database.
# Defaults to a scratch DB so a careless run cannot destroy production.
# See specs/S4b-backups.md.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
ENV_FILE="${REPO_ROOT}/.env"

LIVE_DB_NAME="english_bot"
DEFAULT_TARGET="english_bot_restore_test"

usage() {
  cat <<EOF
Usage: $(basename "$0") <dump-file> [target-db] [--force]

  dump-file   Path to a pg_dump -Fc file (required).
  target-db   Database to restore into (default: ${DEFAULT_TARGET}).
  --force     Required if target-db is ${LIVE_DB_NAME}.

Connection details are read from DATABASE_URL in ${ENV_FILE}
(host/port/user only — the database name in the URL is ignored; target-db wins).
EOF
}

die() {
  echo "ERROR: $*" >&2
  exit 1
}

require_cmd() {
  command -v "$1" >/dev/null 2>&1 || die "required command not found: $1"
}

load_database_url() {
  if [[ -n "${DATABASE_URL:-}" ]]; then
    return
  fi
  [[ -f "${ENV_FILE}" ]] || die ".env not found at ${ENV_FILE}"
  local line
  line="$(grep -E '^[[:space:]]*DATABASE_URL=' "${ENV_FILE}" | tail -n1 || true)"
  [[ -n "${line}" ]] || die "DATABASE_URL not set in ${ENV_FILE}"
  DATABASE_URL="${line#*=}"
  DATABASE_URL="${DATABASE_URL%\"}"
  DATABASE_URL="${DATABASE_URL#\"}"
  DATABASE_URL="${DATABASE_URL%\'}"
  DATABASE_URL="${DATABASE_URL#\'}"
  [[ -n "${DATABASE_URL}" ]] || die "DATABASE_URL is empty"
}

parse_database_url() {
  local url="${DATABASE_URL}"
  url="${url#postgresql://}"
  url="${url#postgres://}"

  local creds hostport db
  if [[ "${url}" == *"@"* ]]; then
    creds="${url%%@*}"
    url="${url#*@}"
  else
    creds=""
  fi
  db="${url##*/}"
  db="${db%%\?*}"
  hostport="${url%/${db}}"
  hostport="${hostport%%\?*}"

  local user="" password=""
  if [[ -n "${creds}" ]]; then
    user="${creds%%:*}"
    if [[ "${creds}" == *":"* ]]; then
      password="${creds#*:}"
    fi
  fi

  local host="${hostport}"
  local port="5432"
  if [[ "${hostport}" == *":"* ]]; then
    host="${hostport%%:*}"
    port="${hostport##*:}"
  fi

  [[ -n "${host}" ]] || die "could not parse host from DATABASE_URL"

  export PGHOST="${host}"
  export PGPORT="${port}"
  [[ -n "${user}" ]] && export PGUSER="${user}"
  if [[ -n "${password}" ]]; then
    export PGPASSWORD="${password}"
  fi
  # Remember live DB name from URL for messaging only.
  SOURCE_DB_NAME="${db}"
}

DUMP_FILE=""
TARGET_DB="${DEFAULT_TARGET}"
FORCE=0

while [[ $# -gt 0 ]]; do
  case "$1" in
    -h|--help)
      usage
      exit 0
      ;;
    --force)
      FORCE=1
      shift
      ;;
    -*)
      die "unknown option: $1"
      ;;
    *)
      if [[ -z "${DUMP_FILE}" ]]; then
        DUMP_FILE="$1"
      else
        TARGET_DB="$1"
      fi
      shift
      ;;
  esac
done

[[ -n "${DUMP_FILE}" ]] || { usage; die "dump-file is required"; }
[[ -f "${DUMP_FILE}" ]] || die "dump file not found: ${DUMP_FILE}"

if [[ "${TARGET_DB}" == "${LIVE_DB_NAME}" && "${FORCE}" -ne 1 ]]; then
  die "refusing to restore into live database '${LIVE_DB_NAME}' without --force"
fi

require_cmd psql
require_cmd pg_restore
require_cmd createdb
require_cmd dropdb

load_database_url
parse_database_url

echo "Restoring $(basename "${DUMP_FILE}") → database '${TARGET_DB}' on ${PGHOST}:${PGPORT}"

# Drop scratch target if it already exists (safe for the default name).
if psql -d postgres -tAc "SELECT 1 FROM pg_database WHERE datname='${TARGET_DB}'" | grep -q 1; then
  if [[ "${TARGET_DB}" == "${LIVE_DB_NAME}" ]]; then
    echo "Dropping existing live database '${TARGET_DB}' (--force was given)..."
  else
    echo "Dropping existing scratch database '${TARGET_DB}'..."
  fi
  dropdb --if-exists "${TARGET_DB}"
fi

createdb "${TARGET_DB}"
# --no-owner/--no-acl: local role names may differ between machines.
pg_restore --dbname="${TARGET_DB}" --no-owner --no-acl "${DUMP_FILE}" \
  || die "pg_restore failed (database '${TARGET_DB}' left in place for inspection)"

echo "SUCCESS: restored into '${TARGET_DB}'"
echo "Verify with:"
echo "  psql -p ${PGPORT} ${TARGET_DB} -c \"SELECT count(*) FROM errors;\""
echo "  psql -p ${PGPORT} ${TARGET_DB} -c \"SELECT count(*) FROM error_types;\""
