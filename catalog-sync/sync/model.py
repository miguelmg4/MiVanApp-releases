"""Formato común de producto que publican todas las cadenas."""
from dataclasses import asdict, dataclass
from typing import Iterable, List, Optional


@dataclass
class Product:
    id: str
    name: str
    price: float
    brand: Optional[str] = None
    size: Optional[str] = None
    unitPrice: Optional[float] = None
    unitLabel: Optional[str] = None
    image: Optional[str] = None
    cat: str = ""
    sub: str = ""
    catOrder: int = 0

    def to_dict(self) -> dict:
        return asdict(self)


def clean(products: Iterable[Product]) -> List[Product]:
    """Quita productos sin nombre o sin precio y los repetidos (gana el primero)."""
    seen = set()
    out = []
    for p in products:
        if not p.name.strip() or not p.price or p.price <= 0 or p.id in seen:
            continue
        seen.add(p.id)
        out.append(p)
    return out
