"""Lidl: servicio de catálogo de la app Lidl Plus para la tienda de Cuenca.

Es un servicio interno de su app (no una web pública): puede cambiar sin aviso. Desde el
2026-11-17 la lista de categorías llega vacía (204) pero el buscador sigue respondiendo, así que
si no hay categorías el catálogo se reconstruye buscando (ver `search_catalog`).
"""
import re
import sys
from collections import Counter
from typing import Dict, Iterable, List, Optional, Tuple
from urllib.parse import quote

from sync.http import FetchError
from sync.model import Product

STORE = "ES0573"  # tienda de Cuenca
BASE = f"https://product-catalog.lidlplus.com/api/app/v1/ES/store/{STORE}"
SEARCH = BASE + "/search?q="
HEADERS = {"Accept-Language": "es"}

# Términos generales para encontrar productos que no estaban en el catálogo anterior.
GENERAL_TERMS = (
    "leche", "yogur", "queso", "mantequilla", "nata", "huevos", "pan", "galletas", "cereales", "chocolate",
    "café", "infusión", "zumo", "agua", "refresco", "cerveza", "vino", "aceite", "vinagre", "sal", "azúcar",
    "harina", "arroz", "pasta", "legumbres", "garbanzos", "lentejas", "tomate", "salsa", "conserva", "atún",
    "sardinas", "aceitunas", "pollo", "cerdo", "vacuno", "ternera", "pavo", "jamón", "chorizo", "salchichas",
    "embutido", "pescado", "salmón", "merluza", "gambas", "marisco", "congelado", "pizza", "helado",
    "verdura", "fruta", "manzana", "plátano", "naranja", "patatas", "cebolla", "lechuga", "ensalada",
    "frutos secos", "snack", "patatas fritas", "bollería", "postre", "mermelada", "miel", "bebida vegetal",
    "proteína", "ecológico", "sin gluten", "sin lactosa", "detergente", "suavizante", "lavavajillas",
    "limpiador", "papel higiénico", "servilletas", "champú", "gel", "desodorante", "pasta de dientes",
    "pañales", "toallitas", "comida para perro", "comida para gato", "vitamina",
)
_STOP = {"con", "sin", "para", "del", "los", "las", "una", "uno", "por", "sabor", "pack"}
_MAX_FAILED_RATIO = 0.2  # más búsquedas fallidas que esto: Lidl nos está bloqueando

_UNIT_PRICE = re.compile(r"^(1\s*(?:kg|l)|100\s*(?:g|ml))\s*=\s*(\d+(?:[.,]\d+)?)$", re.I)
_PER = {"1kg": (1, "kg"), "1l": (1, "l"), "100g": (10, "kg"), "100ml": (10, "l")}
_BULK = re.compile(r"^1\s*(kg|l)$", re.I)
_SIZE = re.compile(r"^(\d+(?:[.,]\d+)?)\s*([A-Za-z.]+)$")


def parse_unit(annotations: List[str]) -> Tuple[Optional[float], Optional[str]]:
    """Busca una anotación como «1kg = 6.33» (o «100g = 2.31») y devuelve (6.33, "kg") / (23.1, "kg")."""
    for text in annotations:
        match = _UNIT_PRICE.match(text.strip())
        if match:
            factor, label = _PER[re.sub(r"\s", "", match.group(1)).lower()]
            return round(float(match.group(2).replace(",", ".")) * factor, 2), label
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


def _product(item: dict, price: float, annotations: List[str], cat: str, sub: str, cat_order: int) -> Product:
    unit_price, unit_label = parse_unit(annotations)
    if unit_price is None:
        bulk = next((_BULK.match(a.strip()) for a in annotations if _BULK.match(a.strip())), None)
        if bulk:  # se vende al peso: el precio ya es por kilo o litro
            unit_price, unit_label = price, bulk.group(1).lower()
    return Product(
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
    )


def parse_products(data: Optional[dict], cat: str, sub: str, cat_order: int) -> List[Product]:
    products = []
    for item in (data or {}).get("products") or []:
        price_info = item.get("price") or {}
        products.append(_product(item, price_info.get("price") or 0, price_info.get("annotations") or [],
                                 cat, sub, cat_order))
    return products


def _words(text: str) -> List[str]:
    return [w for w in re.findall(r"[a-záéíóúñü]+", text.lower()) if len(w) >= 3 and w not in _STOP]


