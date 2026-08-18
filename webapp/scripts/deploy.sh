#!/usr/bin/env bash
set -euo pipefail

APP_DIR="/var/www/tradingapp/webapp"
VENV_DIR="/var/www/tradingapp/venv"
SERVICE_NAME="vikalp-income"

log() {
  printf '[deploy] %s\n' "$*"
}

fail() {
  printf '[deploy][error] %s\n' "$*" >&2
}

systemctl_cmd() {
  if [[ "${EUID}" -eq 0 ]]; then
    systemctl "$@"
  else
    sudo -n systemctl "$@"
  fi
}

branch="${1:-}"
if [[ "$branch" != "develop" && "$branch" != "master" ]]; then
  fail "Usage: $0 <develop|master>"
  exit 2
fi

rollback() {
  local previous_sha="${1:-}"
  if [[ -z "$previous_sha" ]]; then
    fail "Rollback skipped: previous SHA is unknown."
    return 1
  fi

  fail "Deployment failed. Rolling back to ${previous_sha}."
  cd "$APP_DIR"
  git reset --hard "$previous_sha"
  systemctl_cmd restart "$SERVICE_NAME"
  if systemctl_cmd is-active --quiet "$SERVICE_NAME"; then
    log "Rollback restarted ${SERVICE_NAME}; service is active."
  else
    fail "Rollback restart did not make ${SERVICE_NAME} active. Manual intervention required."
  fi
}

log "Starting deployment for branch '${branch}'."
cd "$APP_DIR"

previous_sha="$(git rev-parse HEAD)"
log "Current SHA before deployment: ${previous_sha}"

log "Fetching origin/${branch}."
git fetch origin "$branch"

log "Checking out ${branch} and resetting to origin/${branch}."
git checkout "$branch"
git reset --hard "origin/${branch}"

# Deliberately never run git clean. Runtime files such as DBs, uploads, broker
# tokens, .env, CSVs and logs may live on the server and must not be deleted.

log "Activating virtual environment."
if [[ ! -f "${VENV_DIR}/bin/activate" ]]; then
  fail "Virtual environment not found at ${VENV_DIR}."
  rollback "$previous_sha"
  exit 1
fi
# shellcheck source=/dev/null
source "${VENV_DIR}/bin/activate"

log "Installing Python requirements."
if [[ ! -f requirements.txt ]]; then
  fail "requirements.txt is missing in ${APP_DIR}."
  rollback "$previous_sha"
  exit 1
fi
python -m pip install --upgrade pip
python -m pip install -r requirements.txt

log "Running Python compile validation."
if ! python -m compileall -q \
  -x '(^|/)(\.git|\.venv|venv|node_modules|__pycache__|\.pytest_cache|\.next|dist|build|coverage)(/|$)' \
  .; then
  fail "Python compile validation failed."
  rollback "$previous_sha"
  exit 1
fi

log "Restarting ${SERVICE_NAME}."
if ! systemctl_cmd restart "$SERVICE_NAME"; then
  fail "systemctl restart failed."
  rollback "$previous_sha"
  exit 1
fi

log "Verifying ${SERVICE_NAME} is active."
if ! systemctl_cmd is-active --quiet "$SERVICE_NAME"; then
  fail "${SERVICE_NAME} is not active after restart."
  rollback "$previous_sha"
  exit 1
fi

new_sha="$(git rev-parse HEAD)"
log "Deployment successful: ${previous_sha} -> ${new_sha} on ${branch}."
