#!/usr/bin/env bash
# S4b/S4c — daily pg_dump + optional verified off-site copy.
# Runs from cron without the Python venv. See specs/S4b-backups.md + BUILD_PROGRESS S4c.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
# Override for tests; production uses repo-root .env.
ENV_FILE="${ENV_FILE:-${REPO_ROOT}/.env}"

KEEP_DAYS="${KEEP_DAYS:-14}"
MIN_BYTES="${MIN_BYTES:-10240}"  # 10 KB sanity floor
LIVE_DB_NAME="english_bot"

# Track which backup keys the real environment already provided (even if empty).
# Real env wins over .env; unset → fall through to .env → defaults.
#
# Known issue #26: BACKUP_DIR and BACKUP_OFFSITE_DIR used to be read from the
# process environment only, so configuring them in .env — the only way they are
# really configured — looked "unset" and the copy silently skipped. Every key
# below, including the five R2 ones, goes through env_file_get for that reason
# (CLAUDE.md §3 rule 3).
_ENV_HAS_BACKUP_DIR="${BACKUP_DIR+y}"
_ENV_HAS_BACKUP_OFFSITE_DIR="${BACKUP_OFFSITE_DIR+y}"
_ENV_HAS_BACKUP_OFFSITE_KEEP="${BACKUP_OFFSITE_KEEP+y}"
_ENV_HAS_R2_ACCOUNT_ID="${R2_ACCOUNT_ID+y}"
_ENV_HAS_R2_BUCKET="${R2_BUCKET+y}"
_ENV_HAS_R2_ENDPOINT="${R2_ENDPOINT+y}"
_ENV_HAS_R2_ACCESS_KEY_ID="${R2_ACCESS_KEY_ID+y}"
_ENV_HAS_R2_SECRET_ACCESS_KEY="${R2_SECRET_ACCESS_KEY+y}"
BACKUP_DIR="${BACKUP_DIR:-}"
# S4c — empty means skip off-site (INFO line, not silent).
BACKUP_OFFSITE_DIR="${BACKUP_OFFSITE_DIR:-}"
BACKUP_OFFSITE_KEEP="${BACKUP_OFFSITE_KEEP:-}"
# W1c — Cloudflare R2. All five empty means skip the R2 copy (INFO line).
# Any other combination is a configuration mistake and dies loudly.
R2_ACCOUNT_ID="${R2_ACCOUNT_ID:-}"
R2_BUCKET="${R2_BUCKET:-}"
R2_ENDPOINT="${R2_ENDPOINT:-}"
R2_ACCESS_KEY_ID="${R2_ACCESS_KEY_ID:-}"
R2_SECRET_ACCESS_KEY="${R2_SECRET_ACCESS_KEY:-}"
# Object key layout: english_bot/<YYYY>/<MM>/english_bot_<date>_<HHMM>.dump
# Not configurable: the freshness check in packages/core reads the same prefix,
# and two places that must agree should not be two variables to keep in step.
R2_PREFIX="english_bot"
# The five key names, in one place, so the "all set / none set / some set"
# check and the .env loader cannot drift apart.
R2_KEYS="R2_ACCOUNT_ID R2_BUCKET R2_ENDPOINT R2_ACCESS_KEY_ID R2_SECRET_ACCESS_KEY"

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

