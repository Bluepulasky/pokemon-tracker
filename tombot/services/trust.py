"""Which price quotes can be believed.

TCGdex reports one Cardmarket product for several different cards. In the WOTC
sets that is systematic: the non-holo print of a rare carries the holo's
product, so it prices four to six times too high. The Gym sets add a second
shape, where a Trainer's holo product lands on every "Brock's ..." common.

The affected products are listed in data/tcgdex_shared_products.json, generated
by scripts/tcgdex_scan.py against the live API. A quote reading one of those
products describes whichever card actually owns it, so it is refused rather
than blended into an average — an average of the right card and the wrong one
is wrong in a way nobody can see.
"""
from __future__ import annotations

import json
import pathlib

_DATA = pathlib.Path(__file__).resolve().parent.parent / "data" / "tcgdex_shared_products.json"
_cache: dict | None = None


def _load() -> dict:
    global _cache
    if _cache is None:
        try:
            _cache = json.loads(_DATA.read_text())
        except (OSError, ValueError):
            # Missing data must not stop the app pricing anything; it only
            # means we lose the guard, and the tests cover that it is present.
            _cache = {"shared_products": {}}
    return _cache


def shared_products() -> dict[str, list[str]]:
    return _load().get("shared_products") or {}


def product_is_shared(product_id) -> bool:
    return product_id is not None and str(product_id) in shared_products()


def cards_sharing(product_id) -> list[str]:
    return shared_products().get(str(product_id), [])


def distrust_reason(product_id, card_id: str) -> str | None:
    """Why this quote cannot be used, or None if it can."""
    others = [c for c in cards_sharing(product_id) if c != card_id]
    if not others:
        return None
    return (f"TCGdex da el producto {product_id} de Cardmarket también a "
            f"{', '.join(others)}, así que este precio puede ser el de esa carta")
