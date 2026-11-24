#!/usr/bin/env bash
# Скачивает wheels на хосте (нужен доступ к PyPI), затем docker build ставит их offline.
set -euo pipefail
cd "$(dirname "$0")/.."
mkdir -p wheels
pip3 download -r requirements.txt -d wheels
echo "Wheels ready in $(pwd)/wheels"
