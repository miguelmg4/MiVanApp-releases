"""Lidl: servicio de catálogo de la app Lidl Plus para la tienda de Cuenca.

Es un servicio interno de su app (no una web pública): puede cambiar sin aviso.
"""
import re
import sys
from typing import List, Optional, Tuple

from sync.model import Product

STORE = "ES0573"  # Cuenca, C. de Pedro Almodóvar
BASE = f"https://product-catalog.lidlplus.com/api/app/v1/ES/store/{STORE}"
HEADERS = {"Accept-Language": "es"}

_UNIT_PRICE = re.compile(r"^1\s*(kg|l)\s*=\s*(\d+(?:[.,]\d+)?)$", re.I)
_BULK = re.compile(r"^1\s*(kg|l)$", re.I)
_SIZE = re.compile(r"^(\d+(?:[.,]\d+)?)\s*([A-Za-z.]+)$")


def parse_unit(annotations: List[str]) -> Tuple[Optional[float], Optional[str]]:
    """Busca una anotación como «1kg = 6.33» y devuelve (6.33, "kg")."""
    for text in annotations:
        match = _UNIT_PRICE.match(text.strip())
        if match:
            return float(match.group(2).replace(",", ".")), match.group(1).lower()
    return None, None


def _size(annotations: List[str]) -> Optional[str]:
    parts = []
    for text in annotations:
        text = text.strip()
        if _UNIT_PRICE.match(text):
            continue
        match = _SIZE.match(text)
        if match:
            unit = "uds" if match.group(2).lower().startswith("stk") else match.group(2)
            text = f"{match.group(1)} {unit}"
        parts.append(text)
    return ", ".join(parts) or None


def parse_categories(data: Optional[dict]) -> List[dict]:
    return list((data or {}).get("categories") or [])


def parse_products(data: Optional[dict], cat: str, sub: str, cat_order: int) -> List[Product]:
    products = []
    for item in (data or {}).get("products") or []:
        price_info = item.get("price") or {}
        price = price_info.get("price") or 0
        annotations = price_info.get("annotations") or []
        unit_price, unit_label = parse_unit(annotations)
        if unit_price is None:
            bulk = next((_BULK.match(a.strip()) for a in annotations if _BULK.match(a.strip())), None)
            if bulk:  # se vende al peso: el precio ya es por kilo o litro
                unit_price, unit_label = price, bulk.group(1).lower()
        products.append(Product(
            id=str(item["id"]),
            name=item.get("title") or "",
            price=price,
            brand=item.get("brand"),
            size=_size(annotations),
            unitPrice=unit_price,
            unitLabel=unit_label,
            image=item.get("imageUrl"),
            cat=cat,
            sub=sub,
            catOrder=cat_order,
        ))
    return products


def fetch(http, limit: Optional[int] = None) -> List[Product]:
    """`limit` recorta el número de categorías de primer nivel (para pruebas rápidas)."""
    products: List[Product] = []
    categories = parse_categories(http.get_json(BASE + "/categories", HEADERS))
    for order, category in enumerate(categories[:limit]):
        category_url = f"{BASE}/categories/{category['id']}"
        if category.get("hasSubcategories"):
            subs = [(sub["name"], f"{category_url}/categories/{sub['id']}/products")
                    for sub in parse_categories(http.get_json(category_url + "/categories", HEADERS))]
        else:
            subs = [("", category_url + "/products")]
        for sub_name, url in subs:
            data = http.get_json(url, HEADERS)
            found = parse_products(data, category["name"], sub_name, order)
            total = (data or {}).get("totalProducts")
            if total and total != len(found):
                print(f"lidl: «{sub_name or category['name']}» anuncia {total} productos y llegan {len(found)}",
                      file=sys.stderr)
            products += found
    return products
