#!/usr/bin/env python3
"""Agente para controlar los Estados de WhatsApp desde la app del celular.

Corre en el mismo PC que publicar.py y expone una API HTTP pequeña, protegida con una clave:
estado, ejecutar ahora, detener, pausar la programación, ver y cambiar el plan de la próxima ejecución,
catálogo, categorías, historial, log en vivo y ajustes.

Uso:
    .venv\\Scripts\\python agente.py            (Windows; activar_agente.bat lo deja corriendo al iniciar sesión)
    .venv/bin/python agente.py                 (Linux)
    python agente.py --mostrar-clave           imprime la clave y sale

La clave se crea sola la primera vez en datos/agente_clave.txt. Se escribe en la app junto con la dirección
del PC (con Tailscale: http://<IP de Tailscale del PC>:8770).
"""
import argparse
import hmac
import json
import logging
import logging.handlers
import os
import secrets
import subprocess
import sys
import threading
import time
from contextlib import contextmanager
from datetime import datetime, timedelta
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse
from zoneinfo import ZoneInfo

import catalogo
import rotacion
from util import (
    AJUSTES_APP,
    BASE,
    CONTROL,
    DATOS,
    DETENER,
    EJECUCION,
    HISTORIAL,
    aplicar_ajustes,
    cargar_config,
    escribir_json,
    leer_json,
    pausa_activa,
)

VERSION = "1.0.0"
PUERTO = 8770
ARCHIVO_CLAVE = DATOS / "agente_clave.txt"
LOG_ESTADOS = DATOS / "logs" / "estados.log"
LOG_SALIDA = DATOS / "logs" / "ultima_ejecucion.txt"
NOMBRE_TAREA = "EstadosWhatsApp"

log = logging.getLogger("agente")


class ErrorApi(Exception):
    def __init__(self, mensaje, codigo=400):
        super().__init__(mensaje)
        self.codigo = codigo


# ---------------------------------------------------------------- utilidades
def clave():
    if ARCHIVO_CLAVE.exists():
        c = ARCHIVO_CLAVE.read_text(encoding="utf-8").strip()
        if c:
            return c
    DATOS.mkdir(parents=True, exist_ok=True)
    c = secrets.token_urlsafe(18)
    ARCHIVO_CLAVE.write_text(c, encoding="utf-8")
    return c


