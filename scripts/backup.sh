#!/usr/bin/env bash
# S4b — daily pg_dump for the self-hosted English bot database.
# Runs from cron without the Python venv. See specs/S4b-backups.md.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
ENV_FILE="${REPO_ROOT}/.env"

BACKUP_DIR="${BACKUP_DIR:-${HOME}/english-bot-backups}"
KEEP_DAYS="${KEEP_DAYS:-14}"
MIN_BYTES="${MIN_BYTES:-10240}"  # 10 KB sanity floor
LIVE_DB_NAME="english_bot"

log() {
  local msg="$*"
  local ts
  ts="$(date '+%Y-%m-%d %H:%M:%S')"
  mkdir -p "${BACKUP_DIR}"
  echo "[${ts}] ${msg}" | tee -a "${BACKUP_DIR}/backup.log" >&2
}

die() {
  local msg="$*"
  local ts
  ts="$(date '+%Y-%m-%d %H:%M:%S')"
  # Never mkdir here — refuse-inside-repo must not create a path under the repo.
  echo "[${ts}] ERROR: ${msg}" >&2
  if [[ -d "${BACKUP_DIR}" ]]; then
    echo "[${ts}] ERROR: ${msg}" >> "${BACKUP_DIR}/backup.log" || true
  fi
  exit 1
}

require_cmd() {
  command -v "$1" >/dev/null 2>&1 || die "required command not found: $1"
}

# Resolve absolute path without requiring GNU realpath.
abspath() {
  local target="$1"
  if [[ -d "${target}" ]]; then
    (cd "${target}" && pwd -P)
  else
    local parent
    parent="$(cd "$(dirname "${target}")" && pwd -P)"
    echo "${parent}/$(basename "${target}")"
  fi
}

# Refuse dumps inside the git repo — they contain private writing (PRD §10).
assert_backup_dir_outside_repo() {
  local backup_abs repo_abs parent
  repo_abs="$(abspath "${REPO_ROOT}")"
  if [[ -d "${BACKUP_DIR}" ]]; then
    backup_abs="$(abspath "${BACKUP_DIR}")"
  else
    parent="$(dirname "${BACKUP_DIR}")"
    [[ -d "${parent}" ]] || die "BACKUP_DIR parent does not exist: ${parent}"
    backup_abs="$(abspath "${parent}")/$(basename "${BACKUP_DIR}")"
  fi
  case "${backup_abs}/" in
    "${repo_abs}"/*)
      die "BACKUP_DIR (${backup_abs}) is inside the git repo (${repo_abs}). Refuse to write dumps that could be committed (PRD §10)."
      ;;
  esac
}

load_database_url() {
  if [[ -n "${DATABASE_URL:-}" ]]; then
    log "Using DATABASE_URL from environment"
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

# Parse postgresql://[user[:password]@]host[:port]/dbname[?params]
# into PG* vars. Supports postgres:// as well.
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

  [[ -n "${db}" ]] || die "could not parse database name from DATABASE_URL"
  [[ -n "${host}" ]] || die "could not parse host from DATABASE_URL"

  export PGHOST="${host}"
  export PGPORT="${port}"
  export PGDATABASE="${db}"
  [[ -n "${user}" ]] && export PGUSER="${user}"
  if [[ -n "${password}" ]]; then
    export PGPASSWORD="${password}"
  fi

  log "Parsed DATABASE_URL → host=${PGHOST} port=${PGPORT} db=${PGDATABASE} user=${PGUSER:-"(default)"}"
}

# ---------------------------------------------------------------------------
# OFF-SITE COPY (stub) — weekly independent storage.
#
# Options when wiring this up (do not add credentials in this slice):
#   1. rsync to another host:  rsync -av "${BACKUP_DIR}/" user@offsite:/path/
#   2. rclone to object storage: rclone copy "${BACKUP_DIR}" remote:bucket/
#   3. Manual weekly copy of the newest .dump to offline media
#
# Call site below is intentional so automation is one function body away.
# ---------------------------------------------------------------------------
offsite_copy_stub() {
  local dump_path="$1"
  # Intentionally no-op. See BUILD_PROGRESS known issues — off-site not automated.
  log "OFFSITE STUB: skipped copy of $(basename "${dump_path}") (rsync / rclone / manual — not configured)"
}

prune_old_dumps() {
  # Only called after a successful dump. Never prune on failure.
  local cutoff
  cutoff="$(date -v-"${KEEP_DAYS}"d '+%Y-%m-%d' 2>/dev/null || date -d "${KEEP_DAYS} days ago" '+%Y-%m-%d')"
  log "Pruning dumps older than ${KEEP_DAYS} days (before ${cutoff})"
  local f base day
  shopt -s nullglob
  for f in "${BACKUP_DIR}"/english_bot_*.dump; do
    base="$(basename "${f}")"
    # english_bot_YYYY-MM-DD_HHMM.dump
    day="$(echo "${base}" | sed -n 's/^english_bot_\([0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]\)_.*/\1/p')"
    if [[ -n "${day}" && "${day}" < "${cutoff}" ]]; then
      log "Deleting old dump ${base}"
      rm -f "${f}"
    fi
  done
  shopt -u nullglob
}

main() {
  require_cmd pg_dump
  require_cmd tee
  assert_backup_dir_outside_repo
  load_database_url
  parse_database_url

  if [[ "${PGDATABASE}" != "${LIVE_DB_NAME}" ]]; then
    log "WARNING: dumping database '${PGDATABASE}' (expected '${LIVE_DB_NAME}')"
  fi

  local stamp outfile tmp
  stamp="$(date '+%Y-%m-%d_%H%M')"
  outfile="${BACKUP_DIR}/english_bot_${stamp}.dump"
  tmp="${outfile}.partial"

  log "Starting pg_dump → ${outfile}"
  if ! pg_dump -Fc -Z 9 -f "${tmp}" ; then
    rm -f "${tmp}"
    die "pg_dump failed"
  fi

  local size
  size="$(wc -c < "${tmp}" | tr -d ' ')"
  if [[ "${size}" -lt "${MIN_BYTES}" ]]; then
    rm -f "${tmp}"
    die "dump too small (${size} bytes < ${MIN_BYTES} sanity floor) — refusing to keep"
  fi

  mv "${tmp}" "${outfile}"
  log "SUCCESS dump=${outfile} size=${size} bytes"
  prune_old_dumps
  offsite_copy_stub "${outfile}"
  echo "${outfile}"
}

main "$@"
