"""Pruebas del control desde la app: pausa, ajustes, cambio de plan y la API del agente."""
import json
import random
import sys
import threading
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import agente  # noqa: E402
import catalogo  # noqa: E402
import rotacion  # noqa: E402
import util  # noqa: E402

CAT = {
    "servicio": {f"servicio:s{i}": {"id": f"servicio:s{i}", "tipo": "servicio", "slug": f"s{i}", "url": f"https://x/servicios/s{i}"} for i in range(5)},
    "producto": {
        f"producto:{i}": {
            "id": f"producto:{i}",
            "tipo": "producto",
            "item": {"id": f"producto:{i}", "tipo": "producto", "titulo": f"Producto {i}", "precio": "$1.000",
                     "url": f"https://x/store/{i}", "imagen": f"https://x/{i}.jpg", "categorias": ["Mugs"]},
        }
        for i in range(9)
    },
}


def test_cambiar_plan_ajusta_la_rotacion():
    estado = {}
    cfg = {"servicios_por_dia": 2, "productos_por_dia": 2}
    dia = rotacion.plan_del_dia(estado, "2026-11-04", CAT, cfg, random.Random(1))
    dia["orden"].insert(0, "promo:mugs")
    viejo_prod = [i for i in dia["orden"] if i.startswith("producto:")]
    libre = next(i for i in CAT["producto"] if i not in viejo_prod)
    nuevo = [i for i in dia["orden"] if i.startswith("servicio:")] + [viejo_prod[0], libre]
    rotacion.cambiar_plan(estado, "2026-11-04", nuevo)
    assert dia["orden"][0] == "promo:mugs" and dia["orden"][1:] == nuevo
    ciclo = estado["ciclos"]["producto"]
    assert ciclo["pendientes"][0] == viejo_prod[1]  # el quitado vuelve al frente de la cola
    assert libre in ciclo["usados"] and libre not in ciclo["pendientes"]
    assert dia["editado"]


def test_cambiar_plan_no_quita_lo_publicado():
    estado = {}
    dia = rotacion.plan_del_dia(estado, "2026-11-04", CAT, {"servicios_por_dia": 1, "productos_por_dia": 1}, random.Random(2))
    dia["publicado"]["personal"] = {dia["orden"][0]: "ok"}
    with pytest.raises(ValueError):
        rotacion.cambiar_plan(estado, "2026-11-04", dia["orden"][1:])


def test_ajustes_de_la_app_se_aplican_encima():
    cfg = {"productos_por_dia": 3, "promo_semana": {"activa": True, "posicion": "primero"},
           "cuentas": [{"nombre": "personal", "activa": True}, {"nombre": "customania", "activa": True}]}
    util.aplicar_ajustes(cfg, {"productos_por_dia": 1, "promo_semana": {"activa": False}, "cuentas_activas": {"personal": False}})
    assert cfg["productos_por_dia"] == 1
    assert cfg["promo_semana"] == {"activa": False, "posicion": "primero"}
    assert [c["activa"] for c in cfg["cuentas"]] == [False, True]


def test_pausa_con_fecha_se_reanuda_sola(tmp_path, monkeypatch):
    monkeypatch.setattr(util, "CONTROL", tmp_path / "control.json")
    assert util.pausa_activa("2026-11-04") is None
    util.escribir_json(util.CONTROL, {"pausado": True, "hasta": "2026-11-05"})
    assert util.pausa_activa("2026-11-05")
    assert util.pausa_activa("2026-11-06") is None
    util.escribir_json(util.CONTROL, {"pausado": True, "hasta": None})
    assert util.pausa_activa("2030-01-01")


def test_dormir_se_interrumpe_al_detener(tmp_path, monkeypatch):
    monkeypatch.setattr(util, "DETENER", tmp_path / "detener.flag")
    (tmp_path / "detener.flag").write_text("x")
    with pytest.raises(util.Detenido):
        util.dormir(30)


def test_excluir_categorias():
    p = {"id": 5, "name": "Gorra", "slug": "gorra", "categories": [{"name": "Gorras", "slug": "gorras"}],
         "images": [{"src": "https://x/g.jpg"}], "prices": {"price": "100", "currency_minor_unit": 0}}
    cfg = {"sitio": "https://x", "excluir_productos": []}
    assert catalogo._item_producto_api(p, cfg)["categorias"] == ["Gorras"]
    assert catalogo._item_producto_api(p, {**cfg, "excluir_categorias": ["GORRAS"]}) is None


