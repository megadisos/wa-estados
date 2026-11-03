"""Convierte la foto del servicio/producto (o la imagen de la promo) en una imagen vertical 9:16 lista para Estados."""
from io import BytesIO

import requests
from PIL import Image, ImageDraw, ImageFilter, ImageFont, ImageOps

W, H = 1080, 1920
NEGRITA = [
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
    "/usr/share/fonts/TTF/DejaVuSans-Bold.ttf",
    "C:/Windows/Fonts/arialbd.ttf",
]
CABECERAS = {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/124.0 Safari/537.36"}


def _fuente(tam):
    for ruta in NEGRITA:
        try:
            return ImageFont.truetype(ruta, tam)
        except OSError:
            continue
    try:
        return ImageFont.load_default(size=tam)
    except TypeError:
        return ImageFont.load_default()


def _envolver(draw, texto, fuente, ancho, max_lineas):
    lineas, actual = [], ""
    for palabra in texto.split():
        prueba = f"{actual} {palabra}".strip()
        if draw.textlength(prueba, font=fuente) <= ancho:
            actual = prueba
        else:
            if actual:
                lineas.append(actual)
            actual = palabra
    if actual:
        lineas.append(actual)
    if len(lineas) > max_lineas:
        lineas = lineas[:max_lineas]
        lineas[-1] = lineas[-1].rstrip(" .,;:") + "..."
    return lineas


def crear_tarjeta(item, ruta_salida):
    r = requests.get(item["imagen"], headers=CABECERAS, timeout=45)
    r.raise_for_status()
    foto = ImageOps.exif_transpose(Image.open(BytesIO(r.content))).convert("RGB")

    fondo = ImageOps.fit(foto, (W, H), Image.LANCZOS).filter(ImageFilter.GaussianBlur(45))
    fondo = Image.blend(fondo, Image.new("RGB", (W, H), (10, 10, 24)), 0.5)
    d = ImageDraw.Draw(fondo)

    if item.get("tipo") == "promo":
        # La imagen de la promo ya trae su diseño y textos: se muestra completa y grande, sin taparla.
        d.text((W // 2, 130), "PROMO DE LA SEMANA", font=_fuente(64), fill=(255, 205, 64), anchor="mm")
        principal = ImageOps.contain(foto, (W - 60, H - 380), Image.LANCZOS)
        mascara = Image.new("L", principal.size, 0)
        ImageDraw.Draw(mascara).rounded_rectangle((0, 0, *principal.size), 36, fill=255)
        x, y = (W - principal.width) // 2, 230 + (H - 380 - principal.height) // 2
        fondo.paste(principal, (x, y), mascara)
        d.text((W // 2, H - 90), "CUSTOMANIA", font=_fuente(52), fill="white", anchor="mm")
        ruta_salida.parent.mkdir(parents=True, exist_ok=True)
        fondo.save(ruta_salida, "JPEG", quality=92)
        return ruta_salida

    d.text((W // 2, 140), "CUSTOMANIA", font=_fuente(58), fill="white", anchor="mm")

    caja = (960, 1140)
    principal = ImageOps.contain(foto, caja, Image.LANCZOS)
    mascara = Image.new("L", principal.size, 0)
    ImageDraw.Draw(mascara).rounded_rectangle((0, 0, *principal.size), 40, fill=255)
    x, y = (W - principal.width) // 2, 240 + (caja[1] - principal.height) // 2
    fondo.paste(principal, (x, y), mascara)

    f_titulo, ancho = _fuente(62), W - 140
    y_txt = 1450
    for linea in _envolver(d, item["titulo"], f_titulo, ancho, 3):
        d.text((W // 2, y_txt), linea, font=f_titulo, fill="white", anchor="mm")
        y_txt += 78
    if item.get("precio"):
        tam = 66
        while tam > 34 and d.textlength(item["precio"], font=_fuente(tam)) > W - 140:
            tam -= 4
        d.text((W // 2, y_txt + 30), item["precio"], font=_fuente(tam), fill=(255, 205, 64), anchor="mm")

    ruta_salida.parent.mkdir(parents=True, exist_ok=True)
    fondo.save(ruta_salida, "JPEG", quality=92)
    return ruta_salida
