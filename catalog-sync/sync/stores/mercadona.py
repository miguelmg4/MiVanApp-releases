"""Mercadona: API pública de su tienda online, almacén que sirve a Cuenca."""
from typing import Dict, List, Optional, Tuple

from sync.http import FetchError
from sync.model import Product

WAREHOUSE = "4606"  # el que asigna tienda.mercadona.es a Cuenca
BASE = "https://tienda.mercadona.es/api/categories/"
QUERY = f"?lang=es&wh={WAREHOUSE}"


def _number(value) -> Optional[float]:
    try:
        return float(str(value).strip())
    except (TypeError, ValueError):
        return None


def _trim(number: float) -> str:
    return f"{number:g}"


def parse_tree(data: dict) -> List[Tuple[int, str, int]]:
    """(id de subcategoría, nombre de la categoría padre, orden del padre)."""
    return [
        (sub["id"], top["name"], top.get("order", 0))
        for top in data.get("results", [])
        for sub in top.get("categories", [])
    ]


def parse_category(data: dict, cat: str, cat_order: int) -> List[Product]:
    products = []
    for leaf in data.get("categories", []):
        for item in leaf.get("products", []):
            price = item.get("price_instructions") or {}
            unit_size = _number(price.get("unit_size"))
            size_parts = [item.get("packaging") or ""]
            if unit_size:
                size_parts.append(f"{_trim(unit_size)} {price.get('size_format') or ''}".strip())
            reference = price.get("reference_format")
            products.append(Product(
                id=str(item["id"]),
                name=item.get("display_name") or "",
                price=_number(price.get("unit_price")) or 0,
                size=" ".join(part for part in size_parts if part) or None,
                unitPrice=_number(price.get("bulk_price")),
                unitLabel=reference.lower() if reference else None,
                image=item.get("thumbnail"),
                cat=cat,
                sub=leaf.get("name") or "",
                catOrder=cat_order,
            ))
    return products


PRODUCT = "https://tienda.mercadona.es/api/products/{id}/" + QUERY


def parse_detail(data: Optional[dict]) -> Optional[dict]:
    """EAN e ingredientes (en crudo, con HTML) de la ficha de un producto."""
    if not data:
        return None
    nutrition = data.get("nutrition_information") or {}
    ean = data.get("ean")
    return {"ean": str(ean) if ean else None, "ingredients": nutrition.get("ingredients") or ""}


def fetch_details(http, ids: List[str], cache: Dict[str, dict]) -> Tuple[Dict[str, dict], int]:
    """Pide la ficha de todos los productos; si una falla, usa la de la caché (si la hay)."""
    details: Dict[str, dict] = {}
    failures = 0
    for product_id in ids:
        try:
            detail = parse_detail(http.get_json(PRODUCT.format(id=product_id)))
        except FetchError:
            detail = None
        if detail is None:
            failures += 1
            detail = cache.get(product_id)
        if detail is not None:
            details[product_id] = detail
    return details, failures


def fetch(http, limit: Optional[int] = None) -> List[Product]:
    """`limit` recorta el número de subcategorías (para pruebas rápidas)."""
    tree = parse_tree(http.get_json(BASE + QUERY))
    products: List[Product] = []
    for sub_id, cat, order in tree[:limit]:
        products += parse_category(http.get_json(f"{BASE}{sub_id}/{QUERY}"), cat, order)
    return products
