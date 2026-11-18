#!/usr/bin/env python3
"""Descarga los catálogos de los supermercados y publica un fichero por cadena.

Uso: python3 run.py --out DIR [--stores mercadona,lidl] [--limit N] [--stale-only]
"""
import argparse
import inspect
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Dict, List, Optional, Tuple

from sync.health.pipeline import enrich_mercadona
from sync.http import Http
from sync.publish import publish_store, read_index, read_products, write_index
from sync.stores import ahorramas, lidl, mercadona

STORES: Dict[str, Tuple[str, Callable]] = {
    "mercadona": ("Mercadona", mercadona.fetch),
    "ahorramas": ("Ahorramás", ahorramas.fetch),
    "lidl": ("Lidl", lidl.fetch),
}


def sync(out_dir: Path, stores: Dict[str, Tuple[str, Callable]], http, now: datetime,
         limit: Optional[int] = None, report_path: Optional[Path] = None,
         enrich: Optional[Dict[str, Callable]] = None) -> int:
    """Devuelve 0 si al menos una cadena se publica fresca; 1 si todas fallan.

    Con [report_path] escribe el estado de cada cadena: "ok" (publicada esta vez), "stale" (falló y se
    conserva la anterior), "stale-known" (sigue fallando: ya estaba desactualizada antes) o "missing"
    (falló y no había nada anterior).

    `enrich` añade la nota de salud a los productos de una cadena antes de publicarlos; su estado va
    al informe como "notas" ("ok" o "missing").
    """
    out_dir.mkdir(parents=True, exist_ok=True)
    entries = dict(read_index(out_dir)["stores"])
    fresh = 0
    status: Dict[str, str] = {}
    for key, (name, fetch) in stores.items():
        was_stale = bool(entries.get(key, {}).get("stale"))
        try:
            if "previous" in inspect.signature(fetch).parameters:  # Lidl: lo necesita si tira del buscador
                products = fetch(http, limit, previous=read_products(out_dir, key))
            else:
                products = fetch(http, limit)
        except Exception as error:  # una cadena rota no debe tumbar a las demás
            print(f"{key}: FALLO en la descarga: {type(error).__name__}: {error}", file=sys.stderr)
            products = None
        if products and enrich and key in enrich:
            products, status["notas"] = enrich[key](products, http, out_dir)
        entry = publish_store(out_dir, key, name, products, now)
        if entry is None:
            entries.pop(key, None)
            status[key] = "missing"
            print(f"{key}: sin datos que publicar")
        else:
            entries[key] = entry
            status[key] = ("stale-known" if was_stale else "stale") if entry["stale"] else "ok"
            if entry["stale"]:
                print(f"{key}: se conserva el catálogo anterior ({entry['count']} productos, {entry['syncedAt']})")
            else:
                fresh += 1
                print(f"{key}: {entry['count']} productos publicados")
        write_index(out_dir, entries)  # tras cada cadena: un corte a mitad no pierde lo ya hecho
    if report_path is not None:
        report_path.write_text(json.dumps(status, ensure_ascii=False), encoding="utf-8")
    return 0 if fresh else 1


def check_report(report_path: Path) -> Tuple[int, List[str]]:
    """(código de salida, cadenas que han dejado de actualizarse esta vez).

    Una caída que ya se avisó ("stale-known") no cuenta: el correo llega una vez al empezar, no cada
    semana mientras dure. La app sigue mostrando la fecha de esos precios y «sin actualizar».
    """
    status = json.loads(report_path.read_text(encoding="utf-8"))
    failed = [key for key, value in status.items() if value not in ("ok", "stale-known")]
    return (1 if failed else 0), failed


def stale_stores(out_dir: Path, known: List[str]) -> List[str]:
    """Cadenas de `known` que no se actualizaron en la última ejecución (o que no están publicadas)."""
    entries = read_index(out_dir)["stores"]
    return [key for key in known if key not in entries or entries[key].get("stale")]


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--out", type=Path, help="carpeta de salida")
    parser.add_argument("--stores", default=",".join(STORES), help="cadenas separadas por comas")
    parser.add_argument("--limit", type=int, help="solo las N primeras categorías de cada cadena (pruebas)")
    parser.add_argument("--report", type=Path, help="escribe aquí el estado de cada cadena (JSON)")
    parser.add_argument("--stale-only", action="store_true",
                        help="solo las cadenas que quedaron sin actualizar (reintento diario)")
    parser.add_argument("--check", type=Path, help="no descarga: falla si el informe tiene alguna cadena sin actualizar")
    args = parser.parse_args(argv)
    if args.check:
        code, failed = check_report(args.check)
        known = [k for k, v in json.loads(args.check.read_text(encoding="utf-8")).items() if v == "stale-known"]
        if known:
            print(f"::warning::Siguen sin actualizar (ya avisado): {', '.join(known)}. Se reintentan a diario.")
        if failed:
            print(f"::error::No se han actualizado: {', '.join(failed)}. Se mantienen sus precios anteriores.")
        elif not known:
            print("Todas las cadenas actualizadas.")
        return code
    if args.out is None:
        parser.error("falta --out")
    unknown = [s for s in args.stores.split(",") if s not in STORES]
    if unknown:
        parser.error(f"cadenas desconocidas: {', '.join(unknown)}")
    keys = args.stores.split(",")
    if args.stale_only:
        keys = stale_stores(args.out, keys)
        if not keys:
            print("Todas las cadenas están al día: nada que reintentar.")
            return 0
        print(f"Reintentando: {', '.join(keys)}")
    selected = {key: STORES[key] for key in keys}
    code = sync(args.out, selected, Http(), datetime.now(timezone.utc), args.limit, args.report,
                {"mercadona": enrich_mercadona})
    # El reintento nunca acaba en error: el aviso por correo ya lo da la ejecución del lunes.
    return 0 if args.stale_only else code


if __name__ == "__main__":
    sys.exit(main())