# ---------------------------------------------------------------- API HTTP
@pytest.fixture
def api(tmp_path, monkeypatch):
    datos = tmp_path / "datos"
    (datos / "logs").mkdir(parents=True)
    for mod in (util, agente):
        for nombre, archivo in [("AJUSTES_APP", "ajustes_app.json"), ("CONTROL", "control.json"), ("DETENER", "detener.flag"),
                                ("EJECUCION", "ejecucion.json"), ("HISTORIAL", "historial.jsonl")]:
            monkeypatch.setattr(mod, nombre, datos / archivo, raising=False)
    monkeypatch.setattr(agente, "DATOS", datos)
    monkeypatch.setattr(agente, "LOG_ESTADOS", datos / "logs" / "estados.log")
    monkeypatch.setattr(agente, "LOG_SALIDA", datos / "logs" / "ultima_ejecucion.txt")
    monkeypatch.setattr(rotacion, "DATOS", datos)
    monkeypatch.setattr(rotacion, "ARCHIVO", datos / "estado.json")
    monkeypatch.setattr(agente.catalogo, "listar", lambda cfg: json.loads(json.dumps(CAT)))
    ag = agente.Agente()
    srv = ThreadingHTTPServer(("127.0.0.1", 0), agente.crear_manejador(ag, "secreta"))
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{srv.server_address[1]}"

    def llamar(metodo, ruta, cuerpo=None, clave="secreta"):
        datos_req = json.dumps(cuerpo).encode() if cuerpo is not None else None
        req = urllib.request.Request(base + ruta, data=datos_req, method=metodo,
                                     headers={"Authorization": f"Bearer {clave}", "Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=10) as r:
                return r.status, json.loads(r.read())
        except urllib.error.HTTPError as e:
            return e.code, json.loads(e.read())

    yield llamar, datos
    srv.shutdown()


def test_api_requiere_clave(api):
    llamar, _ = api
    assert llamar("GET", "/api/ping", clave="")[0] == 200
    assert llamar("GET", "/api/estado", clave="mala")[0] == 401
    codigo, est = llamar("GET", "/api/estado")
    assert codigo == 200 and est["pausado"] is False and est["ejecucion"]["en_curso"] is False


def test_api_pausa(api):
    llamar, _ = api
    assert llamar("POST", "/api/pausa", {"pausado": True})[0] == 200
    assert llamar("GET", "/api/estado")[1]["pausado"] is True
    llamar("POST", "/api/pausa", {"pausado": False})
    assert llamar("GET", "/api/estado")[1]["pausado"] is False


def test_api_plan_crear_y_cambiar(api):
    llamar, datos = api
    codigo, plan = llamar("GET", "/api/plan?fecha=2099-01-01")
    assert codigo == 200 and plan["existe"] is False
    codigo, plan = llamar("POST", "/api/plan", {"fecha": "2099-01-01"})
    assert codigo == 200 and len(plan["items"]) == 6
    assert all(it["titulo"] for it in plan["items"])
    ids = [it["id"] for it in plan["items"]]
    otro = next(i for i in CAT["producto"] if i not in ids)
    codigo, plan2 = llamar("PUT", "/api/plan", {"fecha": "2099-01-01", "ids": ids[:2] + [otro]})
    assert codigo == 200 and [it["id"] for it in plan2["items"]] == ids[:2] + [otro]
    assert llamar("PUT", "/api/plan", {"fecha": "2099-01-01", "ids": ["producto:noexiste"]})[0] == 400
    assert json.loads((datos / "estado.json").read_text())["dias"]["2099-01-01"]["editado"] is True


def test_api_ajustes(api):
    llamar, datos = api
    codigo, aj = llamar("PUT", "/api/ajustes", {"cambios": {"productos_por_dia": 2, "excluir_categorias": ["gorras", " "]}})
    assert codigo == 200 and aj["productos_por_dia"] == 2 and aj["excluir_categorias"] == ["gorras"]
    assert llamar("PUT", "/api/ajustes", {"cambios": {"productos_por_dia": 99}})[0] == 400
    assert llamar("PUT", "/api/ajustes", {"cambios": {"tienda_api": "x"}})[0] == 400
    assert json.loads((datos / "ajustes_app.json").read_text()) == {"productos_por_dia": 2, "excluir_categorias": ["gorras"]}
    codigo, aj = llamar("PUT", "/api/ajustes", {"restablecer": True})
    assert aj["modificados_desde_app"] == []


def test_api_log_e_historial(api):
    llamar, datos = api
    (datos / "logs" / "estados.log").write_text("linea 1\n", encoding="utf-8")
    _, r = llamar("GET", "/api/log")
    assert r["texto"] == "linea 1\n"
    with open(datos / "logs" / "estados.log", "a", encoding="utf-8") as f:
        f.write("linea 2\n")
    _, r2 = llamar("GET", f"/api/log?desde={r['offset']}")
    assert r2["texto"] == "linea 2\n"
    util.registrar_historial({"fecha": "2099-01-01", "cuenta": "personal", "id": "producto:1", "resultado": "ok"})
    _, h = llamar("GET", "/api/historial?dias=36500")
    assert h and h[0]["id"] == "producto:1"


def test_api_detener_sin_ejecucion(api):
    llamar, _ = api
    assert llamar("POST", "/api/detener", {})[0] == 409


# ---------------------------------------------------------------- publicar.py con la app
class _Nada:
    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


@pytest.fixture
def publicar_falso(tmp_path, monkeypatch):
    """publicar.main() completo, con catálogo, imágenes y WhatsApp simulados."""
    import publicar

    datos = tmp_path / "datos"
    datos.mkdir()
    for mod in (util, publicar):
        for nombre, archivo in [("CONTROL", "control.json"), ("DETENER", "detener.flag"),
                                ("EJECUCION", "ejecucion.json"), ("HISTORIAL", "historial.jsonl")]:
            monkeypatch.setattr(mod, nombre, datos / archivo, raising=False)
    monkeypatch.setattr(util, "AJUSTES_APP", datos / "ajustes_app.json")
    monkeypatch.setattr(publicar, "DATOS", datos)
    monkeypatch.setattr(rotacion, "DATOS", datos)
    monkeypatch.setattr(rotacion, "ARCHIVO", datos / "estado.json")
    monkeypatch.setattr(publicar.catalogo, "listar", lambda cfg: json.loads(json.dumps(CAT)))
    monkeypatch.setattr(publicar.catalogo, "detalle", lambda ref, cfg: {"id": ref["id"], "tipo": ref["tipo"], "titulo": ref["id"], "url": "u"})
    monkeypatch.setattr(publicar, "crear_tarjeta", lambda item, ruta: None)
    monkeypatch.setattr(publicar, "agregar_promo", lambda dia, cfg: None)
    monkeypatch.setattr(publicar, "sync_playwright", lambda: _Nada())
    monkeypatch.setattr(publicar, "mantener_despierto", lambda: None)
    publicados = []

    class Sesion:
        detener_en_2 = False

        def __init__(self, pw, cuenta, cfg, **kw):
            self.cuenta = cuenta["nombre"]

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def esperar_listo(self):
            pass

        def ir_a_estados(self):
            pass

        def publicar_imagen(self, ruta, texto, enviar=True):
            publicados.append(self.cuenta)
            if len(publicados) == 2 and self.detener_en_2:
                util.DETENER.write_text("x")

    monkeypatch.setattr(publicar, "Sesion", Sesion)

    def correr(*args):
        monkeypatch.setattr(sys, "argv", ["publicar.py", "--sin-espera", "--forzar", *args])
        return publicar.main()

    return correr, datos, publicados, Sesion


def test_publicar_respeta_pausa_y_registra_historial(publicar_falso):
    correr, datos, publicados, _ = publicar_falso
    util.escribir_json(util.CONTROL, {"pausado": True, "hasta": None})
    assert correr() == 0 and publicados == []  # programada + pausa: no publica
    assert correr("--ignorar-pausa", "--cuenta", "personal") == 0  # botón "Ejecutar ahora"
    assert len(publicados) == 6  # 3 servicios + 3 productos (la promo está simulada fuera)
    info = json.loads((datos / "ejecucion.json").read_text())
    assert info["estado"] == "ok" and info["publicados"] == 6
    filas = [json.loads(x) for x in (datos / "historial.jsonl").read_text().splitlines()]
    assert len(filas) == 6 and {f["cuenta"] for f in filas} == {"personal"}


def test_publicar_se_detiene_desde_la_app(publicar_falso):
    correr, datos, publicados, Sesion = publicar_falso
    Sesion.detener_en_2 = True
    assert correr("--cuenta", "personal") == 3
    assert len(publicados) == 2
    info = json.loads((datos / "ejecucion.json").read_text())
    assert info["estado"] == "detenida" and info["publicados"] == 2
    assert not (datos / "detener.flag").exists()
