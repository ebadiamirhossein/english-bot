#!/usr/bin/env bash
# W1c — the restore drill. Pull the newest dump out of Cloudflare R2, rebuild a
# scratch database from it, and compare row counts against the live one.
#
# An untested backup is a hypothesis. Known issue #6 does not close because a
# file appears in a bucket; it closes because a database was rebuilt from that
# file and the numbers matched.
#
# Safe by construction: the target is a scratch database and the live one is
# refused outright. There is no --force here, unlike scripts/restore.sh — this
# script exists to be run casually and often, and a flag that can destroy the
# error journal does not belong in something you run casually.
#
#   ./scripts/restore_from_r2.sh              # drill: restore, count, drop
#   ./scripts/restore_from_r2.sh --keep       # leave the scratch DB for poking
#   ./scripts/restore_from_r2.sh --key K      # a specific object, not the newest
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
ENV_FILE="${ENV_FILE:-${REPO_ROOT}/.env}"

LIVE_DB_NAME="english_bot"
SCRATCH_DB="${SCRATCH_DB:-english_bot_restore_test}"
R2_PREFIX="english_bot"
# The tables the drill compares. `errors` first because it is the product
# (CLAUDE.md §5); the rest are what a restored database has to be usable.
VERIFY_TABLES="errors chunks users sessions"

KEEP_DB=0
WANT_KEY=""

usage() {
  cat <<EOF
Usage: $(basename "$0") [--keep] [--key <object-key>]

  --keep          Do not drop ${SCRATCH_DB} at the end.
  --key <key>     Restore this object instead of the newest one.

Reads DATABASE_URL and the five R2_* keys from ${ENV_FILE}
(real environment variables win, same precedence as scripts/backup.sh).
Never touches '${LIVE_DB_NAME}'.
EOF
}

die() {
  echo "ERROR: $*" >&2
  exit 1
}

require_cmd() {
  command -v "$1" >/dev/null 2>&1 || die "required command not found: $1"
}

