#!/usr/bin/env bash

set -euo pipefail

readonly ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
readonly PID_FILE="$ROOT_DIR/api-server.pid"
readonly LOG_OUT="$ROOT_DIR/api-server.out.log"
readonly LOG_ERR="$ROOT_DIR/api-server.err.log"
readonly ENV_FILE="$ROOT_DIR/.env.production"

load_env_file() {
  local file="$1"
  while IFS= read -r line || [[ -n "$line" ]]; do
    case "$line" in
      \#*|"")
        continue
        ;;
      export\ *)
        line="${line#export }"
        ;;
    esac
    if [[ "$line" == *"="* ]]; then
      export "$line"
    fi
  done < "$file"
}

if [[ -f "$ENV_FILE" ]]; then
  load_env_file "$ENV_FILE"
fi

cd "$ROOT_DIR"

if [[ -f "$PID_FILE" ]]; then
  EXISTING_PID="$(cat "$PID_FILE")"
  if [[ -n "$EXISTING_PID" ]] && ps -p "$EXISTING_PID" > /dev/null 2>&1; then
    echo "Service already running (pid: $EXISTING_PID)."
    exit 1
  fi
fi

if [[ -n "${VIRTUAL_ENV:-}" ]] && [[ -x "$VIRTUAL_ENV/bin/python" ]]; then
  PYTHON_BIN="$VIRTUAL_ENV/bin/python"
elif [[ -x "$ROOT_DIR/.venv/bin/python" ]]; then
  PYTHON_BIN="$ROOT_DIR/.venv/bin/python"
elif command -v python3 >/dev/null 2>&1; then
  PYTHON_BIN="python3"
elif command -v python >/dev/null 2>&1; then
  PYTHON_BIN="python"
else
  echo "No Python executable found."
  exit 1
fi

export XIAGENT_DATABASE_PATH="${XIAGENT_DATABASE_PATH:-$ROOT_DIR/.data/xiagent.sqlite3}"
export XIAGENT_ASSET_STORAGE_DIR="${XIAGENT_ASSET_STORAGE_DIR:-$ROOT_DIR/storage/assets}"
export XIAGENT_WORKFLOW_DIR="${XIAGENT_WORKFLOW_DIR:-$ROOT_DIR/workflows}"
export XIAGENT_API_HOST="${XIAGENT_API_HOST:-0.0.0.0}"
export XIAGENT_API_PORT="${XIAGENT_API_PORT:-8000}"

UVICORN_WORKERS="${XIAGENT_UVICORN_WORKERS:-1}"
UVICORN_RELOAD="${XIAGENT_UVICORN_RELOAD:-false}"

CMD=("$PYTHON_BIN" -m uvicorn "xiagent.api.app:app" --host "$XIAGENT_API_HOST" --port "$XIAGENT_API_PORT")
if [[ "$UVICORN_WORKERS" != "1" ]]; then
  CMD+=(--workers "$UVICORN_WORKERS")
fi
if [[ "$UVICORN_RELOAD" == "1" || "$UVICORN_RELOAD" == "true" || "$UVICORN_RELOAD" == "yes" ]]; then
  CMD+=(--reload)
fi

echo "Starting XiAgent API..."
echo "PID file: $PID_FILE"
echo "Log: $LOG_OUT / $LOG_ERR"
nohup "${CMD[@]}" > "$LOG_OUT" 2> "$LOG_ERR" < /dev/null &
echo $! > "$PID_FILE"
echo "Started with pid $! on ${XIAGENT_API_HOST}:${XIAGENT_API_PORT}"

