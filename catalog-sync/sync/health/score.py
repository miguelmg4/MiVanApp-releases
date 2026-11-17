"""Nota de salud 0-100: completa (con Nutri-Score) o por ingredientes.

Pesos del método público de Yuka: 60 % nutrición (o procesado, si no hay Nutri-Score), 30 %
aditivos y 10 % ecológico. Un aditivo de riesgo alto deja la nota en 49 como máximo.
"""
import re
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

from sync.health.additives import Additive, AdditiveTable, plain
from sync.health.ingredients import estimate_nova

NON_FOOD_CATS = {
    "Cuidado del cabello", "Cuidado facial y corporal", "Fitoterapia y parafarmacia",
    "Limpieza y hogar", "Maquillaje", "Mascotas",
}
NON_FOOD_BABY = {
    "Accesorios", "Aceite y crema", "Biberón", "Braguita y otros", "Champú y jabón", "Chupete",
    "Colonia", "Pañal talla de 0 a 3", "Pañal talla de 4 a XL", "Toallitas",
}
ALCOHOL_CAT = "Bodega"
# Categorías de frescos: sin lista de ingredientes cuentan como un solo ingrediente. None = todas.
FRESH: Dict[str, Optional[set]] = {
    "Fruta y verdura": None,
    "Carne": {"Cerdo", "Conejo", "Cordero", "Pavo y otras aves", "Pollo", "Vacuno"},
    "Huevos, leche y mantequilla": {"Huevos"},
}
FRESH_FISH_CAT = "Marisco y pescado"
FRESH_FISH_EXCLUDED = {"Ahumados", "Salazones", "Surimi y otros"}

# Rango de puntos Nutri-Score (alimentos, versión 2023) y tramo de nota por letra.
_GRADES: Dict[str, Tuple[int, int, int, int]] = {
    # letra: (mejor puntuación, peor puntuación, nota mínima, nota máxima)
    "a": (-17, 0, 80, 100),
    "b": (1, 2, 60, 79),
    "c": (3, 10, 40, 59),
    "d": (11, 18, 20, 39),
    "e": (19, 55, 0, 19),
}
_ORGANIC = re.compile(r"(?<!\w)(ecologico|ecologica|bio)(?!\w)")
HIGH_RISK_CAP = 49


@dataclass
class OffRow:
    code: str
    nutriscore_grade: Optional[str] = None
    nutriscore_score: Optional[int] = None
    nova_group: Optional[int] = None
    additives_tags: List[str] = field(default_factory=list)
    labels_tags: List[str] = field(default_factory=list)


def nutrition_points(grade: str, score: Optional[int]) -> float:
    best, worst, low, high = _GRADES[grade]
    if score is None:
        return (low + high + 1) // 2  # centro del tramo
    clamped = min(max(score, best), worst)
    return high - (clamped - best) * (high - low) / (worst - best)


def additive_points(additives: List[Additive]) -> float:
    if any(a.risk == "high" for a in additives):
        return 0
    return max(0, 100 - 30 * sum(1 for a in additives if a.risk == "moderate"))


def processing_points(nova: int, markers: int) -> float:
    if nova == 4:
        return max(0, 25 - 5 * (max(markers, 1) - 1))
    return {1: 100, 2: 75, 3: 50}[nova]


def _is_food(name: str, cat: str, sub: str) -> bool:
    if cat in NON_FOOD_CATS or (cat == "Bebé" and sub in NON_FOOD_BABY):
        return False
    if cat == ALCOHOL_CAT:
        flat = plain(name)
        return "sin alcohol" in flat or "0,0" in flat
    return True


def _is_fresh(cat: str, sub: str) -> bool:
    if cat == FRESH_FISH_CAT:
        return sub not in FRESH_FISH_EXCLUDED
    subs = FRESH.get(cat, set())
    return subs is None or sub in subs


# Texto que describe un tratamiento de la piel (ceras, fungicidas de los cítricos), no una receta.
_SURFACE = re.compile(r"^\s*tratad[oa]s?\b|agentes? de recubrimiento|en superficie")
PRODUCE_CAT = "Fruta y verdura"


def _surface_only(cat: str, ingredients: str) -> bool:
    return cat == PRODUCE_CAT and bool(ingredients) and bool(_SURFACE.search(plain(ingredients)))


def compute(name: str, cat: str, sub: str, ingredients: str, off: Optional[OffRow],
            table: AdditiveTable) -> Optional[dict]:
    if not _is_food(name, cat, sub):
        return None
    grade = (off.nutriscore_grade or "").lower() if off else ""
    full = grade in _GRADES
    fresh = not ingredients and _is_fresh(cat, sub)
    if not full and not ingredients and not fresh:
        return None

    if off and off.additives_tags:
        additives = table.from_tags(off.additives_tags)
    else:
        additives = table.find_in_text(ingredients) if ingredients else []
    if _surface_only(cat, ingredients):
        nova_estimated, markers = 1, 0  # fruta entera: el tratamiento es de la piel, sus aditivos sí cuentan
    else:
        nova_estimated, markers = estimate_nova(ingredients, additives) if ingredients else (1, 0)
    if off and off.nova_group:
        nova, estimated = off.nova_group, False
    elif ingredients or fresh:
        nova, estimated = nova_estimated, True
    else:
        nova, estimated = None, False
    organic = bool((off and "en:organic" in off.labels_tags) or _ORGANIC.search(plain(name)))

    main = nutrition_points(grade, off.nutriscore_score) if full else processing_points(nova, markers)
    value = 0.6 * main + 0.3 * additive_points(additives) + (10 if organic else 0)
    if any(a.risk == "high" for a in additives):
        value = min(value, HIGH_RISK_CAP)
    return {
        "value": int(round(value)),
        "kind": "full" if full else "ingredients",
        "nutriscore": grade if full else None,
        "nova": nova,
        "novaEstimated": estimated,
        "organic": organic,
        "additives": [{"code": a.code, "name": a.name, "risk": a.risk} for a in additives],
    }
