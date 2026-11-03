#!/usr/bin/env python3
"""Vincula una cuenta de WhatsApp una sola vez (escanear el QR).

Uso en Windows:  login.bat customania      (se abre una ventana de Chromium: escanea el QR ahí)
Uso en VPS Linux: bash login.sh customania

Como el servidor no tiene pantalla, el QR se publica en http://127.0.0.1:8765 solo dentro del servidor.
Desde tu PC abre un túnel SSH y mira el QR en tu navegador:
    ssh -L 8765:127.0.0.1:8765 usuario@IP_DEL_VPS
    -> abre http://127.0.0.1:8765 y escanéalo desde WhatsApp > Dispositivos vinculados > Vincular dispositivo
(También guarda datos/qr_<cuenta>.png por si prefieres descargarlo.)
"""
import argparse
import os
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from playwright.sync_api import sync_playwright

from util import DATOS, cargar_config, iniciar_logs, log
from whatsapp import WA_URL, Sesion

ultima = {"png": b""}

PAGINA = b"""<!doctype html><meta charset=utf-8><meta http-equiv=refresh content=3>
<title>QR WhatsApp</title><body style="font-family:sans-serif;text-align:center;background:#111;color:#eee">
<p>Escanea el codigo desde tu celular. Esta pagina se actualiza sola.</p>
<img src="/qr.png" style="max-width:95vw"></body>"""


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):  # noqa: N802
        if self.path.startswith("/qr.png"):
            cuerpo, tipo = ultima["png"], "image/png"
        else:
            cuerpo, tipo = PAGINA, "text/html; charset=utf-8"
        self.send_response(200)
        self.send_header("Content-Type", tipo)
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(cuerpo)

    def log_message(self, *a):
        pass


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("cuenta")
    ap.add_argument("--puerto", type=int, default=8765)
    ap.add_argument("--minutos", type=int, default=10)
    args = ap.parse_args()

    iniciar_logs()
    cfg = cargar_config()
    cuenta = next((c for c in cfg["cuentas"] if c["nombre"] == args.cuenta), None)
    if not cuenta:
        sys.exit(f"Cuenta '{args.cuenta}' no existe en config.toml")

    sin_pantalla = sys.platform.startswith("linux") and not os.environ.get("DISPLAY")
    if sin_pantalla:  # VPS: el QR se ve por un túnel SSH
        servidor = ThreadingHTTPServer(("127.0.0.1", args.puerto), Handler)
        threading.Thread(target=servidor.serve_forever, daemon=True).start()
        log.info("QR disponible en http://127.0.0.1:%d (usa un túnel SSH para verlo)", args.puerto)
    else:
        log.info("Se abrió una ventana de Chromium: escanea el QR ahí con tu celular.")

    with sync_playwright() as pw, Sesion(pw, cuenta, cfg) as s:
        s.page.goto(WA_URL, wait_until="domcontentloaded", timeout=60000)
        limite = time.time() + args.minutos * 60
        while time.time() < limite:
            ultima["png"] = s.page.screenshot()
            (DATOS / f"qr_{cuenta['nombre']}.png").write_bytes(ultima["png"])
            if s._visible("listo"):
                log.info("Vinculado. Espero 30 s para que la sesión se guarde bien...")
                s.page.wait_for_timeout(30000)
                log.info("Sesión de '%s' guardada. Ya puedes cerrar el túnel.", cuenta["nombre"])
                (DATOS / f"qr_{cuenta['nombre']}.png").unlink(missing_ok=True)
                return
            s.page.wait_for_timeout(2500)
    sys.exit("Se acabó el tiempo sin vincular. Vuelve a ejecutar el comando.")


if __name__ == "__main__":
    main()
