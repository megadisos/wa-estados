"""Arma el texto (caption) de cada estado a partir de las plantillas de config.toml."""
import re

CAMPOS = re.compile(r"\{(\w+)\}")
# Por si config.toml no trae la plantilla de la promo
POR_DEFECTO = {"promo": "PROMO DE LA SEMANA\n{titulo}\nPídela aquí: {url}"}


def renderizar(plantilla, item, cfg):
    datos = {
        "titulo": item.get("titulo", ""),
        "descripcion": item.get("descripcion", ""),
        "precio": item.get("precio", ""),
        "url": item.get("url", ""),
        "wa": cfg.get("url_whatsapp", ""),
    }
    lineas = []
    for linea in plantilla.split("\n"):
        campos = CAMPOS.findall(linea)
        if campos and any(not datos.get(c) for c in campos):
            continue  # una línea con un dato vacío se omite completa
        lineas.append(CAMPOS.sub(lambda m: datos.get(m.group(1), ""), linea).strip())
    return "\n".join(lineas).strip()


def caption(item, cuenta, cfg):
    propios = cuenta.get("textos", {})
    plantilla = propios.get(item["tipo"]) or cfg["textos"].get(item["tipo"]) or POR_DEFECTO.get(item["tipo"], "{titulo}")
    return renderizar(plantilla, item, cfg)
