#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
mkdir -p "$ROOT/wheels"
pip3 download -d "$ROOT/wheels" \
  --only-binary=:all: \
  --python-version 311 \
  --platform manylinux2014_aarch64 \
  -r "$ROOT/requirements.txt" || pip3 download -d "$ROOT/wheels" -r "$ROOT/requirements.txt"
echo "Wheels ready in $ROOT/wheels"
