#!/usr/bin/env bash
set -euo pipefail
# Explicit toolchain download, only when the user runs this script. Kept outside
# the source tree by default. SDK release and SDK repository commit are pinned.
DEST="${1:-$HOME/.cache/paperweek-emsdk}"
if [[ ! -d "$DEST/.git" ]]; then
  git clone --branch 4.0.14 --depth 1 https://github.com/emscripten-core/emsdk.git "$DEST"
fi
actual="$(git -C "$DEST" rev-parse HEAD)"
[[ "$actual" == eff90ca04a3785f571a8095b3a42b63799cf384a ]] || { echo "Unexpected emsdk checkout at $DEST. Use a new empty directory." >&2;exit 1; }
"$DEST/emsdk" install 4.0.14
"$DEST/emsdk" activate 4.0.14
echo "Next: source \"$DEST/emsdk_env.sh\""