# Same reader as scripts/backup.sh, and for the same reason: production
# configures through .env, so a script that only reads the process environment
# is a script that silently does nothing (known issue #26, CLAUDE.md §3 rule 3).
env_file_get() {
  local key="$1"
  local line raw
  [[ -f "${ENV_FILE}" ]] || return 1
  line="$(grep -E "^[[:space:]]*${key}=" "${ENV_FILE}" | tail -n1 || true)"
  [[ -n "${line}" ]] || return 1
  raw="${line#*=}"
  raw="${raw#"${raw%%[![:space:]]*}"}"
  if [[ "${raw}" == \"*\" ]]; then
    raw="${raw#\"}"
    raw="${raw%\"}"
  elif [[ "${raw}" == \'*\' ]]; then
    raw="${raw#\'}"
    raw="${raw%\'}"
  else
    if [[ "${raw}" == *" #"* ]]; then
      raw="${raw%% #*}"
    fi
    raw="${raw%"${raw##*[![:space:]]}"}"
  fi
  printf '%s' "${raw}"
  return 0
}

# Real environment wins; .env fills the rest.
load_key() {
  local name="$1" v
  if [[ -n "${!name:-}" ]]; then
    return 0
  fi
  v="$(env_file_get "${name}")" || return 0
  printf -v "${name}" '%s' "${v}"
}

load_config() {
  local name
  for name in DATABASE_URL R2_ACCOUNT_ID R2_BUCKET R2_ENDPOINT \
              R2_ACCESS_KEY_ID R2_SECRET_ACCESS_KEY; do
    printf -v "${name}" '%s' "${!name:-}"
    load_key "${name}"
  done
  [[ -n "${DATABASE_URL}" ]] || die "DATABASE_URL not set (env or ${ENV_FILE})"
  local missing=""
  for name in R2_ACCOUNT_ID R2_BUCKET R2_ENDPOINT R2_ACCESS_KEY_ID \
              R2_SECRET_ACCESS_KEY; do
    [[ -n "${!name}" ]] || missing="${missing}${name} "
  done
  [[ -z "${missing}" ]] || die "R2 not configured — missing: ${missing% }"
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
  SOURCE_DB_NAME="${db}"
}

# R2_SECRET_ACCESS_KEY lives in this command's environment and nowhere else.
# It is never echoed, never logged, never named in an error (CLAUDE.md §5).
r2_aws() {
  env -u AWS_SESSION_TOKEN -u AWS_PROFILE \
    AWS_ACCESS_KEY_ID="${R2_ACCESS_KEY_ID}" \
    AWS_SECRET_ACCESS_KEY="${R2_SECRET_ACCESS_KEY}" \
    AWS_DEFAULT_REGION="auto" \
    AWS_EC2_METADATA_DISABLED="true" \
    AWS_REQUEST_CHECKSUM_CALCULATION="when_required" \
    AWS_RESPONSE_CHECKSUM_VALIDATION="when_required" \
    aws --endpoint-url "${R2_ENDPOINT}" "$@"
}

newest_key() {
  # Sort by the key rather than by LastModified: the key carries the dump's own
  # date, which is the thing being restored, and it sorts chronologically
  # because the layout puts the date in fixed-width ISO form.
  r2_aws s3api list-objects-v2 \
    --bucket "${R2_BUCKET}" \
    --prefix "${R2_PREFIX}/" \
    --query 'Contents[].Key' \
    --output text \
    | tr '\t' '\n' \
    | grep -E "^${R2_PREFIX}/[0-9]{4}/[0-9]{2}/english_bot_[0-9]{4}-[0-9]{2}-[0-9]{2}_[0-9]{4}\.dump$" \
    | LC_ALL=C sort \
    | tail -n1
}

count_rows() {
  local db="$1" table="$2" out
  out="$(psql -d "${db}" -tAc \
    "SELECT count(*) FROM ${table}" 2>/dev/null)" || {
    echo "n/a"
    return 0
  }
  echo "${out}" | tr -d '[:space:]'
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    -h|--help) usage; exit 0 ;;
    --keep) KEEP_DB=1; shift ;;
    --key) WANT_KEY="${2:-}"; [[ -n "${WANT_KEY}" ]] || die "--key needs a value"; shift 2 ;;
    *) die "unknown argument: $1" ;;
  esac
done

[[ "${SCRATCH_DB}" != "${LIVE_DB_NAME}" ]] \
  || die "refusing to use '${LIVE_DB_NAME}' as the drill target"

require_cmd aws
require_cmd psql
require_cmd pg_restore
require_cmd createdb
require_cmd dropdb

load_config
parse_database_url

started_at="$(date '+%s')"
echo "Restore drill — $(date '+%Y-%m-%d %H:%M:%S %Z')"
echo "  bucket:  ${R2_BUCKET}"
echo "  server:  ${PGHOST}:${PGPORT}"
echo "  live DB: ${SOURCE_DB_NAME}"
echo "  scratch: ${SCRATCH_DB}"

key="${WANT_KEY}"
if [[ -z "${key}" ]]; then
  key="$(newest_key)" || die "could not list bucket ${R2_BUCKET}"
fi
[[ -n "${key}" ]] || die "no dump found under ${R2_PREFIX}/ in ${R2_BUCKET}"
echo "  object:  ${key}"

tmp_dir="$(mktemp -d)"
cleanup() {
  rm -rf "${tmp_dir}"
}
trap cleanup EXIT

dump_path="${tmp_dir}/$(basename "${key}")"
echo
echo "1/5 downloading…"
r2_aws s3 cp "s3://${R2_BUCKET}/${key}" "${dump_path}" --only-show-errors \
  || die "download failed for ${key}"
dump_size="$(wc -c < "${dump_path}" | tr -d ' ')"
echo "    ${dump_size} bytes"

echo "2/5 createdb ${SCRATCH_DB}…"
if psql -d postgres -tAc \
     "SELECT 1 FROM pg_database WHERE datname='${SCRATCH_DB}'" | grep -q 1; then
  dropdb --if-exists "${SCRATCH_DB}"
fi
createdb "${SCRATCH_DB}" || die "createdb failed"

echo "3/5 pg_restore…"
# --no-owner/--no-acl: role names differ between the Mac and the server, and a
# drill that fails on a role name has proved nothing about the data.
if ! pg_restore --dbname="${SCRATCH_DB}" --no-owner --no-acl "${dump_path}"; then
  die "pg_restore failed — ${SCRATCH_DB} left in place for inspection"
fi

echo "4/5 row counts (restored vs live)…"
printf '    %-12s %12s %12s   %s\n' "table" "restored" "live" ""
mismatch=0
for table in ${VERIFY_TABLES}; do
  restored="$(count_rows "${SCRATCH_DB}" "${table}")"
  live="$(count_rows "${SOURCE_DB_NAME}" "${table}")"
  verdict="match"
  if [[ "${restored}" == "n/a" ]]; then
    verdict="MISSING IN RESTORE"
    mismatch=1
  elif [[ "${live}" == "n/a" ]]; then
    verdict="no live table to compare"
  elif [[ "${restored}" != "${live}" ]]; then
    # Not automatically a failure: the dump is a point in time and the live
    # database has kept moving since 04:00. A restored count *higher* than
    # live is the one that cannot be explained that way.
    if [[ "${restored}" -gt "${live}" ]]; then
      verdict="RESTORED > LIVE — investigate"
      mismatch=1
    else
      verdict="behind live (dump predates today's writes)"
    fi
  fi
  printf '    %-12s %12s %12s   %s\n' "${table}" "${restored}" "${live}" "${verdict}"
done

echo "5/5 cleanup…"
if [[ "${KEEP_DB}" -eq 1 ]]; then
  echo "    kept ${SCRATCH_DB} (--keep)"
else
  dropdb --if-exists "${SCRATCH_DB}"
  echo "    dropped ${SCRATCH_DB}"
fi

elapsed=$(( $(date '+%s') - started_at ))
echo
if [[ "${mismatch}" -ne 0 ]]; then
  echo "DRILL FAILED after ${elapsed}s — see the table above."
  exit 1
fi
echo "DRILL PASSED in ${elapsed}s — ${key} restores and the counts are consistent."
