"""Aditivos con su riesgo: el de la EFSA (taxonomía de Open Food Facts) y, si no lo hay, el que se deduce
del Reglamento (CE) 1333/2008 (ver eu_additives)."""
import re
import unicodedata
from dataclasses import dataclass
from typing import Dict, Iterable, Iterator, List, Pattern, Tuple

from .eu_additives import AUTHORIZED, BANNED, GROUP_I

_RISKS = {"en:high": "high", "en:moderate": "moderate", "en:no": "none"}
_CODE = re.compile(r"\bE\s?-?\s?(\d{3,4}[a-d]?)(?!\w)", re.IGNORECASE)
_VARIANT = re.compile(r"^(E\d{3,4}[A-D]?)(?:I{1,3}|IV|V)$")  # E322I, E450III, E160AI…
_MIN_NAME = 5  # nombres más cortos dan demasiados falsos positivos
# Nombres de aditivo que en una etiqueta suelen ser un alimento, un sabor o una vitamina, no un
# aditivo: solo cuentan si aparecen con su número E.
FOOD_NAMES = {
    "azafran", "caramelo", "gelatina", "amaranto", "tanino", "sandalo", "licopeno", "dextrina",
    "riboflavina", "alanina", "l-leucina", "etanol", "nitrogeno", "oxigeno", "plata", "aluminio",
    "cloro", "helio", "beta-caroteno", "alfa-caroteno", "luteina", "alfa-tocoferol",
    "delta-tocoferol", "gamma-tocoferol", "tocoferol concentrado", "peptona", "lisozima",
}


@dataclass(frozen=True)
class Additive:
    code: str
    name: str
    risk: str  # "high" | "moderate" | "limited" | "none" | "unrated"


def plain(text: str) -> str:
    """Minúsculas y sin acentos, para comparar textos de etiquetas."""
    decomposed = unicodedata.normalize("NFKD", text.lower())
    return "".join(c for c in decomposed if not unicodedata.combining(c))


def _lineage(code: str, parents: Dict[str, List[str]]) -> Iterator[str]:
    """El propio código y después sus «padres»: el de la taxonomía y el que sale de quitar el sufijo."""
    yield code
    for parent in parents.get(code, []):
        yield parent
    match = _VARIANT.match(code)
    if match:
        yield match.group(1)
    if re.fullmatch(r"E\d{3,4}[A-D]", code):  # E960A → E960
        yield code[:-1]
    if code == "E14XX":  # «almidón modificado» sin concretar: todos los E14xx autorizados son del Grupo I
        yield "E1404"


def _legal_risk(code: str) -> str:
    if code in BANNED:
        return "high"
    if code in GROUP_I:
        return "none"
    if code in AUTHORIZED:
        return "limited"
    family = [c for c in AUTHORIZED if len(c) == len(code) + 1 and c.startswith(code) and c[-1].isalpha()]
    if family:  # p. ej. E150 sin letra: el peor de sus variantes
        return "none" if all(c in GROUP_I for c in family) else "limited"
    return "unrated"


def resolve_risk(code: str, efsa: Dict[str, str], parents: Dict[str, List[str]]) -> str:
    """Prohibido > riesgo de la EFSA > reglamento; mirando también el aditivo principal de una variante."""
    lineage = list(dict.fromkeys(_lineage(code, parents)))
    if any(c in BANNED for c in lineage):
        return "high"
    for candidate in lineage:
        if candidate in efsa:
            return efsa[candidate]
    for candidate in lineage:
        risk = _legal_risk(candidate)
        if risk != "unrated":
            return risk
    return "unrated"


class AdditiveTable:
    def __init__(self, by_code: Dict[str, Additive], efsa: Dict[str, str] = None, parents: Dict[str, List[str]] = None):
        self.by_code = by_code
        self._efsa = efsa or {}
        self._parents = parents or {}
        names = sorted(
            ((plain(a.name), a.code) for a in by_code.values()
             if len(a.name) >= _MIN_NAME and a.name != a.code and plain(a.name) not in FOOD_NAMES),
            key=lambda item: -len(item[0]),
        )
        self._names: List[Tuple[Pattern, str]] = [
            (re.compile(r"(?<!\w)" + re.escape(name) + r"(?!\w)"), code) for name, code in names
        ]

    @staticmethod
    def from_taxonomy(data: dict) -> "AdditiveTable":
        code_of = lambda key: key.split(":", 1)[-1].upper()
        efsa, parents, names = {}, {}, {}
        for key, entry in data.items():
            code = code_of(key)
            risk = _RISKS.get((entry.get("efsa_evaluation_overexposure_risk") or {}).get("en"))
            if risk:
                efsa[code] = risk
            parents[code] = [code_of(p) for p in entry.get("parents") or []]
            labels = entry.get("name") or {}
            label = labels.get("es") or labels.get("en") or code
            name = label.split(" - ", 1)[1].strip() if " - " in label else label.strip()
            names[code] = name[:1].upper() + name[1:]
        by_code = {code: Additive(code, name, resolve_risk(code, efsa, parents)) for code, name in names.items()}
        return AdditiveTable(by_code, efsa, parents)

    def _get(self, code: str) -> Additive:
        return self.by_code.get(code) or Additive(code, code, resolve_risk(code, self._efsa, self._parents))

    def from_tags(self, tags: Iterable[str]) -> List[Additive]:
        return self._unique(tag.split(":", 1)[-1].strip().upper() for tag in tags if tag.strip())

    def find_in_text(self, text: str) -> List[Additive]:
        found: List[Tuple[int, str]] = [(m.start(), "E" + m.group(1).upper()) for m in _CODE.finditer(text)]
        flat = plain(text)
        for pattern, code in self._names:
            match = pattern.search(flat)
            if match:
                found.append((match.start(), code))
        return self._unique(code for _, code in sorted(found))

    def _unique(self, codes: Iterable[str]) -> List[Additive]:
        seen, out = set(), []
        for code in codes:
            if code not in seen:
                seen.add(code)
                out.append(self._get(code))
        return out
