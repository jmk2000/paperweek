#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
export PATH="/opt/homebrew/bin:/usr/local/bin:$PATH"
if [[ ! -x .venv/bin/python || ! -x build/paperweek ]]; then
  echo 'Run bash setup.sh once before launching Paperweek.'
  exit 1
fi
exec .venv/bin/python main.py "$@"
