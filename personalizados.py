"""Estados personalizados: una imagen y un texto propios que se suben desde la app para un día concreto.

No vienen de la página: se guardan en datos/personalizados/ y entran al plan de ese día como un estado más
(se pueden mover, quitar o cambiarles el texto desde la app mientras no se hayan publicado).
"""
import io
import uuid

from util import DATOS

PREFIJO = "propio:"
TIPO = "personalizado"
CARPETA = DATOS / "personalizados"
LADO_MAXIMO = 2048  # px; WhatsApp las reduce de todas formas
MAX_TEXTO = 1500


def es(id_):
    return id_.startswith(PREFIJO)


def ruta(item):
    return CARPETA / item["foto"]


def _titulo(texto):
    primera = next((l.strip() for l in texto.splitlines() if l.strip()), "")
    if not primera:
        return "Estado personalizado"
    return primera if len(primera) <= 60 else primera[:57].rstrip() + "..."


def item(id_, foto, texto):
    return {
        "id": id_,
        "tipo": TIPO,
        "titulo": _titulo(texto),
        "texto": texto,
        "foto": foto,
        "url": "",
        "imagen": f"/api/propio?id={id_}",  # la app la pide al agente
    }


def guardar_imagen(datos):
    """Valida la imagen subida y la guarda como JPEG (derecha, sin transparencias). Devuelve el nombre del archivo."""
    from PIL import Image, ImageOps, UnidentifiedImageError

    try:
        img = Image.open(io.BytesIO(datos))
        img.load()
    except (UnidentifiedImageError, OSError) as e:
        raise ValueError("El archivo no es una imagen válida (usa JPG, PNG o WEBP)") from e
    img = ImageOps.exif_transpose(img)
    if img.mode in ("RGBA", "LA", "P"):
        img = img.convert("RGBA")
        fondo = Image.new("RGB", img.size, "white")
        fondo.paste(img, mask=img.split()[-1])
        img = fondo
    else:
        img = img.convert("RGB")
    img.thumbnail((LADO_MAXIMO, LADO_MAXIMO))
    CARPETA.mkdir(parents=True, exist_ok=True)
    nombre = uuid.uuid4().hex[:12] + ".jpg"
    img.save(CARPETA / nombre, "JPEG", quality=90)
    return nombre


def limpiar_texto(texto):
    texto = str(texto or "").replace("\r\n", "\n").strip()
    if len(texto) > MAX_TEXTO:
        raise ValueError(f"El texto es muy largo (máximo {MAX_TEXTO} caracteres)")
    return texto


def agregar(dia, datos_imagen, texto):
    """Suma al final del plan del día un estado con esta imagen y texto. Devuelve su id."""
    texto = limpiar_texto(texto)
    foto = guardar_imagen(datos_imagen)
    id_ = PREFIJO + foto.rsplit(".", 1)[0]
    dia["items"][id_] = item(id_, foto, texto)
    dia["orden"].append(id_)
    dia["editado"] = True
    return id_


def cambiar_texto(dia, id_, texto):
    it = dia["items"].get(id_)
    if not es(id_) or not it or id_ not in dia["orden"]:
        raise KeyError(id_)
    if any(id_ in hechos for hechos in dia.get("publicado", {}).values()):
        raise ValueError("Ese estado ya se publicó; ya no se le puede cambiar el texto")
    dia["items"][id_] = item(id_, it["foto"], limpiar_texto(texto))
    return dia["items"][id_]


def buscar(estado, id_):
    """El item de un estado personalizado en cualquier día guardado (para servir su imagen)."""
    for dia in estado.get("dias", {}).values():
        it = dia.get("items", {}).get(id_)
        if it and es(id_):
            return it
    return None


def limpiar(estado):
    """Borra las imágenes que ya no usa ningún día guardado (quitadas del plan o de días viejos)."""
    if not CARPETA.exists():
        return
    usadas = {it.get("foto") for dia in estado.get("dias", {}).values()
              for i, it in dia.get("items", {}).items() if es(i)}
    for f in CARPETA.iterdir():
        if f.is_file() and f.name not in usadas:
            f.unlink(missing_ok=True)
