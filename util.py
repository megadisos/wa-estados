"""Utilidades comunes: configuración, logs, pausas, notificaciones y el control desde la app."""
import json
import logging
import logging.handlers
import os
import random
import sys
import time
from datetime import date
from pathlib import Path

import requests

try:
    import tomllib
except ImportError:  # Python < 3.11
    import tomli as tomllib

BASE = Path(__file__).resolve().parent
DATOS = BASE / "datos"

# Archivos que comparten publicar.py y el agente de la app (agente.py)
AJUSTES_APP = DATOS / "ajustes_app.json"  # cambios hechos desde la app; se aplican encima de config.toml
CONTROL = DATOS / "control.json"  # pausa de las publicaciones programadas
DETENER = DATOS / "detener.flag"  # si existe, la ejecución en curso se detiene en el siguiente paso seguro
EJECUCION = DATOS / "ejecucion.json"  # ejecución en curso o la última que corrió
HISTORIAL = DATOS / "historial.jsonl"  # una línea por estado publicado (no se borra con la rotación)

log = logging.getLogger("estados")


class Detenido(Exception):
    """Se pidió detener la ejecución desde la app."""


def leer_json(ruta, defecto=None):
    try:
        with open(ruta, encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, ValueError):
        return defecto


def escribir_json(ruta, datos):
    ruta = Path(ruta)
    ruta.parent.mkdir(parents=True, exist_ok=True)
    tmp = ruta.with_suffix(ruta.suffix + ".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(datos, f, ensure_ascii=False, indent=1)
    os.replace(tmp, ruta)


def aplicar_ajustes(cfg, ajustes):
    """Mezcla los ajustes guardados por la app encima de config.toml (config.toml no se modifica)."""
    for clave, valor in (ajustes or {}).items():
        if clave == "cuentas_activas":
            for c in cfg.get("cuentas", []):
                if c["nombre"] in valor:
                    c["activa"] = bool(valor[c["nombre"]])
        elif isinstance(valor, dict) and isinstance(cfg.get(clave), dict):
            cfg[clave] = {**cfg[clave], **valor}
        else:
            cfg[clave] = valor
    return cfg


def cargar_config(ruta=None, ajustes=True):
    ruta = Path(ruta) if ruta else BASE / "config.toml"
    with open(ruta, "rb") as f:
        cfg = tomllib.load(f)
    if ajustes:
        aplicar_ajustes(cfg, leer_json(AJUSTES_APP, {}))
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


def revisar_detener():
    """Lanza Detenido si desde la app se pidió detener la ejecución en curso."""
    if DETENER.exists():
        raise Detenido("Ejecución detenida desde la app")


def dormir(seg):
    """time.sleep que se interrumpe si se pide detener desde la app."""
    fin = time.monotonic() + seg
    while True:
        revisar_detener()
        falta = fin - time.monotonic()
        if falta <= 0:
            return
        time.sleep(min(1.0, falta))


def pausa(rango, motivo=""):
    """Espera un tiempo aleatorio dentro de rango=[min,max] segundos."""
    seg = random.uniform(rango[0], rango[1])
    if motivo:
        log.info("Pausa de %.0fs (%s)", seg, motivo)
    dormir(seg)


def pausa_activa(hoy):
    """Devuelve el control de pausa si las publicaciones programadas están en pausa hoy, o None.

    control.json: {"pausado": true, "hasta": "AAAA-MM-DD" o null}. "hasta" es inclusive: el día siguiente
    se reanuda sola.
    """
    ctl = leer_json(CONTROL, {}) or {}
    if not ctl.get("pausado"):
        return None
    hasta = ctl.get("hasta")
    if hasta and date.fromisoformat(hoy) > date.fromisoformat(hasta):
        return None
    return ctl


def registrar_historial(registro):
    """Agrega una línea al historial permanente de publicaciones."""
    HISTORIAL.parent.mkdir(parents=True, exist_ok=True)
    with open(HISTORIAL, "a", encoding="utf-8") as f:
        f.write(json.dumps(registro, ensure_ascii=False) + "\n")


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
