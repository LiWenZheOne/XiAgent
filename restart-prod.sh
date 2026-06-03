#!/usr/bin/env bash

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

if [[ -x "$SCRIPT_DIR/stop-prod.sh" ]]; then
  "$SCRIPT_DIR/stop-prod.sh"
fi

if [[ -x "$SCRIPT_DIR/start-prod.sh" ]]; then
  "$SCRIPT_DIR/start-prod.sh"
fi

