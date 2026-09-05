#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
export PATH="/opt/homebrew/bin:/usr/local/bin:$PATH"
if [[ "$(uname -s)" == Darwin ]]; then
  if ! xcode-select -p >/dev/null 2>&1; then
    echo 'Install Apple command-line tools first: xcode-select --install'
    exit 1
  fi
fi
for tool in cmake pkg-config git; do
  if ! command -v "$tool" >/dev/null; then
    echo "Missing $tool. On a Mac, run: brew install cmake pkgconf sdl2-compat python@3.12"
    exit 1
  fi
done
if ! pkg-config --exists sdl2; then
  echo 'SDL2 development files are missing. On a Mac: brew install sdl2-compat'
  exit 1
fi
if command -v python3.12 >/dev/null; then PYTHON=python3.12; else PYTHON=python3; fi
"$PYTHON" -c 'import sys; assert sys.version_info >= (3,10), "Python 3.10+ required"'
if [[ ! -x .venv/bin/python ]]; then "$PYTHON" -m venv .venv; fi
if [[ "${PAPERWEEK_SKIP_GOOGLE_DEPS:-0}" != 1 ]]; then
  .venv/bin/python -m pip install -r requirements.txt
fi
.venv/bin/python -m unittest discover -s tests -v
cmake -S . -B build -DCMAKE_BUILD_TYPE=Release
cmake --build build --parallel "${CMAKE_BUILD_PARALLEL_LEVEL:-4}"
ctest --test-dir build --output-on-failure
.venv/bin/python -m pip freeze > build/python-versions.txt
# Render smoke test: this is the actual LVGL framebuffer, not a second mock renderer.
PAPERWEEK_DATA_DIR="$PWD/build/smoke-state" .venv/bin/python main.py demo --date 2026-09-05 --export build/smoke-test.png
printf '\nReady. Run ./run.sh demo or ./run.sh connect.\n'
