#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
command -v emcmake >/dev/null || { echo 'Activate Emscripten first: source /path/to/emsdk/emsdk_env.sh' >&2; exit 1; }
emcmake cmake -S . -B build/lvgl -DPW_BUILD_LVGL=ON -DBUILD_TESTING=OFF -DCMAKE_BUILD_TYPE=Release
cmake --build build/lvgl --parallel "${CMAKE_BUILD_PARALLEL_LEVEL:-4}"
python3 tools/package_web.py lvgl
