#!/usr/bin/env python3
"""Publica los Estados del día (promo de la semana + estados fijos + 3 servicios + 3 productos) en cada cuenta de WhatsApp.

Uso normal (lo llama el timer de systemd, una vez al día):
    xvfb-run -a .venv/bin/python publicar.py

Opciones útiles:
    --dry-run        arma el plan, textos e imágenes del día SIN abrir WhatsApp ni gastar la rotación
    --sin-enviar     abre WhatsApp y llega hasta el botón Enviar, pero NO envía (para probar selectores)
    --cuenta NOMBRE  solo esa cuenta
    --sin-espera     omite la espera aleatoria inicial y las pausas largas
    --depurar        guarda capturas de cada publicación
    --forzar         ignora la ventana horaria de seguridad
    --ignorar-pausa  publica aunque la programación esté en pausa desde la app (la usa el botón "Ejecutar ahora")
"""
import argparse
import os
import random
import sys
from datetime import datetime
from zoneinfo import ZoneInfo

from playwright.sync_api import sync_playwright

import catalogo
import fijos
import promo
import rotacion
import textos
from tarjeta import crear_tarjeta
from util import (
    BASE,
    DATOS,
    DETENER,
    EJECUCION,
    Detenido,
    cargar_config,
    dormir,
    escribir_json,
    iniciar_logs,
    log,
    mantener_despierto,
    notificar,
    pausa,
    pausa_activa,
    registrar_historial,
    revisar_detener,
)
from whatsapp import FalloPublicacion, NecesitaLogin, Sesion


def _hora(s):
    h, m = s.split(":")
    return int(h) * 60 + int(m)


def _dentro_de_ventana(ahora, cfg):
    minutos = ahora.hour * 60 + ahora.minute
    return _hora(cfg.get("no_publicar_antes", "00:00")) <= minutos <= _hora(cfg.get("no_publicar_despues", "23:59"))


def agregar_promo(dia, cfg):
    """Suma al plan del día la promo de la semana de customania.com.co/promos (una vez por día).

    Se revisa cada día, así que cuando la página cambia de promo (los lunes) el estado cambia solo y durante
    toda la semana se publica la misma imagen, un estado por día (los estados duran 24 h).
    """
    pc = cfg.get("promo_semana", {})
    if not pc.get("activa", True) or dia.get("promo_revisada"):
        return
    dia["promo_revisada"] = True
    try:
        item = promo.detectar(cfg)
    except Exception as e:  # noqa: BLE001
        log.exception("Detalle del error al leer la promo")
        notificar(cfg, f"No pude detectar la promo de la semana; hoy salen los demás estados sin ella: {e}")
        return
    dia["items"][item["id"]] = item
    if item["id"] not in dia["orden"]:
        if pc.get("posicion", "primero") == "ultimo":
            dia["orden"].append(item["id"])
        else:
            dia["orden"].insert(0, item["id"])


