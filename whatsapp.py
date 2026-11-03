"""Control de WhatsApp Web con Playwright (una sesión de navegador persistente por cuenta).

IMPORTANTE: WhatsApp cambia la interfaz de vez en cuando. Todos los selectores viven en SEL (abajo);
si un paso falla, el programa guarda una captura y un volcado de la pantalla en datos/capturas/
para ajustar solo esa lista.
"""
import json
import os
import random
import re
import time
from pathlib import Path

from playwright.sync_api import TimeoutError as PWTimeout

from util import DATOS, log

WA_URL = os.environ.get("WA_URL", "https://web.whatsapp.com/")

# Cada clave es una lista de alternativas (español / inglés / versiones distintas de la interfaz).
SEL = {
    "listo": [
        "#pane-side",
        "[data-icon='status-refreshed']",
        "[data-icon='status-outline']",
        "button[aria-label='Estados']",
        "button[aria-label='Status']",
    ],
    "qr": [
        "canvas[aria-label*='QR' i]",
        "div[data-ref]",
        "[aria-label*='código QR' i]",
        "[aria-label*='QR code' i]",
    ],
    "nav_estados": [
        "button[aria-label='Estados']",
        "button[aria-label='Status']",
        "[data-navbar-item='status']",
        "button:has([data-icon='status-refreshed'])",
        "button:has([data-icon='status-outline'])",
        "[role='button'][aria-label*='Estado' i]",
        "[role='button'][aria-label*='Status' i]",
    ],
    "agregar_estado": [
        "[aria-label*='Agregar estado' i]",
        "[aria-label*='Añadir estado' i]",
        "[aria-label*='Add status' i]",
        "[title*='Agregar estado' i]",
        "[title*='Add status' i]",
        "button:has([data-icon='plus-rounded'])",
        "button:has([data-icon='plus'])",
    ],
    "menu_foto": [
        "[aria-label*='Fotos y videos' i]",
        "[aria-label*='Photos & videos' i]",
        "[aria-label*='Photos and videos' i]",
        "li:has-text('Fotos y videos')",
        "li:has-text('Photos')",
        "text=/Fotos y videos/i",
        "text=/Photos (&|and) videos/i",
    ],
    "caption": [
        "div[contenteditable='true'][aria-label*='comentario' i]",
        "div[contenteditable='true'][aria-label*='pie de foto' i]",
        "div[contenteditable='true'][aria-label*='caption' i]",
        "div[contenteditable='true'][data-tab='10']",
        "div[role='textbox'][contenteditable='true']",
    ],
    "enviar": [
        "[aria-label='Enviar']",
        "[aria-label='Send']",
        "button:has([data-icon='wds-ic-send-filled'])",
        "[role='button']:has([data-icon='send'])",
        "span[data-icon='send']",
        "[data-icon='send']",
        "[data-icon*='send' i]",  # cualquier variante del ícono de enviar
    ],
}

# Botones con los que se cierran los avisos de WhatsApp ("Novedades", "Activa las notificaciones", etc.).
# Solo coincide con el texto exacto: nunca toca "Cerrar sesión" ni nada parecido.
BOTON_AVISO = re.compile(
    r"^(ok|aceptar|entendido|continuar|cerrar|ahora no|m[aá]s tarde|omitir|listo|usar aqu[ií]|"
    r"got it|continue|close|not now|later|skip|dismiss|use here)$",
    re.I,
)

# Simula un "pegar" de texto plano: el editor de WhatsApp convierte los saltos de línea en líneas reales.
PEGAR_JS = """(texto) => {
    const el = document.activeElement;
    const dt = new DataTransfer();
    dt.setData('text/plain', texto);
    el.dispatchEvent(new ClipboardEvent('paste', {clipboardData: dt, bubbles: true, cancelable: true}));
}"""


class NecesitaLogin(Exception):
    """La sesión de WhatsApp Web se cerró: hay que volver a escanear el QR (login.py)."""


class FalloPublicacion(Exception):
    def __init__(self, msg, incierto=False):
        super().__init__(msg)
        self.incierto = incierto  # True = quizá se publicó igual; no reintentar solo


