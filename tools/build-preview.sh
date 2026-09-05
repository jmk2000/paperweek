#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
CLANG="${CLANG:-clang}"
command -v "$CLANG" >/dev/null || { echo 'Install LLVM with a WebAssembly target, or use the Emscripten LVGL build.' >&2; exit 1; }
mkdir -p build/preview
"$CLANG" --target=wasm32 -O2 -fno-builtin -nostdlib \
  -Itools/freestanding/include -Icore -Iui \
  core/calendar.c ui/calendar_ui.c platform/web/bridge.c platform/web/canvas_browser.c \
  tools/freestanding/minilib.c \
  -Wl,--no-entry -Wl,--export-all -Wl,--export-memory \
  -Wl,--initial-memory=4194304 -Wl,--max-memory=16777216 -Wl,-z,stack-size=131072 \
  -o build/preview/paperweek-preview.wasm
python3 tools/package_web.py preview
