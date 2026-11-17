"""Ahorramás: se lee la rejilla de productos de su web, categoría a categoría."""
import html
import json
import re
from typing import List, Optional, Tuple
from urllib.parse import unquote

from sync.model import Product

HOME = "https://www.ahorramas.com/"
GRID = "https://www.ahorramas.com/on/demandware.store/Sites-Ahorramas-Site/es/Search-UpdateGrid"
PAGE = 48
MAX_PAGES = 400  # tope de seguridad por categoría (~19.000 productos)
SKIP = {"ofertas"}  # no es una categoría: repite productos de las demás
UNITS = {"LITRO": "l", "KILO": "kg", "KG": "kg", "UNIDAD": "ud", "METRO": "m", "DOCENA": "docena"}

_MENU = re.compile(r'<a\s+href="/[a-z-]+/"\s+id="([a-z_]+)"[^>]*>(.*?)</a>', re.S)
_ALT = re.compile(r'alt="([^"]+)"')
_TILE = re.compile(r'<div class="product" data-pid="')
_ATTR = r'{}\s*=\s*"([^"]*)"'
_IMAGE = re.compile(r'<img\s+class="tile-image"\s+src="(https://[^"]+)"')
_UNIT_PRICE = re.compile(r'unit-price-per-unit grey">\s*([\d.,]+)\s*(?:&euro;|€)\s*/\s*([A-Za-zÁ-ú]+)', re.S)


def number(text) -> Optional[float]:
    """Lee «0,83», «1.670,00» o «1.670.00»: el último separador es el decimal si le siguen 1-2 cifras."""
    digits = re.sub(r"[^\d.,]", "", str(text or ""))
    match = re.match(r"^(.*?)(?:[.,](\d{1,2}))?$", digits)
    whole = re.sub(r"[.,]", "", match.group(1)) if match else ""
    if not whole:
        return None
    return float(f"{whole}.{match.group(2) or 0}")


def grid_url(cgid: str, start: int) -> str:
    return f"{GRID}?cgid={cgid}&start={start}&sz={PAGE}"


def _attr(block: str, name: str) -> Optional[str]:
    match = re.search(_ATTR.format(re.escape(name)), block)
    return html.unescape(match.group(1)).strip() if match and match.group(1).strip() else None


def parse_categories(page: str) -> List[Tuple[str, str, int]]:
    """(cgid, nombre, orden) de las categorías de primer nivel del menú."""
    out = []
    for cgid, body in _MENU.findall(page):
        if cgid in SKIP:
            continue
        alt = _ALT.search(body)
        name = html.unescape(alt.group(1)) if alt else cgid.replace("_", " ").capitalize()
        out.append((cgid, name, len(out)))
    return out


def parse_grid(page: str, cat: str, cat_order: int) -> List[Product]:
    products = []
    for block in _TILE.split(page)[1:]:
        pid = block[: block.find('"')]
        layer = _attr(block, "data-gtm-layer")
        try:
            info = json.loads(unquote(layer)) if layer else {}
        except ValueError:
            info = {}
        price = number(info.get("price")) or number(_attr(block, "data-price")) or 0
        brand = _attr(block, "data-brand")
        unit = _UNIT_PRICE.search(block)
        image = _IMAGE.search(block)  # el primer src de la ficha puede ser un icono, no la foto
        products.append(Product(
            id=pid,
            name=info.get("name") or _attr(block, "alt") or "",
            price=price,
            brand=brand.capitalize() if brand else None,
            unitPrice=number(unit.group(1)) if unit else None,
            unitLabel=UNITS.get(unit.group(2).upper(), unit.group(2).lower()) if unit else None,
            image=html.unescape(image.group(1)) if image else None,
            cat=_attr(block, "data-category1") or cat,
            sub=_attr(block, "data-category2") or "",
            catOrder=cat_order,
        ))
    return products


def fetch(http, limit: Optional[int] = None) -> List[Product]:
    """`limit` recorta el número de categorías de primer nivel (para pruebas rápidas)."""
    products: List[Product] = []
    for cgid, name, order in parse_categories(http.get_text(HOME))[:limit]:
        seen = set()
        for page_number in range(MAX_PAGES):
            found = parse_grid(http.get_text(grid_url(cgid, page_number * PAGE)), name, order)
            new = [p for p in found if p.id not in seen]
            seen.update(p.id for p in new)
            products += new
            # El botón «Más resultados» apunta siempre a la misma posición, así que no sirve para
            # paginar: se avanza hasta una página incompleta o que no aporte nada nuevo.
            if len(found) < PAGE or not new:
                break
    return products
