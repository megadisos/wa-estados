"""Utilidades comunes: configuración, logs, pausas y notificaciones."""
import logging
import logging.handlers
import random
import sys
import time
from pathlib import Path

import requests

try:
    import tomllib
except ImportError:  # Python < 3.11
    import tomli as tomllib

BASE = Path(__file__).resolve().parent
DATOS = BASE / "datos"

log = logging.getLogger("estados")


def cargar_config(ruta=None):
    ruta = Path(ruta) if ruta else BASE / "config.toml"
    with open(ruta, "rb") as f:
        cfg = tomllib.load(f)
    for c in cfg.get("cuentas", []):
        p = Path(c["perfil"])
        c["perfil"] = str(p if p.is_absolute() else BASE / p)
    return cfg


def mantener_despierto():
    """En Windows evita que el PC se suspenda mientras corre la publicación."""
    if sys.platform == "win32":
        import ctypes

        ctypes.windll.kernel32.SetThreadExecutionState(0x80000000 | 0x00000001)  # CONTINUOUS | SYSTEM_REQUIRED


def iniciar_logs():
    for flujo in (sys.stdout, sys.stderr):
        try:
            flujo.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass
    (DATOS / "logs").mkdir(parents=True, exist_ok=True)
    log.setLevel(logging.INFO)
    if log.handlers:
        return
    fmt = logging.Formatter("%(asctime)s %(levelname)s %(message)s")
    fh = logging.handlers.RotatingFileHandler(
        DATOS / "logs" / "estados.log", maxBytes=1_000_000, backupCount=5, encoding="utf-8"
    )
    fh.setFormatter(fmt)
    sh = logging.StreamHandler(sys.stdout)
    sh.setFormatter(fmt)
    log.addHandler(fh)
    log.addHandler(sh)


def pausa(rango, motivo=""):
    """Espera un tiempo aleatorio dentro de rango=[min,max] segundos."""
    seg = random.uniform(rango[0], rango[1])
    if motivo:
        log.info("Pausa de %.0fs (%s)", seg, motivo)
    time.sleep(seg)


def notificar(cfg, mensaje):
    """Aviso por Telegram si está configurado. Nunca lanza excepciones."""
    log.warning("ALERTA: %s", mensaje)
    n = cfg.get("notificaciones", {})
    if not (n.get("telegram_token") and n.get("telegram_chat_id")):
        return
    try:
        requests.post(
            f"https://api.telegram.org/bot{n['telegram_token']}/sendMessage",
            data={"chat_id": n["telegram_chat_id"], "text": f"Estados WhatsApp: {mensaje}"},
            timeout=15,
        )
    except Exception as e:  # noqa: BLE001
        log.error("No se pudo enviar la alerta por Telegram: %s", e)
