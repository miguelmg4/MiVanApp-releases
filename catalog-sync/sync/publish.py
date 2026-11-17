"""Escribe un fichero por cadena y el índice que consulta la app."""
import gzip
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional

from sync.model import Product, clean

SCHEMA = 1
INDEX = "index.json"
ATTRIBUTION = "Datos nutricionales: Open Food Facts (ODbL)"
MIN_RATIO = 0.5  # por debajo de la mitad de la semana anterior se asume un bloqueo parcial


def _stamp(now: datetime) -> str:
    return now.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def read_index(out_dir: Path) -> dict:
    path = out_dir / INDEX
    if not path.exists():
        return {"schema": SCHEMA, "stores": {}}
    return json.loads(path.read_text(encoding="utf-8"))


def write_index(out_dir: Path, entries: Dict[str, dict]) -> None:
    index = {"schema": SCHEMA, "attribution": ATTRIBUTION, "stores": entries}
    (out_dir / INDEX).write_text(json.dumps(index, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")


def publish_store(
    out_dir: Path, store: str, name: str, products: Optional[List[Product]], now: datetime
) -> Optional[dict]:
    """Devuelve la entrada de índice de la cadena, o None si no hay nada que publicar.

    `products=None` es una descarga fallida. Un fallo, una lista vacía o una caída brusca
    conservan el fichero anterior y lo marcan como desactualizado.
    """
    previous = read_index(out_dir)["stores"].get(store)
    fresh = clean(products) if products else []
    too_few = bool(previous) and len(fresh) < previous["count"] * MIN_RATIO
    if not fresh or too_few:
        return {**previous, "stale": True} if previous else None

    file_name = f"{store}.json.gz"
    payload = {
        "schema": SCHEMA,
        "store": store,
        "syncedAt": _stamp(now),
        "products": [p.to_dict() for p in fresh],
    }
    raw = gzip.compress(json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8"), mtime=0)
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / file_name).write_bytes(raw)
    return {
        "name": name,
        "file": file_name,
        "count": len(fresh),
        "syncedAt": _stamp(now),
        "sha256": hashlib.sha256(raw).hexdigest(),
        "stale": False,
    }
