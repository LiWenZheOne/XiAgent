#!/usr/bin/env bash

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT_DIR"

REMOTE_NAME="${DEPLOY_REMOTE:-origin}"
BRANCH="${DEPLOY_BRANCH:-main}"
HARD_RESET="${DEPLOY_HARD_RESET:-false}"
FORCE_DIRTY="${DEPLOY_FORCE_DIRTY:-false}"
UPDATE_DEPS="${DEPLOY_UPDATE_DEPS:-false}"

log() {
  echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*"
}

log "Start deploy. root=$ROOT_DIR branch=$BRANCH remote=$REMOTE_NAME"

if [[ ! -d .git ]]; then
  echo "Not a git repository: $ROOT_DIR"
  exit 1
fi

git fetch --prune "$REMOTE_NAME"
TARGET_REF="$REMOTE_NAME/$BRANCH"

if [[ "$HARD_RESET" == "true" || "$HARD_RESET" == "1" || "$HARD_RESET" == "yes" ]]; then
  log "Reset mode: hard reset to $TARGET_REF"
  git reset --hard "$TARGET_REF"
else
  if [[ "$(git rev-parse --abbrev-ref HEAD)" != "$BRANCH" ]]; then
    log "Switch branch to $BRANCH"
    git switch "$BRANCH"
  fi

  if ! git diff --quiet || ! git diff --cached --quiet; then
    if [[ "$FORCE_DIRTY" == "true" || "$FORCE_DIRTY" == "1" || "$FORCE_DIRTY" == "yes" ]]; then
      log "Local changes detected, forcing backup via stash."
      git stash push -u -m "deploy-prod backup $(date '+%Y%m%d-%H%M%S')" >/dev/null
    else
      echo "Local working tree has uncommitted changes. Set DEPLOY_FORCE_DIRTY=true if you want to continue."
      exit 1
    fi
  fi

  log "Pulling latest changes: $REMOTE_NAME/$BRANCH"
  if ! git pull --ff-only "$REMOTE_NAME" "$BRANCH"; then
    echo "Fast-forward pull failed. Use DEPLOY_HARD_RESET=true if you want to force remote state."
    exit 1
  fi
fi

if [[ "$UPDATE_DEPS" == "true" || "$UPDATE_DEPS" == "1" || "$UPDATE_DEPS" == "yes" ]]; then
  PYTHON_BIN="python3"
  if [[ -n "${VIRTUAL_ENV:-}" ]] && [[ -x "$VIRTUAL_ENV/bin/python" ]]; then
    PYTHON_BIN="$VIRTUAL_ENV/bin/python"
  elif [[ -x "$ROOT_DIR/.venv/bin/python" ]]; then
    PYTHON_BIN="$ROOT_DIR/.venv/bin/python"
  elif command -v python3 >/dev/null 2>&1; then
    PYTHON_BIN="python3"
  elif command -v python >/dev/null 2>&1; then
    PYTHON_BIN="python"
  else
    echo "No Python executable found for installing dependencies."
    exit 1
  fi

  log "Updating dependencies..."
  "$PYTHON_BIN" -m pip install -e .
fi

if [[ -x "$ROOT_DIR/stop-prod.sh" ]]; then
  log "Stopping service..."
  "$ROOT_DIR/stop-prod.sh"
fi

log "Starting service..."
"$ROOT_DIR/start-prod.sh"

log "Deploy finished."

