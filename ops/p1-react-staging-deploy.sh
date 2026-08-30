#!/usr/bin/env bash
set -euo pipefail

readonly CONFIG_FILE="/etc/p1-react-staging/deploy.env"
readonly PROJECT_NAME="proizvodstvo1-react-staging"
readonly TARGET_RE='^ghcr\.io/zavx0z/proizvodstvo1-react-portal@sha256:[0-9a-f]{64}$'
readonly LEGACY_RE='^10\.66\.0\.10:5000/platform/proizvodstvo1-react-portal@sha256:[0-9a-f]{64}$'
readonly STATE_BASENAME="release-state.env"
readonly LEDGER_BASENAME="release-ledger.log"

fail() {
  echo "p1-react-staging-deploy: $*" >&2
  exit 1
}

valid_target() { [[ "$1" =~ $TARGET_RE ]]; }
valid_known_image() { [[ "$1" =~ $TARGET_RE || "$1" =~ $LEGACY_RE ]]; }

next_ring() {
  local current="$1" rollback="$2" safety="$3" pending="$4"
  if [[ "$pending" == "$current" ]]; then
    printf '%s\n%s\n%s\n%s\n' "$current" "$rollback" "$safety" ""
  else
    printf '%s\n%s\n%s\n%s\n' "$pending" "$current" "$rollback" "$safety"
  fi
}

self_test() {
  local a b c n action image extra
  a="ghcr.io/zavx0z/proizvodstvo1-react-portal@sha256:$(printf 'a%.0s' {1..64})"
  b="ghcr.io/zavx0z/proizvodstvo1-react-portal@sha256:$(printf 'b%.0s' {1..64})"
  c="ghcr.io/zavx0z/proizvodstvo1-react-portal@sha256:$(printf 'c%.0s' {1..64})"
  n="ghcr.io/zavx0z/proizvodstvo1-react-portal@sha256:$(printf 'd%.0s' {1..64})"

  valid_target "$a"
  ! valid_target "ghcr.io/zavx0z/other@sha256:$(printf 'a%.0s' {1..64})"
  valid_known_image "10.66.0.10:5000/platform/proizvodstvo1-react-portal@sha256:$(printf 'e%.0s' {1..64})"
  ! valid_known_image "ubuntu:latest"

  IFS=' ' read -r action image extra <<< "deploy $n"
  [[ "$action" == deploy && "$image" == "$n" && -z "${extra:-}" ]]
  IFS=' ' read -r action image extra <<< "state"
  [[ "$action" == state && -z "${image:-}" && -z "${extra:-}" ]]

  mapfile -t ring < <(next_ring "$a" "$b" "$c" "$n")
  [[ "${ring[0]}" == "$n" && "${ring[1]}" == "$a" && "${ring[2]}" == "$b" && "${ring[3]}" == "$c" ]]
  mapfile -t ring < <(next_ring "$a" "$b" "$c" "$a")
  [[ "${ring[0]}" == "$a" && "${ring[1]}" == "$b" && "${ring[2]}" == "$c" && -z "${ring[3]}" ]]

  echo "P1_VPS_DEPLOY_WRAPPER_SELF_TEST_VALID"
}

if [[ "${1:-}" == "--self-test" ]]; then
  [[ "$#" == 1 ]] || fail "--self-test takes no additional arguments"
  self_test
  exit 0
fi
[[ "$#" == 0 ]] || fail "arguments are forbidden; use forced SSH command"

