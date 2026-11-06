#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
TARGET="${CUSTOM_NODES_DIR:-$ROOT/data/custom_nodes}"
mkdir -p "$TARGET"
repo=https://github.com/trungnk-png/comfyUI-detect-nsfw-text.git
if [[ -d "$TARGET/comfyUI-detect-nsfw-text/.git" ]]; then
  git -C "$TARGET/comfyUI-detect-nsfw-text" pull --ff-only
else
  git clone "$repo" "$TARGET/comfyUI-detect-nsfw-text"
fi

