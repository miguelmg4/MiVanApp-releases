"""Limpieza de la lista de ingredientes y estimación del grado de procesado (NOVA)."""
import html
import re
from typing import List, Optional, Tuple

from sync.health.additives import Additive, plain

# Clases de aditivo que delatan un ultraprocesado (NOVA 4), por rango de número E: colorantes,
# espesantes/emulgentes/estabilizantes, antiaglomerantes, potenciadores del sabor, glaseantes,
# edulcorantes y almidones modificados. Los gases de envasado (E938-E949) no cuentan.
_NOVA4_RANGES = [(100, 199), (400, 499), (551, 559), (620, 650), (900, 937), (950, 969), (1400, 1452)]
NOVA4_TERMS = [
    "jarabe de glucosa", "jarabe de fructosa", "glucosa-fructosa", "dextrosa", "maltodextrina",
    "aromas?", "almidon modificado", "proteina aislada", "proteina hidrolizada",
    "aceite hidrogenado", "grasa hidrogenada", "lactosuero en polvo", "azucar invertido",
]
_TERMS = [re.compile(r"(?<!\w)" + term + r"(?!\w)") for term in NOVA4_TERMS]
_CULINARY = ("aceite", "sal", "azucar", "vinagre", "harina", "mantequilla", "miel")
_ADDED = re.compile(r"(?<!\w)(sal|azucar(es)?|aceites?|vinagre)(?!\w)")
_PREFIX = re.compile(r"^\s*ingredientes\s*:\s*", re.IGNORECASE)


def clean_ingredients(raw: Optional[str]) -> str:
    if not raw:
        return ""
    text = html.unescape(re.sub(r"<[^>]+>", " ", raw))
    text = re.sub(r"\s+", " ", text).strip()
    text = re.sub(r"\s+([.,;:)\]])", r"\1", text)  # el hueco que deja una etiqueta antes de un signo
    return _PREFIX.sub("", text).strip()


def _is_nova4_additive(additive: Additive) -> bool:
    match = re.match(r"E(\d+)", additive.code)
    if not match:
        return False
    number = int(match.group(1))
    return any(low <= number <= high for low, high in _NOVA4_RANGES)


def split_ingredients(text: str) -> List[str]:
    """Trocea por comas que no estén dentro de paréntesis o corchetes."""
    parts, depth, current = [], 0, []
    for char in text:
        if char in "([":
            depth += 1
        elif char in ")]" and depth:
            depth -= 1
        if char == "," and depth == 0:
            parts.append("".join(current))
            current = []
        else:
            current.append(char)
    parts.append("".join(current))
    return [p.strip(" .") for p in parts if p.strip(" .")]


def estimate_nova(text: str, additives: List[Additive]) -> Tuple[int, int]:
    """(grupo NOVA 1-4, nº de marcadores de ultraprocesado)."""
    flat = plain(text)
    markers = sum(1 for term in _TERMS if term.search(flat))
    markers += sum(1 for additive in additives if _is_nova4_additive(additive))
    if markers:
        return 4, markers
    parts = split_ingredients(flat)
    if len(parts) <= 1 and not additives:
        return (2 if flat.strip().startswith(_CULINARY) else 1), 0
    if additives or _ADDED.search(flat):
        return 3, 0
    return 1, 0
