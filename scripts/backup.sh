#!/usr/bin/env bash
# S4b/S4c — daily pg_dump + optional verified off-site copy.
# Runs from cron without the Python venv. See specs/S4b-backups.md + BUILD_PROGRESS S4c.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
ENV_FILE="${REPO_ROOT}/.env"

BACKUP_DIR="${BACKUP_DIR:-${HOME}/english-bot-backups}"
KEEP_DAYS="${KEEP_DAYS:-14}"
MIN_BYTES="${MIN_BYTES:-10240}"  # 10 KB sanity floor
LIVE_DB_NAME="english_bot"
# S4c — empty means skip off-site entirely (silent).
BACKUP_OFFSITE_DIR="${BACKUP_OFFSITE_DIR:-}"
BACKUP_OFFSITE_KEEP="${BACKUP_OFFSITE_KEEP:-14}"

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
# path may not exist yet; parent must.
assert_path_outside_repo() {
  local path="$1"
  local label="$2"
  local path_abs repo_abs parent
  repo_abs="$(abspath "${REPO_ROOT}")"
  if [[ -d "${path}" ]]; then
    path_abs="$(abspath "${path}")"
  else
    parent="$(dirname "${path}")"
    [[ -d "${parent}" ]] || die "${label} parent does not exist: ${parent}"
    path_abs="$(abspath "${parent}")/$(basename "${path}")"
  fi
  case "${path_abs}/" in
    "${repo_abs}"/*)
      die "${label} (${path_abs}) is inside the git repo (${repo_abs}). Refuse to write dumps that could be committed (PRD §10)."
      ;;
  esac
}

assert_backup_dir_outside_repo() {
  assert_path_outside_repo "${BACKUP_DIR}" "BACKUP_DIR"
}

# Same-disk copy under BACKUP_DIR is not off-site — refuse loudly.
assert_offsite_not_inside_backup() {
  local offsite_abs backup_abs parent
  if [[ -d "${BACKUP_OFFSITE_DIR}" ]]; then
    offsite_abs="$(abspath "${BACKUP_OFFSITE_DIR}")"
  else
    parent="$(dirname "${BACKUP_OFFSITE_DIR}")"
    if [[ -d "${parent}" ]]; then
      offsite_abs="$(abspath "${parent}")/$(basename "${BACKUP_OFFSITE_DIR}")"
    else
      # Existence check happens later; still resolve what we can for the nest check
      # when parent is missing we cannot nest under BACKUP_DIR usefully — skip nest.
      return 0
    fi
  fi
  if [[ -d "${BACKUP_DIR}" ]]; then
    backup_abs="$(abspath "${BACKUP_DIR}")"
  else
    parent="$(dirname "${BACKUP_DIR}")"
    [[ -d "${parent}" ]] || return 0
    backup_abs="$(abspath "${parent}")/$(basename "${BACKUP_DIR}")"
  fi
  if [[ "${offsite_abs}" == "${backup_abs}" ]]; then
    die "BACKUP_OFFSITE_DIR (${offsite_abs}) must not equal BACKUP_DIR (${backup_abs}) — same folder is not off-site."
  fi
  case "${offsite_abs}/" in
    "${backup_abs}"/*)
      die "BACKUP_OFFSITE_DIR (${offsite_abs}) is inside BACKUP_DIR (${backup_abs}). Same-disk tree is false confidence, not off-site."
      ;;
  esac
}

file_sha256() {
  local path="$1"
  if command -v shasum >/dev/null 2>&1; then
    shasum -a 256 "${path}" | awk '{print $1}'
  elif command -v sha256sum >/dev/null 2>&1; then
    sha256sum "${path}" | awk '{print $1}'
  else
    die "required command not found: shasum or sha256sum"
  fi
}

# Canonical stamp key for retention sort: english_bot_YYYY-MM-DD_HHMM.dump
offsite_stamp_key() {
  local base="$1"
  # .english_bot_....dump.icloud → english_bot_....dump
  base="${base#.}"
  base="${base%.icloud}"
  echo "${base}"
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

clean_stale_partials() {
  local dir="$1"
  local f
  shopt -s nullglob
  for f in "${dir}"/english_bot_*.dump.partial; do
    log "Removing stale partial $(basename "${f}")"
    rm -f "${f}"
  done
  shopt -u nullglob
}

prune_offsite_dumps() {
  # Only called after a successful verified off-site copy. Never prune on failure.
  local keep="${BACKUP_OFFSITE_KEEP}"
  local -a entries=()
  local f base key
  shopt -s nullglob
  for f in "${BACKUP_OFFSITE_DIR}"/english_bot_*.dump \
           "${BACKUP_OFFSITE_DIR}"/.english_bot_*.dump.icloud; do
    [[ -e "${f}" ]] || continue
    base="$(basename "${f}")"
    key="$(offsite_stamp_key "${base}")"
    entries+=("${key}|${f}")
  done
  shopt -u nullglob

  local count="${#entries[@]}"
  if [[ "${count}" -le "${keep}" ]]; then
    log "Off-site retention: ${count} copies (keep ${keep}) — nothing to prune"
    return
  fi

  # Sort by stamp key descending (newest first); delete from index keep onward.
  local sorted
  sorted="$(printf '%s\n' "${entries[@]}" | LC_ALL=C sort -r)"
  local i=0
  local line path
  while IFS= read -r line; do
    [[ -n "${line}" ]] || continue
    path="${line#*|}"
    if [[ "${i}" -ge "${keep}" ]]; then
      log "Deleting old off-site copy $(basename "${path}")"
      rm -f "${path}"
    fi
    i=$((i + 1))
  done <<< "${sorted}"
}

# ---------------------------------------------------------------------------
# OFF-SITE COPY (S4c) — verified copy to independent storage.
#
# Destination options (no credentials in this repo):
#   1. Cloud-synced folder (iCloud / Dropbox / Google Drive) — script writes;
#      sync client transfers. iCloud "Optimise Mac Storage" may replace dumps
#      with .english_bot_*.dump.icloud placeholders (healthy; counted present).
#   2. rsync to another host:  rsync -av "${BACKUP_DIR}/" user@offsite:/path/
#   3. rclone to object storage: rclone copy "${BACKUP_DIR}" remote:bucket/
# ---------------------------------------------------------------------------
offsite_copy() {
  local dump_path="$1"
  local dump_base dest partial size src_hash dest_hash

  if [[ -z "${BACKUP_OFFSITE_DIR}" ]]; then
    return 0
  fi

  assert_path_outside_repo "${BACKUP_OFFSITE_DIR}" "BACKUP_OFFSITE_DIR"
  assert_offsite_not_inside_backup

  [[ -d "${BACKUP_OFFSITE_DIR}" ]] || die "BACKUP_OFFSITE_DIR does not exist (not mounted / not synced?): ${BACKUP_OFFSITE_DIR}"
  [[ -w "${BACKUP_OFFSITE_DIR}" ]] || die "BACKUP_OFFSITE_DIR is not writable: ${BACKUP_OFFSITE_DIR}"

  clean_stale_partials "${BACKUP_OFFSITE_DIR}"

  dump_base="$(basename "${dump_path}")"
  dest="${BACKUP_OFFSITE_DIR}/${dump_base}"
  partial="${dest}.partial"

  log "Off-site copy → ${dest}"
  if ! cp "${dump_path}" "${partial}"; then
    rm -f "${partial}"
    die "off-site cp failed"
  fi

  size="$(wc -c < "${partial}" | tr -d ' ')"
  local src_size
  src_size="$(wc -c < "${dump_path}" | tr -d ' ')"
  if [[ "${size}" != "${src_size}" ]]; then
    rm -f "${partial}"
    die "off-site copy size mismatch (src=${src_size} dest=${size}) — refusing"
  fi

  src_hash="$(file_sha256 "${dump_path}")"
  dest_hash="$(file_sha256 "${partial}")"
  if [[ "${src_hash}" != "${dest_hash}" ]]; then
    rm -f "${partial}"
    die "off-site copy checksum mismatch — refusing"
  fi

  mv "${partial}" "${dest}"
  log "OFFSITE SUCCESS dump=${dest} size=${size} bytes sha256=${src_hash}"
  prune_offsite_dumps
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
  offsite_copy "${outfile}"
  echo "${outfile}"
}

if [[ "${BASH_SOURCE[0]}" == "$0" ]]; then
  main "$@"
fi
