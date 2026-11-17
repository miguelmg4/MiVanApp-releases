"""Añade la nota de salud a los productos de Mercadona sin poner nunca en riesgo los precios."""
import sys
from dataclasses import replace
from pathlib import Path
from typing import Callable, Dict, List, Tuple

from sync.health import off
from sync.health.additives import AdditiveTable
from sync.health.cache import read_gz_json, write_gz_json
from sync.health.ingredients import clean_ingredients
from sync.health.score import OffRow, compute
from sync.model import Product
from sync.stores import mercadona

LICENCE = """# Licencia de los datos de salud

El campo `score` de los productos se calcula con datos de Open Food Facts
(https://world.openfoodfacts.org), disponibles bajo la Open Database License (ODbL)
https://opendatacommons.org/licenses/odbl/1-0/. Esos datos derivados se comparten con la misma
licencia. Los ficheros de `details/` son copias de respaldo de las fuentes.
"""


def _log(message: str) -> None:
    print(f"notas: {message}", file=sys.stderr)


def _taxonomy(details_dir: Path, fetch_taxonomy: Callable) -> dict:
    path = details_dir / "additives.json.gz"
    try:
        data = fetch_taxonomy()
        write_gz_json(path, data)
        return data
    except Exception as error:
        _log(f"taxonomía de aditivos no disponible ({error}); se usa la copia anterior")
        return read_gz_json(path)


def _off_rows(details_dir: Path, codes: set, fetch_off: Callable) -> Dict[str, OffRow]:
    path = details_dir / "off.json.gz"
    try:
        rows = fetch_off(codes)
        write_gz_json(path, {code: off.row_to_json(row) for code, row in rows.items()})
        return rows
    except Exception as error:
        cached = read_gz_json(path) or {}
        _log(f"Open Food Facts no disponible ({error}); copia anterior con {len(cached)} productos")
        return {code: off.row_from_json(code, data) for code, data in cached.items()}


def _enrich(products: List[Product], http, out_dir: Path, fetch_off: Callable,
            fetch_taxonomy: Callable) -> Tuple[List[Product], str]:
    details_dir = out_dir / "details"
    details_path = details_dir / "mercadona.json.gz"
    details, failures = mercadona.fetch_details(http, [p.id for p in products], read_gz_json(details_path) or {})
    if failures:
        _log(f"{failures} fichas de Mercadona fallidas (se usa la copia anterior si la hay)")
    write_gz_json(details_path, details)

    taxonomy = _taxonomy(details_dir, fetch_taxonomy)
    if taxonomy is None:
        _log("sin taxonomía de aditivos ni copia: se publica sin notas")
        return products, "missing"
    table = AdditiveTable.from_taxonomy(taxonomy)

    codes = {off.norm_code(d["ean"]) for d in details.values() if d.get("ean")}
    rows = _off_rows(details_dir, codes, fetch_off)

    scored = []
    for product in products:
        detail = details.get(product.id) or {}
        ean = off.norm_code(detail["ean"]) if detail.get("ean") else None
        score = compute(product.name, product.cat, product.sub, clean_ingredients(detail.get("ingredients")),
                        rows.get(ean) if ean else None, table)
        scored.append(replace(product, score=score))
    (out_dir / "LICENCIA-DATOS.md").write_text(LICENCE, encoding="utf-8")
    full = sum(1 for p in scored if p.score and p.score["kind"] == "full")
    partial = sum(1 for p in scored if p.score and p.score["kind"] == "ingredients")
    _log(f"{full} notas completas y {partial} por ingredientes de {len(scored)} productos")
    return scored, "ok" if full or partial else "missing"


def enrich_mercadona(products: List[Product], http, out_dir: Path,
                     fetch_off: Callable = off.download_extract,
                     fetch_taxonomy: Callable = off.download_taxonomy) -> Tuple[List[Product], str]:
    """Devuelve (productos con `score`, "ok" | "missing"). Nunca lanza excepciones."""
    try:
        return _enrich(products, http, out_dir, fetch_off, fetch_taxonomy)
    except Exception as error:  # un fallo de las notas no puede impedir publicar los precios
        _log(f"FALLO inesperado, se publica sin notas: {type(error).__name__}: {error}")
        return products, "missing"
