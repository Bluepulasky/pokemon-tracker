"""Cardmarket (MKM) product links.

`cardmarket.url` in the pokemontcg.io payload is a prices.pokemontcg.io
redirector, not a Cardmarket address. The real product slug is Cardmarket
internal and not derivable from the card data:

    base1-4  -> .../Singles/Base-Set/Charizard-V2-BS4
    gym1-2   -> .../Singles/Gym-Heroes/Brocks-Rhydon-GH2
    ex7-95   -> .../Singles/EX-Team-Rocket-Returns/R-Energy-TRR95

The 'V2' disambiguator and the slug rules are Cardmarket's, so guessing produces
broken links. `flask resolve-links` reads each one from the redirector's Location
header once and stores it; this module just formats what was stored.

The redirector still works as a live fallback for anything unresolved, so a card
always has a usable link.
"""
from __future__ import annotations

import json

REDIRECTOR = "https://prices.pokemontcg.io/cardmarket/{card_id}"

# Verified against the live site: minCondition=2 selects "Near Mint" in the
# product page's filter panel. Cardmarket's condition ladder, best first.
MIN_CONDITION_PARAM = {
    "NM": 2,     # Near Mint
    "LP": 5,     # Light Played
    "MP": 6,     # Played
    "HP": 7,     # Poor
    "DMG": 7,
}

# NOT verified: `language=<n>` was accepted in the query string but checked no
# box in the filter panel, so it is deliberately not used. Left here so whoever
# confirms the real parameter name has somewhere obvious to put it.
LANGUAGE_PARAM: dict[str, int] = {}


def market_url(card: dict, *, locale: str = "en", condition: str | None = None) -> str | None:
    """Build the Cardmarket product URL for a catalog card.

    Falls back to the redirector when the direct URL has not been resolved yet,
    so the UI never has to deal with a missing link.
    """
    if not card:
        return None

    ext = card.get("external_ids_json")
    if isinstance(ext, str):
        try:
            ext = json.loads(ext)
        except (TypeError, ValueError):
            ext = {}
    ext = ext or {}

    url = ext.get("cardmarket_direct")
    if not url:
        card_id = card.get("id") or card.get("card_id")
        return REDIRECTOR.format(card_id=card_id) if card_id else None

    if locale and locale != "en":
        url = url.replace("/en/", f"/{locale}/", 1)

    # Off by default: an over-filtered page can come back empty and read as a
    # broken link. Enabled by passing an explicit condition.
    if condition and condition in MIN_CONDITION_PARAM:
        url = f"{url}?minCondition={MIN_CONDITION_PARAM[condition]}"

    return url


def attach(rows: list[dict], *, locale: str = "en") -> list[dict]:
    """Add `market_url` to catalog cards or collection rows in place."""
    for r in rows:
        r["market_url"] = market_url(r, locale=locale)
    return rows