class _Searcher:
    """Lanza búsquedas, acumula resultados por id y cuenta los fallos."""

    def __init__(self, http):
        self.http, self.found, self.tried, self.failed = http, {}, set(), 0

    def __call__(self, query: str) -> None:
        query = query.strip()[:200]
        if len(query) < 3 or query.lower() in self.tried:
            return
        self.tried.add(query.lower())
        try:
            data = self.http.get_json(SEARCH + quote(query), HEADERS)
        except FetchError:
            self.failed += 1
            if self.failed >= 5 and self.failed > len(self.tried) * _MAX_FAILED_RATIO:
                raise FetchError(f"el buscador de Lidl falla ({self.failed} de {len(self.tried)} búsquedas)")
            return
        for item in (data or {}).get("results") or []:
            self.found.setdefault(str(item["id"]), item)


def _guess_category(title: str, line: Optional[str], previous: List[dict], df: Counter,
                    by_word: Dict[str, List[dict]], other_order: int) -> Tuple[str, str, int]:
    """Categoría del producto conocido que más palabras poco frecuentes comparte con `title`."""
    weights: Counter = Counter()
    for word in set(_words(title)):
        for known in by_word.get(word, []):
            weights[(known["cat"], known.get("sub", ""), known.get("catOrder", 0))] += 1 / df[word]
    if weights:
        return weights.most_common(1)[0][0]
    if line == "FruitsAndVegetables":
        order = next((p.get("catOrder", 0) for p in previous if p["cat"] == "Fruta y verdura"), 0)
        return "Fruta y verdura", "", order
    return "Otros", "", other_order


def search_catalog(http, previous: List[dict], extra_terms: Iterable[str] = GENERAL_TERMS) -> List[Product]:
    """Reconstruye el catálogo con el buscador (máx. 40 resultados por búsqueda, sin páginas).

    1) Por cada producto del catálogo anterior, sus dos palabras menos frecuentes. 2) El nombre
    entero de los que sigan sin aparecer (p. ej. «Yogur natural»). 3) Términos generales y
    subcategorías para encontrar productos nuevos. Cada producto conserva su categoría anterior;
    los nuevos toman la del producto conocido más parecido.
    """
    search = _Searcher(http)
    df = Counter(w for p in previous for w in set(_words(p["name"])))
    by_word: Dict[str, List[dict]] = {}
    for p in previous:
        for w in set(_words(p["name"])):
            by_word.setdefault(w, []).append(p)
    for p in sorted(previous, key=lambda p: min((df[w] for w in _words(p["name"])), default=0)):
        for word in sorted(_words(p["name"]), key=lambda w: df[w])[:2]:
            if p["id"] in search.found:
                break
            search(word)
    for p in previous:
        if p["id"] not in search.found:
            search(p["name"])
    for term in list(extra_terms) + sorted({p.get("sub") or "" for p in previous}):
        search(term)

    known = {p["id"]: p for p in previous}
    other_order = max((p.get("catOrder", 0) for p in previous), default=-1) + 1
    products = []
    for pid, item in search.found.items():
        if pid in known:
            cat, sub, order = known[pid]["cat"], known[pid].get("sub", ""), known[pid].get("catOrder", 0)
        else:
            cat, sub, order = _guess_category(item.get("title") or "", item.get("productLine"), previous, df,
                                              by_word, other_order)
        item = {**item, "imageUrl": (item.get("imageUrl") or "").replace("Resize%3d(144)", "Resize%3d(384)") or None}
        products.append(_product(item, item.get("price") or 0, item.get("subtitles") or [], cat, sub, order))
    print(f"lidl: sin categorías; reconstruido con {len(search.tried)} búsquedas: {len(products)} productos "
          f"({sum(1 for p in products if p.id in known)} de {len(known)} conocidos)", file=sys.stderr)
    return products


def fetch(http, limit: Optional[int] = None, previous: Optional[List[dict]] = None,
          extra_terms: Iterable[str] = GENERAL_TERMS) -> List[Product]:
    """`limit` recorta el número de categorías de primer nivel (para pruebas rápidas).

    `previous` son los productos publicados la última vez; se usan si hay que tirar del buscador.
    """
    products: List[Product] = []
    categories = parse_categories(http.get_json(BASE + "/categories", HEADERS))
    if not categories:
        return search_catalog(http, previous or [], extra_terms)
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
