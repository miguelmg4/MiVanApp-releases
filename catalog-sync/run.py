#!/usr/bin/env python3
"""Descarga los catálogos de los supermercados y publica un fichero por cadena.

Uso: python3 run.py --out DIR [--stores mercadona,lidl] [--limit N]
"""
import argparse
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Dict, Optional, Tuple

from sync.http import Http
from sync.publish import publish_store, read_index, write_index
from sync.stores import ahorramas, lidl, mercadona

STORES: Dict[str, Tuple[str, Callable]] = {
    "mercadona": ("Mercadona", mercadona.fetch),
    "ahorramas": ("Ahorramás", ahorramas.fetch),
    "lidl": ("Lidl", lidl.fetch),
}


def sync(out_dir: Path, stores: Dict[str, Tuple[str, Callable]], http, now: datetime,
         limit: Optional[int] = None) -> int:
    """Devuelve 0 si al menos una cadena se publica fresca; 1 si todas fallan."""
    out_dir.mkdir(parents=True, exist_ok=True)
    entries = dict(read_index(out_dir)["stores"])
    fresh = 0
    for key, (name, fetch) in stores.items():
        try:
            products = fetch(http, limit)
        except Exception as error:  # una cadena rota no debe tumbar a las demás
            print(f"{key}: FALLO en la descarga: {type(error).__name__}: {error}", file=sys.stderr)
            products = None
        entry = publish_store(out_dir, key, name, products, now)
        if entry is None:
            entries.pop(key, None)
            print(f"{key}: sin datos que publicar")
        else:
            entries[key] = entry
            if entry["stale"]:
                print(f"{key}: se conserva el catálogo anterior ({entry['count']} productos, {entry['syncedAt']})")
            else:
                fresh += 1
                print(f"{key}: {entry['count']} productos publicados")
        write_index(out_dir, entries)  # tras cada cadena: un corte a mitad no pierde lo ya hecho
    return 0 if fresh else 1


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--out", required=True, type=Path, help="carpeta de salida")
    parser.add_argument("--stores", default=",".join(STORES), help="cadenas separadas por comas")
    parser.add_argument("--limit", type=int, help="solo las N primeras categorías de cada cadena (pruebas)")
    args = parser.parse_args(argv)
    unknown = [s for s in args.stores.split(",") if s not in STORES]
    if unknown:
        parser.error(f"cadenas desconocidas: {', '.join(unknown)}")
    selected = {key: STORES[key] for key in args.stores.split(",")}
    return sync(args.out, selected, Http(), datetime.now(timezone.utc), args.limit)


if __name__ == "__main__":
    sys.exit(main())
