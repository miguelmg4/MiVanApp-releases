"""Copias de respaldo en JSON comprimido dentro de la rama `catalog` (carpeta details/)."""
import gzip
import json
from pathlib import Path
from typing import Any, Optional


def read_gz_json(path: Path) -> Optional[Any]:
    if not path.exists():
        return None
    try:
        return json.loads(gzip.decompress(path.read_bytes()).decode("utf-8"))
    except (OSError, ValueError):
        return None  # copia corrupta: como si no hubiera


def write_gz_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    raw = json.dumps(data, ensure_ascii=False, separators=(",", ":"), sort_keys=True).encode("utf-8")
    path.write_bytes(gzip.compress(raw, mtime=0))