def proceso_vivo(pid):
    if not pid:
        return False
    if sys.platform == "win32":
        import ctypes

        k32 = ctypes.windll.kernel32
        h = k32.OpenProcess(0x1000, False, int(pid))  # PROCESS_QUERY_LIMITED_INFORMATION
        if not h:
            return False
        try:
            codigo = ctypes.c_ulong()
            k32.GetExitCodeProcess(h, ctypes.byref(codigo))
            return codigo.value == 259  # STILL_ACTIVE
        finally:
            k32.CloseHandle(h)
    try:
        os.kill(int(pid), 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def matar(pid):
    if sys.platform == "win32":
        subprocess.run(["taskkill", "/PID", str(pid), "/T", "/F"], capture_output=True)
    else:
        import signal

        try:
            os.kill(int(pid), signal.SIGTERM)
        except ProcessLookupError:
            pass


def _ahora(cfg):
    return datetime.now(ZoneInfo(cfg.get("zona_horaria", "America/Bogota")))


def _minutos(s):
    h, m = s.split(":")
    return int(h) * 60 + int(m)


class Agente:
    """Toda la lógica de la API, separada del servidor HTTP para poder probarla."""

    def __init__(self, python=None):
        self.python = python or sys.executable
        self.proceso = None
        self.mutex = threading.Lock()
        self._cache_catalogo = (0.0, None)
        self._cache_categorias = (0.0, None)
        self._cache_tarea = (0.0, None)

    # ------------------------------------------------------------ ejecución
    def ejecucion(self):
        info = leer_json(EJECUCION, {}) or {}
        vivo = False
        if self.proceso is not None and self.proceso.poll() is None:
            vivo = True
        elif info.get("estado") == "en_curso":
            vivo = proceso_vivo(info.get("pid"))
            if not vivo:
                info["estado"] = "interrumpida"  # el proceso murió sin cerrar su registro (apagón, cierre)
        info["en_curso"] = vivo
        info["deteniendo"] = vivo and DETENER.exists()
        return info

    def ejecutar(self, real=True, cuenta=None, ignorar_horario=False, sin_espera=True):
        with self.mutex:
            if self.ejecucion()["en_curso"]:
                raise ErrorApi("Ya hay una ejecución en curso", 409)
            cfg = cargar_config()
            if cuenta and cuenta not in [c["nombre"] for c in cfg.get("cuentas", [])]:
                raise ErrorApi(f"No existe la cuenta {cuenta}")
            args = [self.python, str(BASE / "publicar.py"), "--origen", "app", "--ignorar-pausa"]
            if not real:
                args.append("--dry-run")
            if cuenta:
                args += ["--cuenta", cuenta]
            if ignorar_horario:
                args.append("--forzar")
            if sin_espera:
                args.append("--sin-espera")
            LOG_SALIDA.parent.mkdir(parents=True, exist_ok=True)
            salida = open(LOG_SALIDA, "w", encoding="utf-8")
            salida.write(f"$ {' '.join(args[1:])}\n")
            salida.flush()
            extra = {}
            if sys.platform == "win32":
                extra["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.CREATE_NO_WINDOW
            env = {**os.environ, "PYTHONIOENCODING": "utf-8", "PYTHONUNBUFFERED": "1"}
            DETENER.unlink(missing_ok=True)
            self.proceso = subprocess.Popen(
                args, cwd=BASE, stdout=salida, stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL, env=env, **extra
            )
            proc = self.proceso
            threading.Thread(target=lambda: (proc.wait(), salida.close()), daemon=True).start()
            log.info("Ejecución lanzada desde la app: %s (pid %s)", " ".join(args[2:]), proc.pid)
            return {"pid": proc.pid, "comando": args[1:]}

    def detener(self, forzar=False):
        info = self.ejecucion()
        if not info["en_curso"]:
            raise ErrorApi("No hay ninguna ejecución en curso", 409)
        if not forzar:
            DETENER.parent.mkdir(parents=True, exist_ok=True)
            DETENER.write_text(datetime.now().isoformat(), encoding="utf-8")
            return {"mensaje": "Se detendrá al terminar el estado que está publicando"}
        pid = self.proceso.pid if self.proceso is not None and self.proceso.poll() is None else info.get("pid")
        matar(pid)
        reg = leer_json(EJECUCION, {}) or {}
        if reg.get("estado") == "en_curso":
            reg.update(estado="cancelada", fin=datetime.now().isoformat(timespec="seconds"), codigo=-1)
            escribir_json(EJECUCION, reg)
        DETENER.unlink(missing_ok=True)
        return {"mensaje": "Ejecución cancelada a la fuerza. Revisa el celular por si quedó un estado a medias."}

    # ------------------------------------------------------------ pausa
    def pausar(self, pausado, hasta=None):
        if hasta:
            datetime.strptime(hasta, "%Y-%m-%d")
        ctl = {"pausado": bool(pausado), "hasta": hasta if pausado else None, "cambiado": datetime.now().isoformat(timespec="seconds")}
        escribir_json(CONTROL, ctl)
        log.info("Pausa: %s", ctl)
        return ctl

    # ------------------------------------------------------------ estado general
    def proxima_programada(self):
        """Próxima ejecución del Programador de tareas de Windows (o None si no se puede saber)."""
        t, valor = self._cache_tarea
        if time.monotonic() - t < 300:
            return valor
        valor = None
        if sys.platform == "win32":
            ps = (
                f"$t=Get-ScheduledTask -TaskName '{NOMBRE_TAREA}' -ErrorAction SilentlyContinue;"
                f"if($t){{$i=Get-ScheduledTaskInfo -TaskName '{NOMBRE_TAREA}';"
                "@{activa=($t.State -ne 'Disabled');proxima=$i.NextRunTime.ToString('s');"
                "ultima=$i.LastRunTime.ToString('s')}|ConvertTo-Json}"
            )
            try:
                r = subprocess.run(
                    ["powershell", "-NoProfile", "-Command", ps],
                    capture_output=True, text=True, timeout=20, creationflags=subprocess.CREATE_NO_WINDOW,
                )
                if r.stdout.strip():
                    valor = json.loads(r.stdout)
            except Exception:  # noqa: BLE001
                log.exception("No pude leer la tarea programada")
        self._cache_tarea = (time.monotonic(), valor)
        return valor

    def fecha_proxima(self, cfg, estado=None):
        """Fecha de la próxima ejecución que publicará: hoy si falta algo por publicar hoy, si no mañana."""
        ahora = _ahora(cfg)
        hoy = ahora.strftime("%Y-%m-%d")
        manana = (ahora + timedelta(days=1)).strftime("%Y-%m-%d")
        if ahora.hour * 60 + ahora.minute > _minutos(cfg.get("no_publicar_despues", "23:59")):
            return manana
        estado = estado if estado is not None else rotacion.cargar()
        dia = estado.get("dias", {}).get(hoy)
        if not dia:
            return hoy
        cuentas = [c["nombre"] for c in cfg.get("cuentas", []) if c.get("activa", True)]
        if all(all(i in dia["publicado"].get(c, {}) for i in dia["orden"]) for c in cuentas):
            return manana
        return hoy

    def estado(self):
        cfg = cargar_config()
        ahora = _ahora(cfg)
        hoy = ahora.strftime("%Y-%m-%d")
        est = rotacion.cargar()
        dia = est.get("dias", {}).get(hoy)
        cuentas = []
        for c in cfg.get("cuentas", []):
            hechos = (dia or {}).get("publicado", {}).get(c["nombre"], {})
            cuentas.append({
                "nombre": c["nombre"],
                "activa": c.get("activa", True),
                "publicados_hoy": sum(1 for v in hechos.values() if v == "ok"),
                "inciertos_hoy": sum(1 for v in hechos.values() if v == "incierto"),
            })
        ctl = pausa_activa(hoy)
        return {
            "version": VERSION,
            "hora_pc": ahora.isoformat(timespec="seconds"),
            "pausado": bool(ctl),
            "pausa_hasta": (ctl or {}).get("hasta"),
            "ejecucion": self.ejecucion(),
            "tarea_programada": self.proxima_programada(),
            "hoy": {"fecha": hoy, "planificados": len(dia["orden"]) if dia else 0},
            "proxima_fecha": self.fecha_proxima(cfg, est),
            "cuentas": cuentas,
            "ventana": [cfg.get("no_publicar_antes", "00:00"), cfg.get("no_publicar_despues", "23:59")],
        }

    # ------------------------------------------------------------ catálogo
    def catalogo(self, refrescar=False):
        t, cat = self._cache_catalogo
        if refrescar or cat is None or time.monotonic() - t > 1800:
            cat = catalogo.listar(cargar_config())
            self._cache_catalogo = (time.monotonic(), cat)
        return cat

    def catalogo_api(self, refrescar=False):
        cat = self.catalogo(refrescar)
        return {
            "servicio": sorted((self._resumen_ref(r) for r in cat["servicio"].values()), key=lambda x: x["titulo"].lower()),
            "producto": [self._resumen_ref(r) for r in cat["producto"].values()],
        }

    @staticmethod
    def _resumen_ref(ref):
        it = ref.get("item") or {}
        return {
            "id": ref["id"],
            "tipo": ref["tipo"],
            "titulo": it.get("titulo") or ref.get("slug", ref["id"]).replace("-", " ").capitalize(),
            "precio": it.get("precio", ""),
            "imagen": it.get("imagen", ""),
            "url": it.get("url") or ref.get("url", ""),
            "categorias": it.get("categorias", []),
        }

    def categorias(self, refrescar=False):
        t, cats = self._cache_categorias
        cfg = cargar_config()
        if refrescar or cats is None or time.monotonic() - t > 1800:
            cats = catalogo.categorias(cfg)
            self._cache_categorias = (time.monotonic(), cats)
        excl = {c.lower() for c in cfg.get("excluir_categorias", [])}
        return [{**c, "excluida": c["slug"].lower() in excl} for c in cats]

    # ------------------------------------------------------------ plan
    def _resumen_plan(self, dia, fecha, cfg, cat=None):
        orden = []
        for id_ in dia["orden"]:
            it = dia["items"].get(id_)
            if not it and cat is not None:
                ref = cat.get(id_.split(":")[0], {}).get(id_)
                it = self._resumen_ref(ref) if ref else None
            it = it or {"id": id_, "tipo": id_.split(":")[0], "titulo": id_.split(":", 1)[1]}
            estados = {c: dia["publicado"].get(c, {}).get(id_) for c in dia["publicado"]}
            orden.append({
                "id": id_,
                "tipo": it.get("tipo", id_.split(":")[0]),
                "titulo": it.get("titulo", id_),
                "precio": it.get("precio", ""),
                "imagen": it.get("imagen", ""),
                "url": it.get("url", ""),
                "nuevo": id_ in dia.get("nuevos", []),
                "publicado": {c: v for c, v in estados.items() if v},
            })
        return {
            "fecha": fecha,
            "existe": True,
            "editado": dia.get("editado", False),
            "items": orden,
            "promo_activa": cfg.get("promo_semana", {}).get("activa", True),
            "promo_incluida": any(i.startswith("promo:") for i in dia["orden"]),
            "cuentas": {c: dict(v) for c, v in dia["publicado"].items()},
        }

    def plan(self, fecha=None, generar=False):
        cfg = cargar_config()
        est = rotacion.cargar()
        fecha = fecha or self.fecha_proxima(cfg, est)
        datetime.strptime(fecha, "%Y-%m-%d")
        dia = est.get("dias", {}).get(fecha)
        if not dia and not generar:
            return {"fecha": fecha, "existe": False, "items": [], "promo_activa": cfg.get("promo_semana", {}).get("activa", True)}
        cat = None
        if not dia:
            if fecha < _ahora(cfg).strftime("%Y-%m-%d"):
                raise ErrorApi("No se puede crear el plan de un día que ya pasó")
            cat = self.catalogo(refrescar=True)
            with self._bloqueo():
                est = rotacion.cargar()
                dia = rotacion.plan_del_dia(est, fecha, cat, cfg)
                rotacion.guardar(est)
            log.info("Plan de %s creado desde la app: %s", fecha, ", ".join(dia["orden"]))
        else:
            try:
                cat = self.catalogo()
            except Exception:  # noqa: BLE001
                cat = None
        return self._resumen_plan(dia, fecha, cfg, cat)

    def cambiar_plan(self, fecha, ids):
        if not isinstance(ids, list) or not all(isinstance(i, str) for i in ids):
            raise ErrorApi("'ids' debe ser una lista de textos")
        cfg = cargar_config()
        cat = self.catalogo()
        validos = set(cat["servicio"]) | set(cat["producto"])
        malos = [i for i in ids if not i.startswith("promo:") and i not in validos]
        if malos:
            raise ErrorApi(f"No están en el catálogo (o están excluidos): {', '.join(malos)}")
        if not [i for i in ids if not i.startswith("promo:")]:
            raise ErrorApi("El plan debe tener al menos un servicio o producto")
        with self._bloqueo():
            est = rotacion.cargar()
            if fecha not in est.get("dias", {}):
                raise ErrorApi("Ese día todavía no tiene plan; créalo primero", 404)
            try:
                dia = rotacion.cambiar_plan(est, fecha, ids)
            except ValueError as e:
                raise ErrorApi(str(e), 409) from e
            rotacion.guardar(est)
        log.info("Plan de %s cambiado desde la app: %s", fecha, ", ".join(dia["orden"]))
        return self._resumen_plan(dia, fecha, cfg, cat)

    def resolver_incierto(self, fecha, cuenta, id_, accion):
        if accion not in ("ok", "reintentar"):
            raise ErrorApi("accion debe ser 'ok' o 'reintentar'")
        with self._bloqueo():
            est = rotacion.cargar()
            hechos = est.get("dias", {}).get(fecha, {}).get("publicado", {}).get(cuenta, {})
            if hechos.get(id_) != "incierto":
                raise ErrorApi("Ese estado no está marcado como incierto", 404)
            if accion == "ok":
                hechos[id_] = "ok"
            else:
                del hechos[id_]  # la próxima ejecución de ese día lo vuelve a publicar
            rotacion.guardar(est)
        return {"mensaje": "Listo"}

    @contextmanager
    def _bloqueo(self):
        if self.ejecucion()["en_curso"]:
            raise ErrorApi("Hay una ejecución en curso; espera a que termine", 409)
        cm = rotacion.bloqueo()
        try:
            cm.__enter__()
        except SystemExit as e:
            raise ErrorApi("Hay una ejecución en curso; espera a que termine", 409) from e
        try:
            yield
        finally:
            cm.__exit__(None, None, None)

    # ------------------------------------------------------------ historial y log
    def historial(self, dias=30, cuenta=None):
        if not HISTORIAL.exists():
            return []
        limite = (datetime.now() - timedelta(days=dias)).strftime("%Y-%m-%d")
        filas = []
        with open(HISTORIAL, encoding="utf-8") as f:
            for linea in f:
                try:
                    r = json.loads(linea)
                except ValueError:
                    continue
                if r.get("fecha", "") >= limite and (not cuenta or r.get("cuenta") == cuenta):
                    filas.append(r)
        filas.reverse()
        return filas

    def log(self, archivo="estados", desde=-1, maximo=64_000):
        ruta = LOG_SALIDA if archivo == "salida" else LOG_ESTADOS
        if not ruta.exists():
            return {"texto": "", "offset": 0, "tamano": 0}
        tamano = ruta.stat().st_size
        if desde < 0 or desde > tamano:  # primera lectura, o el archivo rotó / se reinició
            desde = max(0, tamano - maximo)
        with open(ruta, "rb") as f:
            f.seek(desde)
            datos = f.read(maximo)
        texto = datos.decode("utf-8", "replace")
        return {"texto": texto, "offset": desde + len(datos), "tamano": tamano}

    # ------------------------------------------------------------ ajustes
    EDITABLES = {
        "servicios_por_dia": int,
        "productos_por_dia": int,
        "excluir_productos": list,
        "excluir_servicios": list,
        "excluir_categorias": list,
        "dias_prioridad_nuevos": int,
        "jitter_inicio_min": int,
        "pausa_entre_estados": list,
        "pausa_entre_cuentas": list,
        "no_publicar_antes": str,
        "no_publicar_despues": str,
        "promo_semana": dict,
        "textos": dict,
        "cuentas_activas": dict,
    }

    def ajustes(self):
        cfg = cargar_config()
        r = {k: cfg.get(k) for k in self.EDITABLES if k != "cuentas_activas"}
        r["excluir_categorias"] = cfg.get("excluir_categorias", [])
        r["promo_semana"] = {k: cfg.get("promo_semana", {}).get(k) for k in ("activa", "posicion", "forzar")}
        r["cuentas_activas"] = {c["nombre"]: c.get("activa", True) for c in cfg.get("cuentas", [])}
        r["modificados_desde_app"] = sorted((leer_json(AJUSTES_APP, {}) or {}).keys())
        return r

    def guardar_ajustes(self, cambios, restablecer=False):
        if restablecer:
            AJUSTES_APP.unlink(missing_ok=True)
            self._cache_catalogo = self._cache_categorias = (0.0, None)
            return self.ajustes()
        if not isinstance(cambios, dict):
            raise ErrorApi("Se esperaba un objeto con los ajustes")
        actuales = leer_json(AJUSTES_APP, {}) or {}
        for k, v in cambios.items():
            tipo = self.EDITABLES.get(k)
            if tipo is None:
                raise ErrorApi(f"El ajuste '{k}' no se puede cambiar desde la app")
            if tipo is int and isinstance(v, bool) or not isinstance(v, tipo):
                raise ErrorApi(f"'{k}' tiene un valor inválido")
            if k in ("servicios_por_dia", "productos_por_dia") and not 0 <= v <= 10:
                raise ErrorApi(f"'{k}' debe estar entre 0 y 10")
            if k in ("pausa_entre_estados", "pausa_entre_cuentas"):
                if len(v) != 2 or not all(isinstance(x, (int, float)) and x >= 0 for x in v) or v[0] > v[1]:
                    raise ErrorApi(f"'{k}' debe ser [mínimo, máximo] en segundos")
            if k in ("no_publicar_antes", "no_publicar_despues"):
                try:
                    datetime.strptime(v, "%H:%M")
                except ValueError as e:
                    raise ErrorApi(f"'{k}' debe tener formato HH:MM") from e
            if k in ("excluir_productos", "excluir_servicios", "excluir_categorias"):
                v = [str(x).strip() for x in v if str(x).strip()]
            if k == "promo_semana":
                v = {a: b for a, b in v.items() if a in ("activa", "posicion", "forzar")}
            if k == "textos":
                v = {a: str(b) for a, b in v.items() if a in ("servicio", "producto", "promo")}
            if isinstance(v, dict) and isinstance(actuales.get(k), dict):
                v = {**actuales[k], **v}
            actuales[k] = v
        aplicar_ajustes(cargar_config(ajustes=False), actuales)  # valida que se puedan aplicar
        escribir_json(AJUSTES_APP, actuales)
        self._cache_catalogo = self._cache_categorias = (0.0, None)
        log.info("Ajustes cambiados desde la app: %s", ", ".join(cambios))
        return self.ajustes()

    def promo(self):
        import promo

        return promo.detectar(cargar_config())


# ---------------------------------------------------------------- servidor HTTP
def crear_manejador(agente, clave_api):
    class Manejador(BaseHTTPRequestHandler):
        server_version = "AgenteEstados/" + VERSION

        def log_message(self, fmt, *a):  # noqa: N802
            log.debug("%s %s", self.address_string(), fmt % a)

        def _responder(self, codigo, datos):
            cuerpo = json.dumps(datos, ensure_ascii=False).encode("utf-8")
            self.send_response(codigo)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(cuerpo)))
            self.end_headers()
            self.wfile.write(cuerpo)

        def _cuerpo(self):
            n = int(self.headers.get("Content-Length") or 0)
            if not n:
                return {}
            try:
                return json.loads(self.rfile.read(n).decode("utf-8"))
            except ValueError as e:
                raise ErrorApi("JSON inválido") from e

        def _autorizado(self):
            dado = self.headers.get("Authorization", "")
            dado = dado[7:] if dado.lower().startswith("bearer ") else dado
            return hmac.compare_digest(dado.strip().encode(), clave_api.encode())

        def _atender(self, metodo):
            url = urlparse(self.path)
            q = {k: v[-1] for k, v in parse_qs(url.query).items()}
            ruta = url.path.rstrip("/")
            try:
                if ruta == "/api/ping":
                    return self._responder(200, {"ok": True, "version": VERSION})
                if not self._autorizado():
                    return self._responder(401, {"error": "Clave incorrecta"})
                b = self._cuerpo() if metodo in ("POST", "PUT") else {}
                rutas = {
                    ("GET", "/api/estado"): lambda: agente.estado(),
                    ("POST", "/api/ejecutar"): lambda: agente.ejecutar(
                        real=bool(b.get("real", True)),
                        cuenta=b.get("cuenta") or None,
                        ignorar_horario=bool(b.get("ignorar_horario", False)),
                        sin_espera=bool(b.get("sin_espera", True)),
                    ),
                    ("POST", "/api/detener"): lambda: agente.detener(forzar=bool(b.get("forzar", False))),
                    ("POST", "/api/pausa"): lambda: agente.pausar(bool(b.get("pausado", True)), b.get("hasta") or None),
                    ("GET", "/api/plan"): lambda: agente.plan(q.get("fecha")),
                    ("POST", "/api/plan"): lambda: agente.plan(b.get("fecha"), generar=True),
                    ("PUT", "/api/plan"): lambda: agente.cambiar_plan(b["fecha"], b.get("ids")),
                    ("POST", "/api/incierto"): lambda: agente.resolver_incierto(b["fecha"], b["cuenta"], b["id"], b.get("accion")),
                    ("GET", "/api/catalogo"): lambda: agente.catalogo_api(q.get("refrescar") == "1"),
                    ("GET", "/api/categorias"): lambda: agente.categorias(q.get("refrescar") == "1"),
                    ("GET", "/api/promo"): lambda: agente.promo(),
                    ("GET", "/api/historial"): lambda: agente.historial(int(q.get("dias", 30)), q.get("cuenta")),
                    ("GET", "/api/log"): lambda: agente.log(q.get("archivo", "estados"), int(q.get("desde", -1))),
                    ("GET", "/api/ajustes"): lambda: agente.ajustes(),
                    ("PUT", "/api/ajustes"): lambda: agente.guardar_ajustes(b.get("cambios", {}), bool(b.get("restablecer"))),
                }
                fn = rutas.get((metodo, ruta))
                if fn is None:
                    return self._responder(404, {"error": f"No existe {metodo} {ruta}"})
                return self._responder(200, fn())
            except ErrorApi as e:
                return self._responder(e.codigo, {"error": str(e)})
            except KeyError as e:
                return self._responder(400, {"error": f"Falta el dato {e}"})
            except ValueError as e:
                return self._responder(400, {"error": str(e)})
            except Exception as e:  # noqa: BLE001
                log.exception("Error atendiendo %s %s", metodo, ruta)
                return self._responder(500, {"error": f"Error en el PC: {e}"})

        def do_GET(self):  # noqa: N802
            self._atender("GET")

        def do_POST(self):  # noqa: N802
            self._atender("POST")

        def do_PUT(self):  # noqa: N802
            self._atender("PUT")

    return Manejador