def preparar_dia(estado, fecha, cfg, sufijo=""):
    """Plan del día + datos completos + imágenes. Devuelve (dia, lista ordenada de items con su imagen).

    Si un elemento no se puede preparar (sin imagen, página caída...) se omite ese día y se avisa,
    en vez de tumbar todas las publicaciones.
    """
    cat = None
    dia = estado.get("dias", {}).get(fecha)
    if not dia:
        cat = catalogo.listar(cfg)
        dia = rotacion.plan_del_dia(estado, fecha, cat, cfg)
    agregar_promo(dia, cfg)
    fijos.agregar(dia, cfg)
    items = []
    for n, id_ in list(enumerate(dia["orden"], 1)):
        try:
            item = dia["items"].get(id_)
            if not item:
                cat = cat or catalogo.listar(cfg)
                ref = cat[id_.split(":")[0]].get(id_)
                if not ref:
                    raise RuntimeError("ya no existe en el sitio")
                item = catalogo.detalle(ref, cfg)
                dia["items"][id_] = item
            if item.get("archivo"):  # estado fijo: se publica su propia imagen tal cual
                ruta = BASE / item["archivo"]
                if not ruta.exists():
                    raise RuntimeError(f"no encuentro la imagen {item['archivo']}")
                items.append({**item, "ruta": ruta})
                continue
            slug = "".join(c if c.isalnum() else "-" for c in id_.split(":", 1)[1])[:40]
            ruta = DATOS / f"tarjetas{sufijo}" / fecha / f"{n}_{item['tipo']}_{slug}_v2.jpg"
            if not ruta.exists():
                crear_tarjeta(item, ruta)
            items.append({**item, "ruta": ruta})
        except Exception as e:  # noqa: BLE001
            notificar(cfg, f"Omito {id_} hoy: {e}")
            dia["orden"].remove(id_)
    return dia, items


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--sin-enviar", action="store_true")
    ap.add_argument("--cuenta")
    ap.add_argument("--sin-espera", action="store_true")
    ap.add_argument("--depurar", action="store_true")
    ap.add_argument("--forzar", action="store_true")
    ap.add_argument("--headless", action="store_true", help="sin ventana (por defecto se usa xvfb-run)")
    ap.add_argument("--ignorar-pausa", action="store_true")
    ap.add_argument("--origen", default="programada", help="quién la lanzó: programada, app o manual (solo para el registro)")
    args = ap.parse_args()

    iniciar_logs()
    mantener_despierto()
    cfg = cargar_config()
    tz = ZoneInfo(cfg.get("zona_horaria", "America/Bogota"))
    ahora = datetime.now(tz)
    fecha = ahora.strftime("%Y-%m-%d")

    ctl = pausa_activa(fecha)
    if ctl and not (args.dry_run or args.ignorar_pausa):
        hasta = f" hasta el {ctl['hasta']}" if ctl.get("hasta") else ""
        log.info("Publicaciones en pausa desde la app%s; no publico.", hasta)
        return 0

    if not (args.dry_run or args.forzar or args.sin_enviar) and not _dentro_de_ventana(ahora, cfg):
        log.info("Fuera de la ventana horaria permitida (%s); no publico. Usa --forzar si es a propósito.", ahora.strftime("%H:%M"))
        return 0

    cuentas = [c for c in cfg["cuentas"] if c.get("activa", True) and (not args.cuenta or c["nombre"] == args.cuenta)]
    if not cuentas:
        log.error("No hay cuentas activas que coincidan")
        return 2

    with rotacion.bloqueo():
        DETENER.unlink(missing_ok=True)  # una orden de detener vieja no debe frenar esta ejecución
        info = {
            "estado": "en_curso",
            "pid": os.getpid(),
            "inicio": datetime.now(tz).isoformat(timespec="seconds"),
            "fecha": fecha,
            "origen": args.origen,
            "modo": "prueba" if args.dry_run else ("sin_enviar" if args.sin_enviar else "real"),
            "cuenta": args.cuenta,
            "publicados": 0,
            "fallos": 0,
        }
        escribir_json(EJECUCION, info)
        codigo = 1
        try:
            codigo = _ejecutar(args, cfg, tz, fecha, cuentas, info)
        except Detenido:
            log.warning("Ejecución detenida desde la app")
            info["estado"] = "detenida"
            codigo = 3
        finally:
            DETENER.unlink(missing_ok=True)
            if info["estado"] == "en_curso":
                info["estado"] = "ok" if codigo == 0 else "con_fallos"
            info["fin"] = datetime.now(tz).isoformat(timespec="seconds")
            info["codigo"] = codigo
            escribir_json(EJECUCION, info)
        return codigo


