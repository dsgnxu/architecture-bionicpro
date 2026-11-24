#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
mkdir -p "$ROOT/wheels"
# Reuse auth wheels when present, then fetch clickhouse-connect
if [[ -d "$ROOT/../bionicpro-auth/wheels" ]]; then
  cp "$ROOT/../bionicpro-auth/wheels/"*.whl "$ROOT/wheels/" || true
fi
pip3 download -d "$ROOT/wheels" -r "$ROOT/requirements.txt"
echo "Wheels ready in $ROOT/wheels"
