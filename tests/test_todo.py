"""Pruebas sin internet ni WhatsApp real: rotación, filtros, textos, imagen y el flujo del navegador contra una página simulada."""
import os
import random
import sys
from collections import Counter
from io import BytesIO
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import catalogo  # noqa: E402
import rotacion  # noqa: E402
import tarjeta  # noqa: E402
import textos  # noqa: E402

CFG = {
    "sitio": "https://customania.com.co",
    "url_whatsapp": "https://customania.com.co/wa",
    "excluir_productos": ["medalla", "trofeo"],
    "textos": {
        "servicio": "{titulo}\n{descripcion}\nCotiza: {wa}\n{url}",
        "producto": "{titulo}\n{precio}\nComprar: {url}",
    },
}


def test_rotacion_no_repite_hasta_agotar():
    rng, estado = random.Random(7), {}
    ids = [f"servicio:s{i}" for i in range(7)]
    dias = [rotacion.tomar(estado, "servicio", ids, 3, rng) for _ in range(14)]
    for d in dias:
        assert len(set(d)) == 3, "el mismo día no debe repetir"
    # las primeras 2 vueltas completas (7 ids) -> cada id sale exactamente 2 veces en 42/... usamos ventanas de 7 elementos
    plano = [i for d in dias for i in d]
    assert Counter(plano[:7]).most_common(1)[0][1] == 1
    assert Counter(plano[7:14]).most_common(1)[0][1] == 1
    assert max(Counter(plano).values()) - min(Counter(plano).values()) <= 1


def test_rotacion_catalogo_mas_chico_que_el_cupo():
    estado = {}
    assert len(rotacion.tomar(estado, "x", ["a", "b"], 3, random.Random(1))) == 2


def test_rotacion_agrega_nuevos_y_quita_borrados():
    rng, estado = random.Random(3), {}
    ids = [f"p{i}" for i in range(6)]
    rotacion.tomar(estado, "p", ids, 3, rng)
    ids2 = ids[1:] + ["nuevo"]  # se borra p0, aparece "nuevo"
    sig = rotacion.tomar(estado, "p", ids2, 3, rng)
    assert "p0" not in sig and len(set(sig)) == 3
    sig2 = rotacion.tomar(estado, "p", ids2, 3, rng)
    assert "nuevo" in sig + sig2  # el nuevo entra dentro de la vuelta actual (queda al final de la cola)


def test_plan_del_dia_es_idempotente_e_intercala():
    cat = {"servicio": {f"servicio:s{i}": {} for i in range(5)}, "producto": {f"producto:{i}": {} for i in range(9)}}
    cfg = {"servicios_por_dia": 3, "productos_por_dia": 3}
    estado = {}
    d1 = rotacion.plan_del_dia(estado, "2026-09-22", cat, cfg, random.Random(1))
    d1b = rotacion.plan_del_dia(estado, "2026-09-22", cat, cfg, random.Random(99))
    assert d1 is d1b and len(d1["orden"]) == 6
    assert [i.split(":")[0] for i in d1["orden"]] == ["servicio", "producto"] * 3


def _prod(nombre, cats, precio="3000000", regular=None, stock=True, imgs=True):
    return {
        "id": 1,
        "name": nombre,
        "slug": nombre.lower().replace(" ", "-"),
        "is_in_stock": stock,
        "short_description": "<p>Linda   descripción</p>",
        "categories": [{"name": c, "slug": c.lower()} for c in cats],
        "images": [{"src": "https://x/y.webp"}] if imgs else [],
        "prices": {"price": precio, "regular_price": regular or precio, "currency_minor_unit": 2},
    }


def test_filtro_y_precio_de_productos():
    assert catalogo._item_producto_api(_prod("Medalla Sol ABS", ["Medallas"]), CFG) is None
    assert catalogo._item_producto_api(_prod("Trofeo Win Star", ["Trofeos"]), CFG) is None
    assert catalogo._item_producto_api(_prod("Mug", ["Mugs"], stock=False), CFG) is None
    assert catalogo._item_producto_api(_prod("Mug", ["Mugs"], imgs=False), CFG) is None
    it = catalogo._item_producto_api(_prod("Mug Mago", ["Mugs"], "3000000", "4000000"), CFG)
    assert it["precio"] == "$30.000 (antes $40.000)"
    assert it["url"] == "https://customania.com.co/store/mug-mago"
    assert it["descripcion"] == "Linda descripción"
    it2 = catalogo._item_producto_api(_prod("Gorra", ["Gorras"], "3500000"), CFG)
    assert it2["precio"] == "$35.000"


