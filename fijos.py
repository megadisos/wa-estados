"""Estados fijos: se publican TODOS los días con su propia imagen (no entran en la rotación).

Se configuran en config.toml con bloques [[fijos]] y se pueden activar, desactivar o cambiarles el texto
desde la app (ajuste "fijos").
"""
from util import BASE

PREFIJO = "fijo:"
AUTOMATICOS = ("promo:", PREFIJO)  # ids que no se eligen a mano en el plan


def activos(cfg):
    return [f for f in cfg.get("fijos", []) if f.get("activo", True) and f.get("id")]


def ruta(f):
    return BASE / f["imagen"]


def item(f):
    return {
        "id": PREFIJO + f["id"],
        "tipo": "fijo",
        "titulo": f.get("titulo") or f["id"],
        "descripcion": f.get("descripcion", ""),
        "url": f.get("url", ""),
        "imagen": f"/api/fijo?id={f['id']}",  # la app la pide al agente
        "archivo": f["imagen"],
        "texto": f.get("texto") or "{titulo}\n{url}",
    }


def _colocar(orden, id_, posicion):
    if id_ in orden:
        return
    if posicion == "primero":
        orden.insert(0, id_)
    elif posicion == "ultimo":
        orden.append(id_)
    else:  # "despues_promo": después de la promo y de los otros fijos del inicio
        i = 0
        while i < len(orden) and orden[i].startswith(AUTOMATICOS):
            i += 1
        orden.insert(i, id_)


def agregar(dia, cfg):
    """Pone en el plan del día los fijos activos (con sus datos actuales) y quita los desactivados que no salieron."""
    vigentes = set()
    for f in activos(cfg):
        it = item(f)
        vigentes.add(it["id"])
        dia["items"][it["id"]] = it
        _colocar(dia["orden"], it["id"], f.get("posicion", "despues_promo"))
    publicados = {i for hechos in dia.get("publicado", {}).values() for i in hechos}
    for i in list(dia["orden"]):
        if i.startswith(PREFIJO) and i not in vigentes and i not in publicados:
            dia["orden"].remove(i)
            dia["items"].pop(i, None)
