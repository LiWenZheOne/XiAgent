#!/usr/bin/env bash

set -euo pipefail

readonly ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
readonly PID_FILE="$ROOT_DIR/api-server.pid"

terminate_pid() {
  local pid="$1"
  if ! ps -p "$pid" > /dev/null 2>&1; then
    return 0
  fi

  kill "$pid"
  for _ in {1..10}; do
    sleep 1
    if ! ps -p "$pid" > /dev/null 2>&1; then
      return 0
    fi
  done

  kill -9 "$pid" || true
}

stopped_any=false

if [[ -f "$PID_FILE" ]]; then
  PID_FROM_FILE="$(cat "$PID_FILE")"
  if [[ -n "$PID_FROM_FILE" ]]; then
    if ps -p "$PID_FROM_FILE" > /dev/null 2>&1; then
      echo "Stopping XiAgent API (pid: $PID_FROM_FILE)"
      terminate_pid "$PID_FROM_FILE" || true
      stopped_any=true
    else
      rm -f "$PID_FILE"
    fi
  fi
fi

while IFS= read -r pid; do
  if [[ -n "${pid}" ]] && ps -p "$pid" > /dev/null 2>&1; then
    echo "Stopping XiAgent API (pid: $pid)"
    terminate_pid "$pid" || true
    stopped_any=true
  fi
done < <(pgrep -f "python.*xiagent.api.app:app" || true)

if [[ -f "$PID_FILE" ]] && ! ps -p "$(cat "$PID_FILE")" > /dev/null 2>&1; then
  rm -f "$PID_FILE"
fi

if [[ "$stopped_any" == true ]]; then
  echo "XiAgent API stopped."
else
  echo "No running XiAgent API process found."
fi

