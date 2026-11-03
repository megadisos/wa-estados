"""Lee servicios y productos de customania.com.co.

- Servicios: sitemap del sitio -> páginas /servicios/<slug> -> etiquetas og:title / og:image.
- Productos: API pública de WooCommerce (Store API). Si falla, cae al sitemap (/store/<slug>).

listar() es liviano (solo referencias). detalle() trae los datos completos solo de lo que se va a publicar.
"""
import html
import re
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup

from util import log

CABECERAS = {
    "User-Agent": (
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0 Safari/537.36"
    ),
    "Accept-Language": "es-CO,es;q=0.9",
}


def _get(url, **kw):
    r = requests.get(url, headers=CABECERAS, timeout=30, **kw)
    r.raise_for_status()
    return r


def _urls_sitemap(base):
    pendientes = [f"{base}/sitemap-index.xml", f"{base}/sitemap-0.xml", f"{base}/sitemap.xml"]
    vistos, paginas = set(), []
    while pendientes:
        u = pendientes.pop(0)
        if u in vistos:
            continue
        vistos.add(u)
        try:
            xml = _get(u).content.decode("utf-8", "replace")
        except requests.RequestException:
            continue
        for loc in re.findall(r"<loc>\s*(.*?)\s*</loc>", xml, flags=re.S):
            loc = html.unescape(loc)
            (pendientes if loc.endswith(".xml") else paginas).append(loc)
    return list(dict.fromkeys(paginas))


def _meta(url):
    soup = BeautifulSoup(_get(url).content, "html.parser")  # bytes: bs4 detecta UTF-8 (evita "tamaÃ±os")

    def m(*claves):
        for c in claves:
            t = soup.find("meta", attrs={"property": c}) or soup.find("meta", attrs={"name": c})
            if t and t.get("content"):
                return html.unescape(t["content"]).strip()
        return ""

    titulo = m("og:title", "twitter:title") or (soup.title.string if soup.title and soup.title.string else "")
    titulo = re.sub(r"\s*[|–—-]\s*Customania\s*$", "", titulo).strip()
    imagen = m("og:image", "twitter:image")
    return {
        "titulo": titulo,
        "descripcion": m("og:description", "description"),
        "imagen": urljoin(url, imagen) if imagen else "",
        "precio_raw": m("product:price:amount"),
    }


def _formato_cop(valor):
    return "$" + f"{valor:,.0f}".replace(",", ".")


def _texto_plano(s):
    return re.sub(r"\s+", " ", BeautifulSoup(s or "", "html.parser").get_text(" ")).strip()


# ---------------------------------------------------------------- servicios
def _servicios(cfg):
    base = cfg["sitio"].rstrip("/")
    excl = set(cfg.get("excluir_servicios", []))
    refs = {}
    for u in _urls_sitemap(base):
        m = re.fullmatch(r"/servicios/([^/]+)/?", urlparse(u).path)
        if m and m.group(1) not in excl:
            slug = m.group(1)
            refs[f"servicio:{slug}"] = {"id": f"servicio:{slug}", "tipo": "servicio", "slug": slug, "url": u}
    return refs


# ---------------------------------------------------------------- productos
def _excluido(texto, cfg):
    t = texto.lower()
    return any(p.lower() in t for p in cfg.get("excluir_productos", []))


def _productos_api(cfg):
    api, todos, pagina = cfg["tienda_api"], [], 1
    while pagina <= 30:
        r = _get(api, params={"per_page": 100, "page": pagina, "orderby": "date", "order": "desc"})
        datos = r.json()
        if not datos:
            break
        todos += datos
        if pagina >= int(r.headers.get("X-WP-TotalPages", pagina)):
            break
        pagina += 1
    return todos


def _item_producto_api(p, cfg):
    imagenes = p.get("images") or []
    if not imagenes or not p.get("is_in_stock", True):
        return None
    cats = p.get("categories") or []
    texto = " ".join([c.get("name", "") + " " + c.get("slug", "") for c in cats] + [p.get("name", ""), p.get("slug", "")])
    if _excluido(texto, cfg):
        return None
    pr = p.get("prices") or {}
    precio = ""
    try:
        menor = int(pr.get("currency_minor_unit", 0))
        actual = int(pr["price"]) / 10**menor
        regular = int(pr.get("regular_price") or pr["price"]) / 10**menor
        if actual > 0:
            precio = _formato_cop(actual)
            if regular > actual:
                precio += f" (antes {_formato_cop(regular)})"
    except (KeyError, ValueError, TypeError):
        pass
    slug = p.get("slug") or str(p["id"])
    return {
        "id": f"producto:{p['id']}",
        "tipo": "producto",
        "titulo": html.unescape(p.get("name", "")).strip(),
        "descripcion": _texto_plano(p.get("short_description"))[:160],
        "precio": precio,
        "url": f"{cfg['sitio'].rstrip('/')}/store/{slug}",
        "imagen": imagenes[0].get("src", ""),
    }


def _productos(cfg):
    refs = {}
    try:
        for p in _productos_api(cfg):
            item = _item_producto_api(p, cfg)
            if item:
                refs[item["id"]] = {"id": item["id"], "tipo": "producto", "item": item}
        if refs:
            return refs
        log.warning("La API de la tienda no devolvió productos publicables; uso el sitemap")
    except Exception as e:  # noqa: BLE001
        log.warning("Falló la API de la tienda (%s); uso el sitemap", e)
    base = cfg["sitio"].rstrip("/")
    for u in _urls_sitemap(base):
        m = re.fullmatch(r"/store/([^/]+)/?", urlparse(u).path)
        if m and not _excluido(m.group(1), cfg):
            slug = m.group(1)
            refs[f"producto:{slug}"] = {"id": f"producto:{slug}", "tipo": "producto", "slug": slug, "url": u}
    return refs


# ---------------------------------------------------------------- API pública
def listar(cfg):
    cat = {"servicio": _servicios(cfg), "producto": _productos(cfg)}
    for tipo, refs in cat.items():
        log.info("Catálogo %s: %d elementos", tipo, len(refs))
        if not refs:
            raise RuntimeError(f"No se encontró ningún {tipo} en el sitio; revisa config.toml y la conectividad")
    return cat


def detalle(ref, cfg):
    """Devuelve el item completo (titulo, descripcion, precio, url, imagen)."""
    if "item" in ref:
        return ref["item"]
    meta = _meta(ref["url"])
    precio = ""
    if ref["tipo"] == "producto" and meta["precio_raw"]:
        try:
            precio = _formato_cop(float(meta["precio_raw"]))
        except ValueError:
            pass
    if not meta["imagen"]:
        raise RuntimeError(f"{ref['url']} no tiene imagen (og:image)")
    return {
        "id": ref["id"],
        "tipo": ref["tipo"],
        "titulo": meta["titulo"] or ref["slug"].replace("-", " ").title(),
        "descripcion": meta["descripcion"][:160],
        "precio": precio,
        "url": ref["url"],
        "imagen": meta["imagen"],
    }
