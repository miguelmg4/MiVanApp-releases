"""Open Food Facts: extracto del volcado CSV y taxonomía de aditivos (licencia ODbL)."""
import gzip
import io
import json
import urllib.request
from typing import Callable, Dict, Iterable, List, Optional, Set

from sync.health.score import OffRow

OFF_CSV = "https://static.openfoodfacts.org/data/en.openfoodfacts.org.products.csv.gz"
TAXONOMY = "https://static.openfoodfacts.org/data/taxonomies/additives.json"
USER_AGENT = "MiVanApp-catalog/1.0 (+https://github.com/miguelmg4/MiVanApp-releases)"
_TIMEOUT = 120


def norm_code(code: str) -> str:
    return code.strip().lstrip("0")


def _int(value: str) -> Optional[int]:
    try:
        return int(float(value))
    except ValueError:
        return None


def _tags(value: str) -> List[str]:
    return [tag.strip() for tag in value.split(",") if tag.strip()]


def extract(lines: Iterable[str], codes: Set[str]) -> Dict[str, OffRow]:
    """Filas del CSV (tabuladores, una por línea) cuyos códigos están en `codes` (normalizados)."""
    iterator = iter(lines)
    header = next(iterator, "").rstrip("\r\n").split("\t")
    col = {name: i for i, name in enumerate(header)}
    wanted = ["code", "nutriscore_grade", "nutriscore_score", "nova_group", "additives_tags", "labels_tags"]
    if any(name not in col for name in wanted):
        raise ValueError("el volcado de Open Food Facts ha cambiado de columnas")
    rows: Dict[str, OffRow] = {}
    for line in iterator:
        code = norm_code(line[:line.find("\t")])  # comprobar el código antes de trocear la fila entera
        if code not in codes:
            continue
        fields = line.rstrip("\r\n").split("\t")
        if len(fields) < len(header):
            continue
        rows[code] = OffRow(
            code=code,
            nutriscore_grade=fields[col["nutriscore_grade"]].strip().lower() or None,
            nutriscore_score=_int(fields[col["nutriscore_score"]]),
            nova_group=_int(fields[col["nova_group"]]),
            additives_tags=_tags(fields[col["additives_tags"]]),
            labels_tags=_tags(fields[col["labels_tags"]]),
        )
    return rows


def _open(url: str, opener: Callable):
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    return opener(request, timeout=_TIMEOUT)


def download_extract(codes: Set[str], url: str = OFF_CSV,
                     opener: Callable = urllib.request.urlopen) -> Dict[str, OffRow]:
    """Recorre el volcado en streaming (~1,5 GB comprimido) sin guardarlo."""
    with _open(url, opener) as response:
        text = io.TextIOWrapper(gzip.GzipFile(fileobj=response), encoding="utf-8", errors="replace")
        return extract(text, codes)


def download_taxonomy(opener: Callable = urllib.request.urlopen) -> dict:
    with _open(TAXONOMY, opener) as response:
        return json.loads(response.read().decode("utf-8"))


def row_to_json(row: OffRow) -> dict:
    return {"g": row.nutriscore_grade, "s": row.nutriscore_score, "n": row.nova_group,
            "a": row.additives_tags, "l": row.labels_tags}


def row_from_json(code: str, data: dict) -> OffRow:
    return OffRow(code, data.get("g"), data.get("s"), data.get("n"), data.get("a") or [], data.get("l") or [])
