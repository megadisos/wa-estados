#!/usr/bin/env bash
# Programa la publicación diaria con systemd (hora de Bogotá). Hazlo SOLO después de probar con --sin-enviar.
# Cambia HORA_1 / HORA_2 si quieres otra hora. HORA_2 es un respaldo: si HORA_1 falló, completa lo que falte
# (si ya se publicó todo, no hace nada).
set -euo pipefail
DIR="$(cd "$(dirname "$0")" && pwd)"
HORA_1="${HORA_1:-05:00}"
HORA_2="${HORA_2:-06:30}"

sudo tee /etc/systemd/system/estados-whatsapp.service >/dev/null <<EOF
[Unit]
Description=Estados de WhatsApp (Customania)
After=network-online.target
Wants=network-online.target

[Service]
Type=oneshot
User=$USER
WorkingDirectory=$DIR
ExecStart=/usr/bin/xvfb-run -a $DIR/.venv/bin/python $DIR/publicar.py
TimeoutStartSec=3600
EOF

sudo tee /etc/systemd/system/estados-whatsapp.timer >/dev/null <<EOF
[Unit]
Description=Estados de WhatsApp: ejecución diaria

[Timer]
OnCalendar=*-*-* ${HORA_1}:00 America/Bogota
OnCalendar=*-*-* ${HORA_2}:00 America/Bogota
Persistent=true

[Install]
WantedBy=timers.target
EOF

sudo systemctl daemon-reload
sudo systemctl enable --now estados-whatsapp.timer
systemctl list-timers estados-whatsapp.timer --no-pager
echo "Activado. Ver logs: tail -f $DIR/datos/logs/estados.log"