require_root_file() {
  local path="$1"
  [[ -f "$path" && ! -L "$path" ]] || fail "missing regular file: $path"
  [[ "$(stat -c '%u' "$path")" == 0 ]] || fail "file must be root-owned: $path"
  local mode
  mode="$(stat -c '%a' "$path")"
  (( (8#$mode & 0022) == 0 )) || fail "file must not be group/other writable: $path"
}

require_root_dir() {
  local path="$1"
  [[ -d "$path" && ! -L "$path" ]] || fail "missing real directory: $path"
  [[ "$(stat -c '%u' "$path")" == 0 ]] || fail "directory must be root-owned: $path"
  local mode
  mode="$(stat -c '%a' "$path")"
  (( (8#$mode & 0022) == 0 )) || fail "directory must not be group/other writable: $path"
}

require_root_file "$CONFIG_FILE"
# shellcheck disable=SC1090 -- fixed, root-owned config path.
source "$CONFIG_FILE"

: "${STAGING_COMPOSE_FILE:?missing STAGING_COMPOSE_FILE}"
: "${STAGING_RUNTIME_ENV:?missing STAGING_RUNTIME_ENV}"
: "${STAGING_IMAGE_ENV:?missing STAGING_IMAGE_ENV}"
: "${STATE_DIR:?missing STATE_DIR}"
: "${DOCKER_CONFIG_DIR:?missing DOCKER_CONFIG_DIR}"
: "${PORTAL_SERVICE:=portal}"
: "${NGINX_SERVICE:?missing NGINX_SERVICE}"
: "${MIN_FREE_KB:?missing MIN_FREE_KB}"
: "${EXTERNAL_HEALTH_URL:=https://staging.proizvodstvo1.ru/health}"

[[ "$PORTAL_SERVICE" == "portal" ]] || fail "PORTAL_SERVICE must be portal"
[[ "$NGINX_SERVICE" =~ ^[A-Za-z0-9._-]+$ ]] || fail "invalid NGINX_SERVICE"
[[ "$MIN_FREE_KB" =~ ^[0-9]+$ && "$MIN_FREE_KB" -ge 1048576 ]] || fail "MIN_FREE_KB must be >= 1 GiB"
[[ "$STATE_DIR" = /* && "$STAGING_COMPOSE_FILE" = /* && "$STAGING_RUNTIME_ENV" = /* && "$STAGING_IMAGE_ENV" = /* && "$DOCKER_CONFIG_DIR" = /* ]] || fail "all configured paths must be absolute"

require_root_file "$STAGING_COMPOSE_FILE"
require_root_file "$STAGING_RUNTIME_ENV"
require_root_file "$STAGING_IMAGE_ENV"
require_root_dir "$DOCKER_CONFIG_DIR"
require_root_file "$DOCKER_CONFIG_DIR/config.json"

if [[ ! -d "$STATE_DIR" ]]; then
  install -d -m 0750 -o root -g root "$STATE_DIR"
fi
require_root_dir "$STATE_DIR"

readonly STATE_FILE="$STATE_DIR/$STATE_BASENAME"
readonly LEDGER_FILE="$STATE_DIR/$LEDGER_BASENAME"
readonly LOCK_FILE="$STATE_DIR/deploy.lock"

command -v docker >/dev/null 2>&1 || fail "docker is required"
command -v curl >/dev/null 2>&1 || fail "curl is required"
command -v flock >/dev/null 2>&1 || fail "flock is required"
command -v find >/dev/null 2>&1 || fail "find is required"

ACTIVE_TMP=""
cleanup_active_tmp() {
  if [[ -n "$ACTIVE_TMP" ]]; then
    rm -f -- "$ACTIVE_TMP" || true
    ACTIVE_TMP=""
  fi
}
trap cleanup_active_tmp EXIT
trap 'cleanup_active_tmp; exit 130' INT
trap 'cleanup_active_tmp; exit 143' TERM

compose=(
  docker compose
  --project-name "$PROJECT_NAME"
  --env-file "$STAGING_RUNTIME_ENV"
  --env-file "$STAGING_IMAGE_ENV"
  -f "$STAGING_COMPOSE_FILE"
)

services="$("${compose[@]}" config --services | LC_ALL=C sort)"
expected_services="$(printf '%s\n%s\n' "$NGINX_SERVICE" "$PORTAL_SERVICE" | LC_ALL=C sort)"
[[ "$services" == "$expected_services" ]] || fail "Compose services must be exactly $PORTAL_SERVICE + $NGINX_SERVICE"

exec 9>"$LOCK_FILE"
flock -n 9 || fail "another staging release operation is active"

find "$STATE_DIR" -maxdepth 1 -type f -user root -name '.p1tmp.*' -mmin +1440 -delete || fail "stale temp cleanup failed"

CURRENT_IMAGE=""
ROLLBACK_IMAGE=""
SAFETY_IMAGE=""
PENDING_IMAGE=""
BLOCKED_IMAGE=""

load_state() {
  if [[ -f "$STATE_FILE" ]]; then
    require_root_file "$STATE_FILE"
    # shellcheck disable=SC1090 -- generated by this root-owned script.
    source "$STATE_FILE"
  fi
  for value in "$CURRENT_IMAGE" "$ROLLBACK_IMAGE" "$SAFETY_IMAGE" "$PENDING_IMAGE" "$BLOCKED_IMAGE"; do
    [[ -z "$value" ]] || valid_known_image "$value" || fail "state contains unknown image: $value"
  done
}

save_state() {
  ACTIVE_TMP="$(mktemp "$STATE_DIR/.p1tmp.state.XXXXXX")"
  {
    printf 'CURRENT_IMAGE=%q\n' "$CURRENT_IMAGE"
    printf 'ROLLBACK_IMAGE=%q\n' "$ROLLBACK_IMAGE"
    printf 'SAFETY_IMAGE=%q\n' "$SAFETY_IMAGE"
    printf 'PENDING_IMAGE=%q\n' "$PENDING_IMAGE"
    printf 'BLOCKED_IMAGE=%q\n' "$BLOCKED_IMAGE"
  } > "$ACTIVE_TMP"
  chmod 0640 "$ACTIVE_TMP"
  chown root:root "$ACTIVE_TMP"
  mv -f -- "$ACTIVE_TMP" "$STATE_FILE"
  ACTIVE_TMP=""
}

image_env_value() {
  local count value
  count="$(grep -c '^PROIZVODSTVO1_REACT_STAGING_IMAGE=' "$STAGING_IMAGE_ENV" || true)"
  [[ "$count" == 1 ]] || fail "STAGING_IMAGE_ENV must contain exactly one image assignment"
  [[ "$(grep -cvE '^(PROIZVODSTVO1_REACT_STAGING_IMAGE=|[[:space:]]*$)' "$STAGING_IMAGE_ENV" || true)" == 0 ]] || fail "STAGING_IMAGE_ENV contains unexpected content"
  value="$(sed -n 's/^PROIZVODSTVO1_REACT_STAGING_IMAGE=//p' "$STAGING_IMAGE_ENV")"
  valid_known_image "$value" || fail "STAGING_IMAGE_ENV contains unknown image"
  printf '%s\n' "$value"
}

write_image_env() {
  local image="$1"
  valid_known_image "$image" || fail "refusing unknown image for image env"
  ACTIVE_TMP="$(mktemp "$STATE_DIR/.p1tmp.image-env.XXXXXX")"
  printf 'PROIZVODSTVO1_REACT_STAGING_IMAGE=%s\n' "$image" > "$ACTIVE_TMP"
  chmod 0640 "$ACTIVE_TMP"
  chown root:root "$ACTIVE_TMP"
  install -m 0640 -o root -g root "$ACTIVE_TMP" "$STAGING_IMAGE_ENV"
  rm -f -- "$ACTIVE_TMP"
  ACTIVE_TMP=""
}

portal_id() { "${compose[@]}" ps -q "$PORTAL_SERVICE"; }
nginx_id() { "${compose[@]}" ps -q "$NGINX_SERVICE"; }

live_image() {
  local id
  id="$(portal_id)"
  [[ -n "$id" ]] || fail "staging portal container is missing"
  docker inspect -f '{{.Config.Image}}' "$id"
}

wait_healthy() {
  local id="$1" status=""
  for _ in $(seq 1 60); do
    status="$(docker inspect -f '{{if .State.Health}}{{.State.Health.Status}}{{else}}missing-healthcheck{{end}}' "$id" 2>/dev/null || true)"
    [[ "$status" == healthy ]] && return 0
    [[ "$status" == unhealthy || "$status" == missing-healthcheck ]] && return 1
    sleep 2
  done
  return 1
}

check_health() {
  local id="$1"
  wait_healthy "$id" || return 1
  docker exec "$id" bun -e "const r=await fetch('http://127.0.0.1:18180/health');if(!r.ok)process.exit(1)" >/dev/null 2>&1 || return 1
  curl --silent --show-error --fail --connect-timeout 10 --max-time 30 "$EXTERNAL_HEALTH_URL" >/dev/null || return 1
}

disk_guard() {
  local free_kb
  free_kb="$(df -Pk "$STATE_DIR" | awk 'NR==2 {print $4}')"
  [[ "$free_kb" =~ ^[0-9]+$ ]] || fail "cannot determine disk free space"
  echo "DISK_FREE_KB=$free_kb"
  if (( free_kb < MIN_FREE_KB )); then
    echo "DISK_GUARD_STATUS=DISK_GUARD_BLOCKED"
    return 1
  fi
  echo "DISK_GUARD_STATUS=OK"
}

image_id() {
  docker image inspect -f '{{.Id}}' "$1" 2>/dev/null || true
}

image_used_by_running_container() {
  local candidate_id="$1" id
  [[ -n "$candidate_id" ]] || return 1
  while read -r id; do
    [[ -n "$id" ]] || continue
    [[ "$(docker inspect -f '{{.Image}}' "$id")" == "$candidate_id" ]] && return 0
  done < <(docker ps -q)
  return 1
}

remove_exact_image() {
  local image="$1" id
  [[ -z "$image" ]] && return 0
  valid_known_image "$image" || return 1
  [[ "$image" != "$CURRENT_IMAGE" && "$image" != "$ROLLBACK_IMAGE" && "$image" != "$SAFETY_IMAGE" && "$image" != "$PENDING_IMAGE" ]] || return 1
  id="$(image_id "$image")"
  [[ -n "$id" ]] || return 0
  image_used_by_running_container "$id" && return 1
  docker image rm "$image" >/dev/null 2>&1
}

append_ledger() {
  local status="$1" action="$2" image="$3" line
  line="$(printf '%s\taction=%s\tstatus=%s\timage=%s' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$action" "$status" "$image")"
  ACTIVE_TMP="$(mktemp "$STATE_DIR/.p1tmp.ledger.XXXXXX")"
  if [[ -f "$LEDGER_FILE" ]]; then
    require_root_file "$LEDGER_FILE"
    tail -n 99 "$LEDGER_FILE" > "$ACTIVE_TMP"
  fi
  printf '%s\n' "$line" >> "$ACTIVE_TMP"
  chmod 0640 "$ACTIVE_TMP"
  chown root:root "$ACTIVE_TMP"
  mv -f -- "$ACTIVE_TMP" "$LEDGER_FILE"
  ACTIVE_TMP=""
}

apply_live_image() {
  local image="$1" previous="$2" before_nginx after_nginx new_id restored
  valid_known_image "$image" || fail "apply target is outside allowed repositories"
  valid_known_image "$previous" || fail "restore target is outside allowed repositories"
  before_nginx="$(nginx_id)"
  [[ -n "$before_nginx" ]] || fail "staging Nginx container is missing"

  write_image_env "$image"
  if ! "${compose[@]}" up -d --no-deps "$PORTAL_SERVICE" >/dev/null; then
    write_image_env "$previous"
    "${compose[@]}" up -d --no-deps "$PORTAL_SERVICE" >/dev/null 2>&1 || true
    return 1
  fi

  new_id="$(portal_id)"
  [[ -n "$new_id" ]] || return 1
  if ! check_health "$new_id"; then
    write_image_env "$previous"
    "${compose[@]}" up -d --no-deps "$PORTAL_SERVICE" >/dev/null 2>&1 || true
    restored="$(portal_id)"
    [[ -n "$restored" ]] && check_health "$restored" >/dev/null 2>&1 || true
    return 1
  fi

  after_nginx="$(nginx_id)"
  if [[ "$after_nginx" != "$before_nginx" ]]; then
    write_image_env "$previous"
    "${compose[@]}" up -d --no-deps "$PORTAL_SERVICE" >/dev/null 2>&1 || true
    fail "staging Nginx container changed during portal update"
  fi

  echo "PORTAL_CONTAINER_AFTER=$new_id"
  echo "STAGING_NGINX_CONTAINER=$after_nginx"
}

load_state
current_live="$(live_image)"
valid_known_image "$current_live" || fail "live portal image is outside allowed repositories: $current_live"
configured_image="$(image_env_value)"
[[ "$configured_image" == "$current_live" ]] || fail "STAGING_IMAGE_ENV does not match live portal image"

if [[ -z "$CURRENT_IMAGE" ]]; then
  CURRENT_IMAGE="$current_live"
  save_state
fi

requested="${SSH_ORIGINAL_COMMAND:-}"
[[ -n "$requested" && "$requested" != *$'\n'* && "$requested" != *$'\r'* ]] || fail "missing or malformed SSH_ORIGINAL_COMMAND"
IFS=' ' read -r action image extra <<< "$requested"
[[ -z "${extra:-}" ]] || fail "too many command fields"

case "$action" in
  state)
    [[ -z "${image:-}" ]] || fail "state accepts no image"
    echo "STATUS=ok"
    echo "LIVE_IMAGE=$current_live"
    echo "CURRENT_IMAGE=$CURRENT_IMAGE"
    echo "ROLLBACK_IMAGE=$ROLLBACK_IMAGE"
    echo "SAFETY_IMAGE=$SAFETY_IMAGE"
    echo "PENDING_IMAGE=$PENDING_IMAGE"
    echo "BLOCKED_IMAGE=$BLOCKED_IMAGE"
    ;;

  deploy)
    [[ -n "${image:-}" ]] || fail "deploy requires image"
    valid_target "$image" || fail "deploy accepts only immutable target GHCR image"
    [[ -z "$PENDING_IMAGE" ]] || fail "PENDING_RECOVERY_REQUIRED"

    if [[ -n "$BLOCKED_IMAGE" ]]; then
      if remove_exact_image "$BLOCKED_IMAGE"; then
        BLOCKED_IMAGE=""
        save_state
      else
        fail "CLEANUP_BLOCKED: previous VPS image cannot be safely removed"
      fi
    fi

    [[ "$current_live" == "$CURRENT_IMAGE" ]] || fail "live image does not match committed current state"

    if [[ "$image" == "$CURRENT_IMAGE" ]]; then
      check_health "$(portal_id)" || fail "current no-op image is not healthy"
      PENDING_IMAGE="$image"
      save_state
      append_ledger pending-noop deploy "$image"
      echo "STATUS=pending"
      echo "CURRENT_IMAGE=$CURRENT_IMAGE"
      echo "ROLLBACK_IMAGE=$CURRENT_IMAGE"
      echo "SAFETY_IMAGE=$SAFETY_IMAGE"
      echo "PENDING_IMAGE=$PENDING_IMAGE"
      exit 0
    fi

    disk_guard || fail "DISK_GUARD_BLOCKED"
    docker --config "$DOCKER_CONFIG_DIR" pull "$image" >/dev/null || fail "target image pull failed"

    PENDING_IMAGE="$image"
    save_state
    if ! apply_live_image "$image" "$CURRENT_IMAGE"; then
      PENDING_IMAGE=""
      if remove_exact_image "$image"; then
        BLOCKED_IMAGE=""
      else
        BLOCKED_IMAGE="$image"
      fi
      save_state
      append_ledger apply-failed deploy "$image"
      if [[ -n "$BLOCKED_IMAGE" ]]; then
        fail "new portal did not become healthy; previous current restored; CLEANUP_BLOCKED"
      fi
      fail "new portal did not become healthy; previous current restored and candidate removed"
    fi

    append_ledger pending deploy "$image"
    echo "STATUS=pending"
    echo "CURRENT_IMAGE=$CURRENT_IMAGE"
    echo "ROLLBACK_IMAGE=$CURRENT_IMAGE"
    echo "SAFETY_IMAGE=$SAFETY_IMAGE"
    echo "PENDING_IMAGE=$PENDING_IMAGE"
    ;;

  commit)
    [[ -n "${image:-}" ]] || fail "commit requires image"
    valid_target "$image" || fail "commit accepts only target GHCR image"
    [[ "$PENDING_IMAGE" == "$image" ]] || fail "commit image does not match pending image"
    [[ "$current_live" == "$PENDING_IMAGE" ]] || fail "live image does not match pending image"

    if [[ "$PENDING_IMAGE" == "$CURRENT_IMAGE" ]]; then
      PENDING_IMAGE=""
      save_state
      append_ledger ok commit-noop "$image"
      echo "CLEANUP_STATUS=OK"
      echo "STATUS=ok"
      echo "CURRENT_IMAGE=$CURRENT_IMAGE"
      echo "ROLLBACK_IMAGE=$ROLLBACK_IMAGE"
      echo "SAFETY_IMAGE=$SAFETY_IMAGE"
      echo "BLOCKED_IMAGE=$BLOCKED_IMAGE"
      exit 0
    fi

    mapfile -t ring < <(next_ring "$CURRENT_IMAGE" "$ROLLBACK_IMAGE" "$SAFETY_IMAGE" "$PENDING_IMAGE")
    new_current="${ring[0]}"
    new_rollback="${ring[1]}"
    new_safety="${ring[2]}"
    outgoing="${ring[3]}"

    CURRENT_IMAGE="$new_current"
    ROLLBACK_IMAGE="$new_rollback"
    SAFETY_IMAGE="$new_safety"
    PENDING_IMAGE=""
    BLOCKED_IMAGE=""

    if [[ -n "$outgoing" ]]; then
      if ! remove_exact_image "$outgoing"; then
        BLOCKED_IMAGE="$outgoing"
      fi
    fi

    save_state
    if [[ -n "$BLOCKED_IMAGE" ]]; then
      append_ledger cleanup-blocked commit "$image"
      echo "CLEANUP_STATUS=CLEANUP_BLOCKED"
    else
      append_ledger ok commit "$image"
      echo "CLEANUP_STATUS=OK"
    fi
    echo "STATUS=ok"
    echo "CURRENT_IMAGE=$CURRENT_IMAGE"
    echo "ROLLBACK_IMAGE=$ROLLBACK_IMAGE"
    echo "SAFETY_IMAGE=$SAFETY_IMAGE"
    echo "BLOCKED_IMAGE=$BLOCKED_IMAGE"
    ;;

  rollback)
    [[ -n "${image:-}" ]] || fail "rollback requires image"
    valid_known_image "$image" || fail "rollback image is outside allowed repositories"
    [[ -n "$PENDING_IMAGE" ]] || fail "there is no pending deployment to roll back"
    [[ "$image" == "$CURRENT_IMAGE" ]] || fail "rollback target must equal committed current image"

    failed_image="$PENDING_IMAGE"
    live_now="$(live_image)"

    if [[ "$PENDING_IMAGE" == "$CURRENT_IMAGE" ]]; then
      [[ "$live_now" == "$CURRENT_IMAGE" ]] || fail "no-op pending state has unexpected live image"
      PENDING_IMAGE=""
      save_state
      append_ledger rollback-noop rollback "$failed_image"
      echo "STATUS=ok"
      echo "CLEANUP_STATUS=OK"
      echo "CURRENT_IMAGE=$CURRENT_IMAGE"
      echo "ROLLBACK_IMAGE=$ROLLBACK_IMAGE"
      echo "SAFETY_IMAGE=$SAFETY_IMAGE"
      echo "BLOCKED_IMAGE=$BLOCKED_IMAGE"
      exit 0
    fi

    if [[ "$live_now" == "$CURRENT_IMAGE" ]]; then
      PENDING_IMAGE=""
      if remove_exact_image "$failed_image"; then
        BLOCKED_IMAGE=""
        cleanup="OK"
      else
        BLOCKED_IMAGE="$failed_image"
        cleanup="CLEANUP_BLOCKED"
      fi
      save_state
      append_ledger recovered-before-switch rollback "$failed_image"
      echo "STATUS=ok"
      echo "CLEANUP_STATUS=$cleanup"
      echo "CURRENT_IMAGE=$CURRENT_IMAGE"
      echo "ROLLBACK_IMAGE=$ROLLBACK_IMAGE"
      echo "SAFETY_IMAGE=$SAFETY_IMAGE"
      echo "BLOCKED_IMAGE=$BLOCKED_IMAGE"
      exit 0
    fi

    [[ "$live_now" == "$PENDING_IMAGE" ]] || fail "live image matches neither committed current nor pending image"
    apply_live_image "$CURRENT_IMAGE" "$PENDING_IMAGE" || fail "rollback failed"
    PENDING_IMAGE=""
    if remove_exact_image "$failed_image"; then
      BLOCKED_IMAGE=""
      cleanup="OK"
    else
      BLOCKED_IMAGE="$failed_image"
      cleanup="CLEANUP_BLOCKED"
    fi
    save_state
    append_ledger rollback rollback "$failed_image"
    echo "STATUS=ok"
    echo "CLEANUP_STATUS=$cleanup"
    echo "CURRENT_IMAGE=$CURRENT_IMAGE"
    echo "ROLLBACK_IMAGE=$ROLLBACK_IMAGE"
    echo "SAFETY_IMAGE=$SAFETY_IMAGE"
    echo "BLOCKED_IMAGE=$BLOCKED_IMAGE"
    ;;

  *)
    fail "allowed commands: state, deploy IMAGE, commit IMAGE, rollback IMAGE"
    ;;
esac
