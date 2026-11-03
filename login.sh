#!/usr/bin/env bash
# Vincula una cuenta (una sola vez):  bash login.sh customania   |   bash login.sh personal
set -euo pipefail
DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$DIR"
[ $# -eq 1 ] || { echo "Uso: bash login.sh <nombre_de_cuenta>"; exit 1; }
exec xvfb-run -a "$DIR/.venv/bin/python" login.py "$1"
