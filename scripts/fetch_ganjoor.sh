#!/usr/bin/env bash
set -euo pipefail
DEST="${1:-data/upstream/ganjoor-data}"
mkdir -p "$(dirname "$DEST")"
if [ -d "$DEST/.git" ]; then
  git -C "$DEST" pull --ff-only
else
  git clone --depth 1 https://github.com/ganjoor/ganjoor-data.git "$DEST"
fi
printf 'Ganjoor data ready at %s\n' "$DEST"
