"""Rotación diaria sin repetir hasta agotar el catálogo, y estado persistente (idempotente por día)."""
import copy
import json
import os
import random
from contextlib import contextmanager
from datetime import date

from util import DATOS

try:
    import fcntl
except ImportError:  # Windows
    fcntl = None
    import msvcrt

ARCHIVO = DATOS / "estado.json"
DIAS_A_GUARDAR = 14


def cargar():
    if ARCHIVO.exists():
        with open(ARCHIVO, encoding="utf-8") as f:
            return json.load(f)
    return {}


def guardar(estado):
    DATOS.mkdir(parents=True, exist_ok=True)
    tmp = ARCHIVO.with_suffix(".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(estado, f, ensure_ascii=False, indent=1)
    os.replace(tmp, ARCHIVO)


@contextmanager
def bloqueo():
    """Evita que dos ejecuciones corran a la vez (p. ej. timer + ejecución manual)."""
    DATOS.mkdir(parents=True, exist_ok=True)
    f = open(DATOS / "ejecucion.lock", "w")
    try:
        if fcntl:
            fcntl.flock(f, fcntl.LOCK_EX | fcntl.LOCK_NB)
        else:
            msvcrt.locking(f.fileno(), msvcrt.LK_NBLCK, 1)
    except OSError:
        f.close()
        raise SystemExit("Ya hay otra ejecución en curso; salgo.")
    try:
        yield
    finally:
        if fcntl:
            fcntl.flock(f, fcntl.LOCK_UN)
        else:
            f.seek(0)
            msvcrt.locking(f.fileno(), msvcrt.LK_UNLCK, 1)
        f.close()


def tomar(estado, clave, ids, n, rng, prioridad=()):
    """Toma n ids del ciclo `clave`; no repite ninguno hasta haber pasado por todo el catálogo.

    Los ids de `prioridad` (p. ej. productos nuevos) se toman primero, sin alterar el orden del ciclo.
    """
    vivos = set(ids)
    n = min(n, len(vivos))
    ciclo = estado.setdefault("ciclos", {}).setdefault(clave, {"pendientes": [], "usados": [], "vueltas": 0})
    pend = [i for i in ciclo["pendientes"] if i in vivos]
    usados = [i for i in ciclo["usados"] if i in vivos]
    conocidos = set(pend) | set(usados)
    nuevos = [i for i in ids if i not in conocidos]  # elementos agregados al sitio a mitad de ciclo
    rng.shuffle(nuevos)
    pend += nuevos

    elegidos = [i for i in prioridad if i in vivos][:n]
    for i in elegidos:  # salen del ciclo normal: ya cuentan como usados en esta vuelta
        if i in pend:
            pend.remove(i)
        if i in usados:
            usados.remove(i)
    usados += elegidos
    while len(elegidos) < n:
        if not pend:  # se acabó el catálogo: nueva vuelta, mezclada
            pend = [i for i in usados if i not in elegidos]
            rng.shuffle(pend)
            pend += elegidos  # los de hoy quedan al final de la nueva vuelta
            usados = []
            ciclo["vueltas"] += 1
        i = pend.pop(0)
        if i in elegidos:
            continue
        elegidos.append(i)
        usados.append(i)
    ciclo["pendientes"], ciclo["usados"] = pend, usados
    return elegidos


def novedades(estado, clave, ids_orden, fecha, cfg, iniciales=0):
    """Detecta elementos nuevos del catálogo. `ids_orden` va del más nuevo al más viejo.

    - Un id que nunca se había visto es "nuevo" y queda en la lista de prioritarios durante
      `dias_prioridad_nuevos` días (14 por defecto) o hasta que se incluya en un plan.
    - La primera vez que corre no hay historial: se toman como nuevos los `iniciales` más recientes
      y el resto se da por conocido (así no salen 300 productos "nuevos" de golpe).
    Devuelve los ids nuevos pendientes, del más nuevo al más viejo.
    """
    reg = estado.setdefault("novedades", {}).setdefault(clave, {})
    hoy = date.fromisoformat(fecha)
    if "conocidos" not in reg:
        reg["conocidos"] = [i for i in ids_orden[iniciales:]]
        reg["pendientes"] = {i: fecha for i in ids_orden[:iniciales]}
    conocidos = set(reg["conocidos"])
    for i in ids_orden:
        if i not in conocidos and i not in reg["pendientes"]:
            reg["pendientes"][i] = fecha
    vivos = set(ids_orden)
    limite = cfg.get("dias_prioridad_nuevos", 14)
    vigentes, vencidos = {}, []
    for i, desde in reg["pendientes"].items():
        if i in vivos and (hoy - date.fromisoformat(desde)).days <= limite:
            vigentes[i] = desde
        else:
            vencidos.append(i)
    reg["pendientes"] = vigentes
    reg["conocidos"] = sorted(conocidos | set(vencidos))
    return [i for i in ids_orden if i in vigentes]


def marcar_atendidos(estado, clave, ids):
    reg = estado["novedades"][clave]
    for i in ids:
        reg["pendientes"].pop(i, None)
    reg["conocidos"] = sorted(set(reg["conocidos"]) | set(ids))


def plan_del_dia(estado, fecha, catalogo, cfg, rng=None):
    """Devuelve (creando si hace falta) el plan del día: orden de ids intercalando servicios y productos.

    Los productos nuevos publicados en la tienda entran primero en los cupos de productos del día.
    """
    rng = rng or random.Random()
    dias = estado.setdefault("dias", {})
    if fecha in dias:
        return dias[fecha]
    prod_ids = list(catalogo["producto"])  # orden de la API: del más nuevo al más viejo
    nuevos = novedades(estado, "producto", prod_ids, fecha, cfg, iniciales=cfg.get("nuevos_al_iniciar", 3))
    s = tomar(estado, "servicio", list(catalogo["servicio"]), cfg["servicios_por_dia"], rng)
    p = tomar(estado, "producto", prod_ids, cfg["productos_por_dia"], rng, prioridad=nuevos)
    atendidos = [i for i in p if i in nuevos]
    marcar_atendidos(estado, "producto", atendidos)
    orden = []
    for i in range(max(len(s), len(p))):
        if i < len(s):
            orden.append(s[i])
        if i < len(p):
            orden.append(p[i])
    dias[fecha] = {"orden": orden, "items": {}, "publicado": {}, "nuevos": atendidos}
    for viejo in sorted(dias)[:-DIAS_A_GUARDAR]:
        del dias[viejo]
    return dias[fecha]


def copia(estado):
    return copy.deepcopy(estado)