# Read KEY from ENV_FILE. Last matching assignment wins. Handles quoted and
# unquoted values (unquoted may contain spaces — full rest of line after =).
# Ignores blank lines and full-line comments. Returns 1 if key absent/empty file.
env_file_get() {
  local key="$1"
  local line raw
  [[ -f "${ENV_FILE}" ]] || return 1
  line="$(grep -E "^[[:space:]]*${key}=" "${ENV_FILE}" | tail -n1 || true)"
  [[ -n "${line}" ]] || return 1
  raw="${line#*=}"
  # Trim leading whitespace.
  raw="${raw#"${raw%%[![:space:]]*}"}"
  if [[ "${raw}" == \"*\" ]]; then
    raw="${raw#\"}"
    raw="${raw%\"}"
  elif [[ "${raw}" == \'*\' ]]; then
    raw="${raw#\'}"
    raw="${raw%\'}"
  else
    # Unquoted: strip trailing inline comment (" # …") and trailing whitespace.
    if [[ "${raw}" == *" #"* ]]; then
      raw="${raw%% #*}"
    fi
    raw="${raw%"${raw##*[![:space:]]}"}"
  fi
  printf '%s' "${raw}"
  return 0
}

# Set variable $1 from ENV_FILE unless the real environment already had it ($2
# is "y" when it did). printf -v rather than `declare -g` — the latter is bash
# 4.2+ and this script also has to run under macOS's /bin/bash 3.2.
_dotenv_fill() {
  local name="$1" had="$2" v
  [[ -z "${had}" ]] || return 0
  v="$(env_file_get "${name}")" || return 0
  [[ -n "${v}" ]] || return 0
  printf -v "${name}" '%s' "${v}"
}

# Fill BACKUP_DIR / BACKUP_OFFSITE_* from .env when not set in the real environment.
# Precedence: real env → .env → defaults. Call before any use of BACKUP_DIR.
apply_dotenv_backup_vars() {
  local v
  if [[ -z "${_ENV_HAS_BACKUP_DIR}" ]]; then
    if v="$(env_file_get BACKUP_DIR)" && [[ -n "${v}" ]]; then
      BACKUP_DIR="${v}"
    fi
  fi
  if [[ -z "${_ENV_HAS_BACKUP_OFFSITE_DIR}" ]]; then
    if v="$(env_file_get BACKUP_OFFSITE_DIR)"; then
      BACKUP_OFFSITE_DIR="${v}"
    fi
  fi
  if [[ -z "${_ENV_HAS_BACKUP_OFFSITE_KEEP}" ]]; then
    if v="$(env_file_get BACKUP_OFFSITE_KEEP)" && [[ -n "${v}" ]]; then
      BACKUP_OFFSITE_KEEP="${v}"
    fi
  fi
  _dotenv_fill R2_ACCOUNT_ID "${_ENV_HAS_R2_ACCOUNT_ID}"
  _dotenv_fill R2_BUCKET "${_ENV_HAS_R2_BUCKET}"
  _dotenv_fill R2_ENDPOINT "${_ENV_HAS_R2_ENDPOINT}"
  _dotenv_fill R2_ACCESS_KEY_ID "${_ENV_HAS_R2_ACCESS_KEY_ID}"
  _dotenv_fill R2_SECRET_ACCESS_KEY "${_ENV_HAS_R2_SECRET_ACCESS_KEY}"
  BACKUP_DIR="${BACKUP_DIR:-${HOME}/english-bot-backups}"
  BACKUP_OFFSITE_DIR="${BACKUP_OFFSITE_DIR:-}"
  BACKUP_OFFSITE_KEEP="${BACKUP_OFFSITE_KEEP:-14}"
}

load_database_url() {
  if [[ -n "${DATABASE_URL:-}" ]]; then
    log "Using DATABASE_URL from environment"
    return
  fi
  [[ -f "${ENV_FILE}" ]] || die ".env not found at ${ENV_FILE}"
  local value
  value="$(env_file_get DATABASE_URL)" || die "DATABASE_URL not set in ${ENV_FILE}"
  DATABASE_URL="${value}"
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
    log "off-site copy skipped (BACKUP_OFFSITE_DIR not set)"
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

# ---------------------------------------------------------------------------
# CLOUDFLARE R2 (W1c) — the real off-site copy. Closes known issue #6.
#
# Tool: AWS CLI v2 with --endpoint-url. R2 speaks S3, the CLI is a shell tool
# for a shell concern, and it adds nothing to requirements.txt — this script
# runs from cron without the venv, so a boto3 import would have meant giving it
# one. Install: `apt install awscli` on Ubuntu 24.04 (2.x) or the official
# installer; `brew install awscli` on the Mac.
#
# R2_SECRET_ACCESS_KEY is passed to `aws` in that command's own environment and
# is never echoed, logged, or named in an error message (CLAUDE.md §5).
# ---------------------------------------------------------------------------

# How many of the five keys are set. 0 = skip; 5 = go; anything between is a
# configuration mistake that must never be allowed to look like "skip".
r2_set_count() {
  local name count=0
  for name in ${R2_KEYS}; do
    [[ -n "${!name}" ]] && count=$((count + 1))
  done
  echo "${count}"
}

# Names of the unset keys, space separated. Names only — never values.
r2_missing_keys() {
  local name out=""
  for name in ${R2_KEYS}; do
    [[ -n "${!name}" ]] || out="${out}${name} "
  done
  printf '%s' "${out% }"
}

# Run `aws` against R2. Credentials exist only in this command's environment.
# AWS_*_CHECKSUM_*=when_required: aws-cli v2.23+ adds full-object checksums by
# default, which R2 rejects on some upload paths; "when_required" is the
# setting Cloudflare documents for S3-compatible clients.
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

# english_bot_2026-08-23_0400.dump → english_bot/2026/08/english_bot_2026-08-23_0400.dump
# Dated prefixes so a human browsing the bucket can find one day without
# listing everything.
r2_object_key() {
  local base="$1" day year month
  day="$(echo "${base}" | sed -n 's/^english_bot_\([0-9]\{4\}-[0-9]\{2\}-[0-9]\{2\}\)_[0-9][0-9][0-9][0-9]\.dump$/\1/p')"
  [[ -n "${day}" ]] || return 1
  year="${day%%-*}"
  month="${day#*-}"
  month="${month%%-*}"
  printf '%s/%s/%s/%s' "${R2_PREFIX}" "${year}" "${month}" "${base}"
}

# Date embedded in a canonical object key, or non-zero if the key is not one
# this script wrote. Retention reads the dump's own date, not LastModified:
# the date is what the retention policy is about, and it is testable offline.
r2_key_date() {
  local key="$1" base day
  case "${key}" in
    "${R2_PREFIX}"/[0-9][0-9][0-9][0-9]/[0-9][0-9]/english_bot_*.dump) ;;
    *) return 1 ;;
  esac
  base="${key##*/}"
  day="$(echo "${base}" | sed -n 's/^english_bot_\([0-9]\{4\}-[0-9]\{2\}-[0-9]\{2\}\)_[0-9][0-9][0-9][0-9]\.dump$/\1/p')"
  [[ -n "${day}" ]] || return 1
  printf '%s' "${day}"
}

# Read object keys on stdin, one per line; print the keys to delete.
#
# Pure: no network, no filesystem, no clock. Two rules, both deliberate:
#   * only keys matching the canonical layout are ever candidates — an object
#     this script did not write is never deleted by it;
#   * the newest key always survives, whatever its age. If uploads have been
#     broken for a month, the one surviving dump must not be deleted by its
#     own retention rule.
r2_prune_plan() {
  local cutoff="$1"
  local line day key sorted first=1
  local -a entries=()
  # `|| [[ -n "${line}" ]]` so a final line with no trailing newline is not
  # silently dropped — a listing that ends without one is not a shorter listing.
  while IFS= read -r line || [[ -n "${line}" ]]; do
    line="${line%$'\r'}"
    [[ -n "${line}" ]] || continue
    day="$(r2_key_date "${line}")" || continue
    entries+=("${day}|${line}")
  done
  [[ "${#entries[@]}" -gt 0 ]] || return 0
  # Descending: the dump date leads each entry, and same-day dumps then order
  # by the HHMM inside the key.
  sorted="$(printf '%s\n' "${entries[@]}" | LC_ALL=C sort -r)"
  while IFS= read -r line; do
    [[ -n "${line}" ]] || continue
    day="${line%%|*}"
    key="${line#*|}"
    if [[ "${first}" == "1" ]]; then
      first=0
      continue
    fi
    if [[ "${day}" < "${cutoff}" ]]; then
      printf '%s\n' "${key}"
    fi
  done <<< "${sorted}"
}

r2_list_keys() {
  r2_aws s3api list-objects-v2 \
    --bucket "${R2_BUCKET}" \
    --prefix "${R2_PREFIX}/" \
    --query 'Contents[].Key' \
    --output text | tr '\t' '\n'
}

# Only ever called after a verified upload. Never before, never on failure:
# pruning on a failed run is how you end up with neither an old copy nor a new
# one.
r2_prune() {
  local cutoff keys plan key deleted=0
  cutoff="$(date -v-"${KEEP_DAYS}"d '+%Y-%m-%d' 2>/dev/null || date -d "${KEEP_DAYS} days ago" '+%Y-%m-%d')"
  log "R2 retention: removing objects dated before ${cutoff} (keep ${KEEP_DAYS} days; newest always survives)"
  keys="$(r2_list_keys)" || die "R2 list-objects-v2 failed — retention not applied"
  plan="$(printf '%s\n' "${keys}" | r2_prune_plan "${cutoff}")"
  while IFS= read -r key; do
    [[ -n "${key}" ]] || continue
    log "R2 retention: deleting ${key}"
    r2_aws s3api delete-object --bucket "${R2_BUCKET}" --key "${key}" >/dev/null \
      || die "R2 delete-object failed for ${key}"
    deleted=$((deleted + 1))
  done <<< "${plan}"
  log "R2 retention: ${deleted} object(s) deleted"
}

# Upload the dump the local step just produced. A second copy, never a
# replacement: the local dump stays where it is whatever happens here.
r2_upload() {
  local dump_path="$1"
  local set_count base key local_size remote_size

  set_count="$(r2_set_count)"
  if [[ "${set_count}" == "0" ]]; then
    log "R2 copy skipped (R2_* not configured) — local dump kept at ${dump_path}"
    return 0
  fi
  if [[ "${set_count}" != "5" ]]; then
    die "R2 partially configured — missing: $(r2_missing_keys). All five keys or none; a half-set R2 is exactly the silent skip known issue #26 was written about."
  fi
  require_cmd aws

  base="$(basename "${dump_path}")"
  key="$(r2_object_key "${base}")" \
    || die "dump name is not english_bot_YYYY-MM-DD_HHMM.dump: ${base}"

  log "R2 upload → s3://${R2_BUCKET}/${key}"
  if ! r2_aws s3 cp "${dump_path}" "s3://${R2_BUCKET}/${key}" --only-show-errors; then
    die "R2 upload failed for ${key} — local dump kept at ${dump_path}"
  fi

  # Read the object back. An unverified copy is a hypothesis — the same reason
  # the S4c folder copy is checksummed rather than trusted.
  local_size="$(wc -c < "${dump_path}" | tr -d ' ')"
  remote_size="$(r2_aws s3api head-object --bucket "${R2_BUCKET}" --key "${key}" \
    --query 'ContentLength' --output text)" \
    || die "R2 head-object failed for ${key} — upload not verified"
  remote_size="$(echo "${remote_size}" | tr -d '[:space:]')"
  if [[ "${remote_size}" != "${local_size}" ]]; then
    die "R2 size mismatch for ${key} (local=${local_size} remote=${remote_size}) — refusing"
  fi
  log "R2 SUCCESS bucket=${R2_BUCKET} key=${key} size=${local_size} bytes"
  r2_prune
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
  apply_dotenv_backup_vars
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
  r2_upload "${outfile}"
  echo "${outfile}"
}

# Fill .env + defaults for sourced unit tests that skip main().
# main() also calls this (idempotent given _ENV_HAS_* capture at load).
apply_dotenv_backup_vars

if [[ "${BASH_SOURCE[0]}" == "$0" ]]; then
  main "$@"
fi
