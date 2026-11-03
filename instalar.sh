#!/usr/bin/env bash
# Instala dependencias en el VPS (Ubuntu/Debian). Ejecutar como tu usuario normal (usa sudo cuando hace falta).
set -euo pipefail
DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$DIR"

sudo apt-get update -y
sudo apt-get install -y python3-venv python3-pip xvfb fonts-dejavu-core
python3 -m venv .venv
.venv/bin/pip install -U pip
.venv/bin/pip install -r requirements.txt
.venv/bin/playwright install chromium
sudo "$DIR/.venv/bin/playwright" install-deps chromium

mkdir -p datos/perfiles datos/logs
echo
echo "Listo. Siguientes pasos:"
echo "  1) bash login.sh customania    (escanear QR)"
echo "  2) bash login.sh personal      (escanear QR)"
echo "  3) .venv/bin/python publicar.py --dry-run"
echo "  4) xvfb-run -a .venv/bin/python publicar.py --sin-enviar --depurar --forzar"
echo "  5) bash activar_timer.sh"