def _ejecutar(args, cfg, tz, fecha, cuentas, info):
    estado = rotacion.cargar()
    if args.dry_run:
        estado = rotacion.copia(estado)  # la simulación no gasta la rotación real

    try:
        dia, items = preparar_dia(estado, fecha, cfg, sufijo="_preview" if args.dry_run else "")
    except Exception as e:  # noqa: BLE001
        notificar(cfg, f"No se pudo preparar el contenido del día: {e}")
        return 1
    if not args.dry_run:
        rotacion.guardar(estado)

    log.info("Plan de %s: %s", fecha, ", ".join(dia["orden"]))
    if dia.get("nuevos"):
        log.info("Productos nuevos con prioridad hoy: %s", ", ".join(dia["nuevos"]))
    if args.dry_run:
        for it in items:
            marca = "  [PRODUCTO NUEVO]" if it["id"] in dia.get("nuevos", []) else ""
            print(f"\n--- {it['id']}{marca}  ->  {it['ruta']}")
            for c in cuentas:
                print(f"[{c['nombre']}]\n{textos.caption(it, c, cfg)}\n")
        return 0

    fallos = 0
    with sync_playwright() as pw:
        for idx, cuenta in enumerate(cuentas):
            hechos = dia["publicado"].setdefault(cuenta["nombre"], {})
            pendientes = [it for it in items if it["id"] not in hechos]
            if not pendientes:
                log.info("[%s] Ya está todo publicado hoy", cuenta["nombre"])
                continue
            revisar_detener()

            if idx and not args.sin_espera:
                pausa(cfg.get("pausa_entre_cuentas", [120, 300]), "entre cuentas")
            if not args.sin_espera and cfg.get("jitter_inicio_min") and not hechos:
                espera = random.uniform(0, cfg["jitter_inicio_min"] * 60) if idx == 0 else 0
                if espera:
                    log.info("Espera inicial aleatoria de %.0fs", espera)
                    dormir(espera)

            try:
                with Sesion(pw, cuenta, cfg, headless=args.headless, depurar=args.depurar) as s:
                    s.esperar_listo()
                    s.ir_a_estados()
                    for it in pendientes:
                        revisar_detener()
                        log.info("[%s] Publicando %s", cuenta["nombre"], it["id"])
                        try:
                            s.publicar_imagen(it["ruta"], textos.caption(it, cuenta, cfg), enviar=not args.sin_enviar)
                        except FalloPublicacion as e:
                            if e.incierto:
                                hechos[it["id"]] = "incierto"  # no se reintenta solo (evita duplicados)
                                rotacion.guardar(estado)
                                _historial(fecha, tz, cuenta, it, "incierto", args)
                            raise
                        if args.sin_enviar:
                            break
                        hechos[it["id"]] = "ok"
                        rotacion.guardar(estado)
                        info["publicados"] += 1
                        escribir_json(EJECUCION, info)
                        _historial(fecha, tz, cuenta, it, "ok", args)
                        if it is not pendientes[-1] and not args.sin_espera:
                            pausa(cfg.get("pausa_entre_estados", [25, 70]), "entre estados")
                log.info("[%s] Listo", cuenta["nombre"])
            except Detenido:
                raise
            except NecesitaLogin as e:
                fallos += 1
                notificar(cfg, f"{e}. Ejecuta: bash login.sh {cuenta['nombre']}")
            except FalloPublicacion as e:
                fallos += 1
                extra = " (puede haberse publicado; revisa el celular)" if e.incierto else ""
                notificar(cfg, f"[{cuenta['nombre']}] {e}{extra}")
            except Exception as e:  # noqa: BLE001
                fallos += 1
                log.exception("Error inesperado en %s", cuenta["nombre"])
                notificar(cfg, f"[{cuenta['nombre']}] error inesperado: {e}")
            info["fallos"] = fallos
    return 1 if fallos else 0


def _historial(fecha, tz, cuenta, it, resultado, args):
    registrar_historial({
        "fecha": fecha,
        "hora": datetime.now(tz).isoformat(timespec="seconds"),
        "cuenta": cuenta["nombre"],
        "id": it["id"],
        "tipo": it["tipo"],
        "titulo": it.get("titulo", ""),
        "url": it.get("url", ""),
        "imagen": it.get("imagen", ""),
        "resultado": resultado,
        "origen": args.origen,
    })


if __name__ == "__main__":
    sys.exit(main())