def test_textos_omiten_lineas_vacias():
    item = {"tipo": "producto", "titulo": "Mug", "precio": "", "url": "https://u"}
    assert textos.caption(item, {}, CFG) == "Mug\nComprar: https://u"
    serv = {"tipo": "servicio", "titulo": "DTF", "descripcion": "Texto", "url": "https://s"}
    assert textos.caption(serv, {}, CFG) == "DTF\nTexto\nCotiza: https://customania.com.co/wa\nhttps://s"
    propio = {"textos": {"servicio": "Hola {titulo}"}}
    assert textos.caption(serv, propio, CFG) == "Hola DTF"


def test_tarjeta_vertical(tmp_path, monkeypatch):
    from PIL import Image

    buf = BytesIO()
    Image.new("RGB", (1024, 1024), (200, 30, 90)).save(buf, "WEBP")

    class R:
        content = buf.getvalue()

        def raise_for_status(self):
            pass

    monkeypatch.setattr(tarjeta.requests, "get", lambda *a, **k: R())
    item = {"tipo": "producto", "titulo": "Camisetas de Pareja Flork Enamorados Blanco Edición Especial", "precio": "$80.000 (antes $100.000)", "imagen": "x"}
    salida = tarjeta.crear_tarjeta(item, tmp_path / "t.jpg")
    assert Image.open(salida).size == (1080, 1920)


MOCK = """<!doctype html><meta charset=utf-8><body>
<div id="pane-side">chats</div>
<button aria-label="Estados" onclick="document.getElementById('st').style.display='block'">Estados</button>
<div id="st" style="display:none">
  <button aria-label="Agregar estado" onclick="document.getElementById('menu').style.display='block'">+</button>
  <ul id="menu" style="display:none"><li aria-label="Fotos y videos" onclick="document.getElementById('f').click()">Fotos y videos</li></ul>
</div>
<input id="f" type="file" accept="image/*" style="display:none"
  onchange="document.getElementById('ed').style.display='block'; window.__archivo=this.files[0].name">
<div id="ed" style="display:none">
  <div contenteditable="true" aria-label="Añade un comentario" style="border:1px solid #000;min-height:40px"></div>
  <button aria-label="Enviar" onclick="window.__posted=document.querySelector('#ed [contenteditable]').innerText; document.getElementById('ed').style.display='none'">Enviar</button>
</div></body>"""


def test_flujo_del_navegador_contra_pagina_simulada(tmp_path):
    from PIL import Image
    from playwright.sync_api import sync_playwright

    html = tmp_path / "mock.html"
    html.write_text(MOCK, encoding="utf-8")
    os.environ["WA_URL"] = html.as_uri()
    import importlib

    import whatsapp

    importlib.reload(whatsapp)
    whatsapp.DATOS = tmp_path
    foto = tmp_path / "foto.jpg"
    Image.new("RGB", (300, 500), "blue").save(foto)
    cuenta = {"nombre": "prueba", "perfil": str(tmp_path / "perfil")}
    with sync_playwright() as pw, whatsapp.Sesion(pw, cuenta, {"zona_horaria": "America/Bogota"}, headless=True, depurar=True) as s:
        s.esperar_listo(timeout_s=30)
        s.ir_a_estados()
        s.publicar_imagen(foto, "Linea uno\nLinea dos con ñ y tilde á")
        assert s.page.evaluate("window.__archivo") == "foto.jpg"
        assert s.page.evaluate("window.__posted") == "Linea uno\nLinea dos con ñ y tilde á"


def test_login_requerido_se_detecta(tmp_path):
    from playwright.sync_api import sync_playwright

    html = tmp_path / "qr.html"
    html.write_text('<div data-ref="abc"><canvas aria-label="Scan this QR code"></canvas></div>', encoding="utf-8")
    os.environ["WA_URL"] = html.as_uri()
    import importlib

    import whatsapp

    importlib.reload(whatsapp)
    whatsapp.DATOS = tmp_path
    cuenta = {"nombre": "qr", "perfil": str(tmp_path / "perfil")}
    with sync_playwright() as pw, whatsapp.Sesion(pw, cuenta, {}, headless=True) as s:
        try:
            s.esperar_listo(timeout_s=60)
            raise AssertionError("debió pedir login")
        except whatsapp.NecesitaLogin:
            pass
