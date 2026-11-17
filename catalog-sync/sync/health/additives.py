"""Aditivos con su riesgo según la EFSA, a partir de la taxonomía de Open Food Facts."""
import re
import unicodedata
from dataclasses import dataclass
from typing import Dict, Iterable, List, Pattern, Tuple

_RISKS = {"en:high": "high", "en:moderate": "moderate", "en:no": "none"}
_CODE = re.compile(r"\bE\s?-?\s?(\d{3,4}[a-d]?)(?!\w)", re.IGNORECASE)
_MIN_NAME = 5  # nombres más cortos dan demasiados falsos positivos


@dataclass(frozen=True)
class Additive:
    code: str
    name: str
    risk: str  # "high" | "moderate" | "none" | "unrated"


def plain(text: str) -> str:
    """Minúsculas y sin acentos, para comparar textos de etiquetas."""
    decomposed = unicodedata.normalize("NFKD", text.lower())
    return "".join(c for c in decomposed if not unicodedata.combining(c))


class AdditiveTable:
    def __init__(self, by_code: Dict[str, Additive]):
        self.by_code = by_code
        names = sorted(
            ((plain(a.name), a.code) for a in by_code.values() if len(a.name) >= _MIN_NAME and a.name != a.code),
            key=lambda item: -len(item[0]),
        )
        self._names: List[Tuple[Pattern, str]] = [
            (re.compile(r"(?<!\w)" + re.escape(name) + r"(?!\w)"), code) for name, code in names
        ]

    @staticmethod
    def from_taxonomy(data: dict) -> "AdditiveTable":
        by_code = {}
        for key, entry in data.items():
            code = key.split(":", 1)[-1].upper()
            names = entry.get("name") or {}
            label = names.get("es") or names.get("en") or code
            name = label.split(" - ", 1)[1].strip() if " - " in label else label.strip()
            risk = _RISKS.get((entry.get("efsa_evaluation_overexposure_risk") or {}).get("en"), "unrated")
            by_code[code] = Additive(code, name[:1].upper() + name[1:], risk)
        return AdditiveTable(by_code)

    def _get(self, code: str) -> Additive:
        return self.by_code.get(code) or Additive(code, code, "unrated")

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
