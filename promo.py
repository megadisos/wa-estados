"""Detecta la "promo de la semana" publicada en customania.com.co/promos.

La página /promos elige con JavaScript cuál es la promo vigente ("Esta es la de esta semana:"), así que se
abre con un navegador (Playwright, sin ventana) en vez de leer solo el HTML. Luego entra a la página de esa
promo (/promos/<slug>/) y toma su título (h1) y su imagen principal.

Si algún día la detección automática falla, en config.toml puedes fijarla a mano con [promo_semana] forzar.
"""
import re
from urllib.parse import urljoin, urlparse

from playwright.sync_api import sync_playwright

from util import log

# Devuelve el enlace a la promo vigente: el primer enlace visible a /promos/<slug>/ que aparece después del
# texto "Esta es la de esta semana" (o "promo de la semana"). Si no encuentra ese texto, el primero visible.
ELEGIR_JS = r"""() => {
  const visible = el => {
    const r = el.getBoundingClientRect(), s = getComputedStyle(el);
    return r.width > 0 && r.height > 0 && s.visibility !== 'hidden' && s.display !== 'none' && s.opacity !== '0';
  };
  const esPromo = a => /^\/promos\/[^\/?#]+\/?$/.test(new URL(a.href, location.href).pathname);
  const enlaces = [...document.querySelectorAll('a[href]')].filter(a => esPromo(a) && visible(a));
  let marca = null;
  const w = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
  while (w.nextNode()) {
    const t = w.currentNode.textContent;
    if (/(es la de esta semana|promo de la semana)/i.test(t) && visible(w.currentNode.parentElement)) {
      marca = w.currentNode.parentElement; break;
    }
  }
  const tras = marca ? enlaces.find(a => marca.compareDocumentPosition(a) & Node.DOCUMENT_POSITION_FOLLOWING) : null;
  const a = tras || enlaces[0];
  return {href: a ? a.href : null, con_marca: !!tras, total: enlaces.length};
}"""

# En la página de la promo: h1, descripción y la imagen principal (la primera "-promo." en el contenido,
# tomando la versión más grande de su srcset). Si no hay, og:image.
DETALLE_JS = r"""() => {
  const meta = k => (document.querySelector(`meta[property="${k}"]`) || document.querySelector(`meta[name="${k}"]`) || {}).content || '';
  const mayor = img => {
    let mejor = img.currentSrc || img.src, ancho = img.naturalWidth || 0;
    for (const parte of (img.srcset || '').split(',')) {
      const [u, d] = parte.trim().split(/\s+/);
      const w = parseInt(d || '0', 10);
      if (u && w > ancho) { mejor = u; ancho = w; }
    }
    return new URL(mejor, location.href).href;
  };
  const imgs = [...document.querySelectorAll('main img, article img, img')].filter(i => /-promo[.\-_]/i.test(i.currentSrc || i.src));
  const h1 = document.querySelector('h1');
  return {
    titulo: h1 ? h1.innerText.trim() : meta('og:title'),
    descripcion: meta('og:description') || meta('description'),
    imagen: imgs.length ? mayor(imgs[0]) : meta('og:image'),
  };
}"""


def _slug(url):
    m = re.fullmatch(r"/promos/([^/?#]+)/?", urlparse(url).path)
    return m.group(1) if m else ""


def _abrir_navegador(pw):
    """Abre Chromium sin estorbar. En Windows el "headless shell" de Playwright a veces lo bloquea el antivirus
    ([WinError 5] Acceso denegado), así que se prueba primero el mismo Chromium que usa WhatsApp."""
    intentos = [
        ("Chromium sin ventana", dict(headless=True, channel="chromium")),
        ("Chromium con ventana fuera de pantalla", dict(headless=False, args=["--window-position=-32000,-32000"])),
        ("headless shell", dict(headless=True)),
    ]
    ultimo = None
    for nombre, opciones in intentos:
        try:
            return pw.chromium.launch(**opciones)
        except Exception as e:  # noqa: BLE001
            log.info("No se pudo abrir %s para leer la promo (%s); pruebo otra forma", nombre, str(e).splitlines()[0])
            ultimo = e
    raise ultimo


def detectar(cfg):
    """Devuelve el item de la promo vigente: {id, tipo='promo', titulo, descripcion, precio, url, imagen}."""
    pc = cfg.get("promo_semana", {})
    base = cfg["sitio"].rstrip("/")
    pagina = pc.get("pagina") or f"{base}/promos"
    forzar = (pc.get("forzar") or "").strip()

    with sync_playwright() as pw:
        nav = _abrir_navegador(pw)
        try:
            page = nav.new_page(viewport={"width": 1280, "height": 1600}, locale="es-CO")
            if forzar:
                url = forzar if forzar.startswith("http") else f"{base}/promos/{forzar.strip('/')}/"
                log.info("Promo de la semana fijada a mano en config.toml: %s", url)
            else:
                page.goto(pagina, wait_until="networkidle", timeout=60000)
                r = page.evaluate(ELEGIR_JS)
                if not r["href"]:
                    raise RuntimeError(f"no encontré ninguna promo en {pagina}")
                url = r["href"]
                if not r["con_marca"]:
                    log.warning("No vi el texto 'Esta es la de esta semana' en %s; tomo la primera promo visible", pagina)
                log.info("Promo de la semana detectada: %s (%d promos visibles en la página)", url, r["total"])
            page.goto(url, wait_until="networkidle", timeout=60000)
            d = page.evaluate(DETALLE_JS)
        finally:
            nav.close()

    if not d["imagen"]:
        raise RuntimeError(f"la promo {url} no tiene imagen")
    slug = _slug(url) or "promo"
    return {
        "id": f"promo:{slug}",
        "tipo": "promo",
        "titulo": re.sub(r"\s*\|\s*Customania.*$", "", d["titulo"]).strip(),
        "descripcion": (d["descripcion"] or "")[:160],
        "precio": "",
        "url": urljoin(base + "/", urlparse(url).path.lstrip("/")),
        "imagen": d["imagen"],
    }