def iniciar_logs_agente():
    (DATOS / "logs").mkdir(parents=True, exist_ok=True)
    log.setLevel(logging.INFO)
    fmt = logging.Formatter("%(asctime)s %(levelname)s %(message)s")
    fh = logging.handlers.RotatingFileHandler(DATOS / "logs" / "agente.log", maxBytes=500_000, backupCount=2, encoding="utf-8")
    fh.setFormatter(fmt)
    log.addHandler(fh)
    if sys.stdout:  # con pythonw no hay consola
        sh = logging.StreamHandler(sys.stdout)
        sh.setFormatter(fmt)
        log.addHandler(sh)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--puerto", type=int)
    ap.add_argument("--host", default=None, help="por defecto 0.0.0.0 (todas las redes, incluida Tailscale)")
    ap.add_argument("--mostrar-clave", action="store_true")
    args = ap.parse_args()

    c = clave()
    if args.mostrar_clave:
        print(c)
        return 0
    iniciar_logs_agente()
    cfg = cargar_config()
    ag = cfg.get("agente", {})
    host = args.host or ag.get("host", "0.0.0.0")
    puerto = args.puerto or ag.get("puerto", PUERTO)
    python = sys.executable
    if python.lower().endswith("pythonw.exe"):  # publicar.py necesita consola para su salida
        python = python[:-5] + ".exe"
    servidor = ThreadingHTTPServer((host, puerto), crear_manejador(Agente(python), c))
    log.info("Agente v%s escuchando en http://%s:%s  (clave en %s)", VERSION, host, puerto, ARCHIVO_CLAVE)
    try:
        servidor.serve_forever()
    except KeyboardInterrupt:
        pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