class Sesion:
    def __init__(self, pw, cuenta, cfg, headless=False, depurar=False):
        self.pw, self.cuenta, self.cfg = pw, cuenta, cfg
        self.headless, self.depurar = headless, depurar
        self.capturas = DATOS / "capturas" / cuenta["nombre"]
        self.ctx = self.page = None

    # ------------------------------------------------------------ ciclo de vida
    def __enter__(self):
        Path(self.cuenta["perfil"]).mkdir(parents=True, exist_ok=True)
        self.capturas.mkdir(parents=True, exist_ok=True)
        opciones = dict(
            user_data_dir=self.cuenta["perfil"],
            headless=self.headless,
            viewport={"width": 1366, "height": 820},
            locale="es-CO",
            timezone_id=self.cfg.get("zona_horaria", "America/Bogota"),
            args=[
                "--disable-blink-features=AutomationControlled",
                "--no-first-run",
                "--no-default-browser-check",
                "--password-store=basic",
            ],
            ignore_default_args=["--enable-automation"],
        )
        if self.cuenta.get("proxy"):
            opciones["proxy"] = {"server": self.cuenta["proxy"]}
        self.ctx = self.pw.chromium.launch_persistent_context(**opciones)
        self.page = self.ctx.pages[0] if self.ctx.pages else self.ctx.new_page()
        return self

    def __exit__(self, *exc):
        try:
            self.ctx.close()  # cierre limpio: guarda la sesión en disco
        except Exception:  # noqa: BLE001
            pass

    # ------------------------------------------------------------ utilidades
    def captura(self, nombre):
        ruta = self.capturas / f"{time.strftime('%Y%m%d-%H%M%S')}_{nombre}.png"
        try:
            self.page.screenshot(path=str(ruta))
        except Exception:  # noqa: BLE001
            return None
        # conserva solo las últimas 40 capturas
        for vieja in sorted(self.capturas.glob("*.png"))[:-40]:
            vieja.unlink(missing_ok=True)
        return ruta

    def volcar_ui(self):
        """Guarda los aria-label / title / data-icon visibles: sirve para ajustar SEL si algo cambia."""
        try:
            datos = self.page.evaluate(
                """() => [...document.querySelectorAll('[aria-label],[title],[data-icon]')]
                    .filter(e => e.offsetParent !== null)
                    .map(e => ({tag: e.tagName.toLowerCase(), aria: e.getAttribute('aria-label'),
                                title: e.getAttribute('title'), icon: e.getAttribute('data-icon'),
                                role: e.getAttribute('role')}))"""
            )
            ruta = self.capturas / f"{time.strftime('%Y%m%d-%H%M%S')}_ui.json"
            ruta.write_text(json.dumps(datos, ensure_ascii=False, indent=1), encoding="utf-8")
            return ruta
        except Exception:  # noqa: BLE001
            return None

    def _visible(self, clave, timeout_ms=0):
        """Primer elemento visible entre las alternativas de SEL[clave], esperando hasta timeout_ms."""
        limite = time.time() + timeout_ms / 1000
        while True:
            for sel in SEL[clave]:
                try:
                    loc = self.page.locator(sel).first
                    if loc.is_visible():
                        return loc
                except Exception:  # noqa: BLE001
                    continue
            if time.time() >= limite:
                return None
            self.page.wait_for_timeout(300)

    def _falla(self, paso, incierto=False):
        cap, ui = self.captura(f"fallo_{paso}"), self.volcar_ui()
        raise FalloPublicacion(f"Paso '{paso}' falló (captura: {cap}, pantalla: {ui})", incierto=incierto)

    def _humano(self):
        """Movimientos y esperas cortas para no interactuar de forma robótica."""
        for _ in range(random.randint(1, 3)):
            self.page.mouse.move(random.randint(200, 1100), random.randint(150, 650), steps=random.randint(8, 22))
            self.page.wait_for_timeout(random.randint(200, 700))
        self.page.wait_for_timeout(random.randint(600, 1800))

    def _lineas_en(self, cuadro):
        """Cuántas líneas con texto hay realmente escritas en el cuadro."""
        try:
            texto = cuadro.evaluate("e => e.innerText")
        except Exception:  # noqa: BLE001
            return 0
        return len([l for l in texto.split("\n") if l.strip()])

    def _vaciar(self, cuadro):
        cuadro.click()
        self.page.keyboard.press("ControlOrMeta+A")
        self.page.keyboard.press("Delete")
        self.page.wait_for_timeout(300)

    def _escribir(self, cuadro, texto):
        """Escribe el texto conservando los saltos de línea (los enlaces quedan separados).

        1) Teclado: Shift+Enter entre líneas.  2) Si WhatsApp no los tomó, pega el texto como texto plano.
        3) Último recurso: una sola línea con las partes separadas por dos espacios.
        """
        lineas = texto.split("\n")
        esperadas = len([l for l in lineas if l.strip()])
        for i, linea in enumerate(lineas):
            if linea:
                self.page.keyboard.type(linea, delay=random.randint(12, 40))
            if i < len(lineas) - 1:
                self.page.keyboard.down("Shift")
                self.page.keyboard.press("Enter")
                self.page.keyboard.up("Shift")
                self.page.wait_for_timeout(random.randint(80, 200))
        if self._lineas_en(cuadro) >= esperadas:
            return

        log.warning("WhatsApp no tomó los saltos de línea con Shift+Enter; pruebo pegando el texto")
        self._vaciar(cuadro)
        self.page.evaluate(PEGAR_JS, texto)
        self.page.wait_for_timeout(600)
        if self._lineas_en(cuadro) >= esperadas:
            return

        log.warning("Tampoco funcionó pegar; dejo el texto en una sola línea con separación")
        self._vaciar(cuadro)
        self.page.keyboard.insert_text("  ".join(l for l in lineas if l.strip()))

    def cerrar_avisos(self):
        """Cierra las ventanas emergentes de WhatsApp que tapan la pantalla e impiden hacer clic en Estados."""
        for _ in range(4):
            aviso = self.page.locator("[role='dialog'][aria-modal='true']").first
            try:
                if not aviso.is_visible():
                    return
                texto = " | ".join(l.strip() for l in aviso.inner_text(timeout=2000).split("\n") if l.strip())
            except Exception:  # noqa: BLE001
                return
            log.info("[%s] WhatsApp muestra un aviso: %s", self.cuenta["nombre"], texto[:200])
            self.captura("aviso")
            boton = None
            for b in aviso.locator("button, [role='button']").all():
                try:
                    etiqueta = (b.inner_text(timeout=500).strip() or b.get_attribute("aria-label") or "").strip()
                    if BOTON_AVISO.match(etiqueta) and b.is_visible():
                        boton = b
                        break
                except Exception:  # noqa: BLE001
                    continue
            if boton:
                log.info("Cierro el aviso con el botón '%s'", etiqueta)
                boton.click(timeout=5000)
            else:
                log.info("El aviso no tiene un botón conocido; pruebo con Escape")
                self.page.keyboard.press("Escape")
            self.page.wait_for_timeout(random.randint(1200, 2200))

    # ------------------------------------------------------------ flujo
    def esperar_listo(self, timeout_s=180):
        self.page.goto(WA_URL, wait_until="domcontentloaded", timeout=60000)
        inicio, qr_desde = time.time(), None
        while time.time() - inicio < timeout_s:
            if self._visible("listo"):
                self.page.wait_for_timeout(random.randint(3000, 6000))  # deja terminar la sincronización
                self.cerrar_avisos()
                return
            if time.time() - inicio > 40:
                self.cerrar_avisos()  # un aviso puede estar tapando la pantalla de inicio
            if self._visible("qr"):
                qr_desde = qr_desde or time.time()
                if time.time() - qr_desde > 25:
                    self.captura("necesita_login")
                    raise NecesitaLogin(f"La cuenta '{self.cuenta['nombre']}' pide escanear el QR de nuevo")
            else:
                qr_desde = None
            self.page.wait_for_timeout(1000)
        self._falla("cargar_whatsapp_web")

    def ir_a_estados(self):
        self._humano()
        self.cerrar_avisos()
        if not self._visible("agregar_estado"):
            nav = self._visible("nav_estados", 15000)
            if not nav:
                self._falla("abrir_pestana_estados")
            try:
                nav.click(timeout=15000)
            except PWTimeout:
                self.cerrar_avisos()
                try:
                    nav.click(timeout=15000)
                except PWTimeout:
                    self._falla("abrir_pestana_estados")
            self.page.wait_for_timeout(random.randint(1200, 2500))
        if not self._visible("agregar_estado", 15000):
            self._falla("boton_agregar_estado")

    def publicar_imagen(self, ruta, caption, enviar=True):
        self._humano()
        self.cerrar_avisos()
        agregar = self._visible("agregar_estado", 15000)
        if not agregar:
            self._falla("boton_agregar_estado")
        try:
            with self.page.expect_file_chooser(timeout=20000) as info:
                agregar.click()
                menu = self._visible("menu_foto", 4000)  # si no hay menú, el clic ya abre el selector
                if menu:
                    menu.click()
            info.value.set_files(str(ruta))
        except PWTimeout:
            self._falla("selector_de_archivos")

        cuadro = self._visible("caption", 30000)
        if not cuadro:
            self._falla("cuadro_de_texto")
        editor = cuadro.element_handle()  # el elemento exacto: así se sabe cuándo el editor se cerró
        self.page.wait_for_timeout(random.randint(800, 2000))
        cuadro.click()
        self._escribir(cuadro, caption)
        self.page.wait_for_timeout(random.randint(800, 1800))
        if self.depurar:
            self.captura("antes_de_enviar")

        boton = self._visible("enviar", 6000)
        if not boton:
            self.volcar_ui()  # por si hay que ajustar SEL["enviar"]
        if not enviar:
            log.info("[prueba] Texto listo; botón Enviar %s. NO se envió (--sin-enviar)",
                     "encontrado" if boton else "no encontrado (se enviaría con Enter)")
            self.captura("sin_enviar")
            return

        if boton:
            boton.click()
        else:
            log.info("No encontré el botón Enviar; envío con Enter, como haría una persona")
            cuadro.click()
            self.page.keyboard.press("Enter")

        # el envío terminó cuando el editor (el cuadro de texto exacto) desaparece
        limite = time.time() + 45
        while time.time() < limite:
            try:
                abierto = editor.is_visible() and editor.evaluate("e => e.isConnected")
            except Exception:  # noqa: BLE001
                abierto = False
            if not abierto:
                self.page.wait_for_timeout(random.randint(3000, 6000))
                if self.depurar:
                    self.captura("despues_de_enviar")
                return
            self.page.wait_for_timeout(500)
        self._falla("confirmar_envio", incierto=True)
