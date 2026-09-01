"""Cardmarket (MKM) product links.

The link for a card is the Cardmarket product it maps to. Every imported card
carries its products in `market_products` (the direct tcggo <-> MKM match), each
with its own working `market_url`, so a link is a lookup, not a guess:

    base1-4  -> .../Singles/Base-Set/Charizard-V2-BS4
    gym1-2   -> .../Singles/Gym-Heroes/Brocks-Rhydon-GH2
    ex7-95   -> .../Singles/EX-Team-Rocket-Returns/R-Energy-TRR95

A collection row that pinned an exact version uses that product's URL; anything
else falls back to the card's direct match (`repo.market_urls_for_cards`). There
is deliberately no card-level guess: the old prices.pokemontcg.io redirector was
a leftover from the removed pokemontcg.io source and now only 404s (issue #27),
so a card with no product gets no link rather than a broken one.
"""
from __future__ import annotations

import json

# Verified against the live site: minCondition=2 selects "Near Mint" in the
# product page's filter panel. Cardmarket's condition ladder, best first.
MIN_CONDITION_PARAM = {
    "M/NM": 2,     # Mint/Near Mint
    "EX": 5,     # Excellent
    "GD": 6,     # Played
    "PL": 7,     # Poor
    "PO": 7,
}

# NOT verified: `language=<n>` was accepted in the query string but checked no
# box in the filter panel, so it is deliberately not used. Left here so whoever
# confirms the real parameter name has somewhere obvious to put it.
LANGUAGE_PARAM: dict[str, int] = {}


def market_url(card: dict, *, locale: str = "en", condition: str | None = None) -> str | None:
    """The resolved direct Cardmarket URL stored on the card, or None.

    Returns a link only when the card carries a `cardmarket_direct` URL; there
    is no redirector fallback any more (see the module docstring). Callers that
    want the card's product-level link resolve it through
    `repo.market_urls_for_cards` — see `attach`.
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
        return None

    if locale and locale != "en":
        url = url.replace("/en/", f"/{locale}/", 1)

    # Off by default: an over-filtered page can come back empty and read as a
    # broken link. Enabled by passing an explicit condition.
    if condition and condition in MIN_CONDITION_PARAM:
        url = f"{url}?minCondition={MIN_CONDITION_PARAM[condition]}"

    return url


def attach(rows: list[dict], *, locale: str = "en", repo=None) -> list[dict]:
    """Add `market_url` to catalog cards or collection rows in place.

    Prefers a card's resolved `cardmarket_direct`; otherwise, when a `repo` is
    given, uses the card's direct Cardmarket product match. A card with neither
    is left with `market_url=None` — no link beats a link to the dead redirector.
    """
    by_card: dict[str, str] = {}
    if repo is not None:
        by_card = repo.market_urls_for_cards(
            [r.get("id") or r.get("card_id") for r in rows])
    for r in rows:
        url = market_url(r, locale=locale)
        if not url:
            url = by_card.get(r.get("id") or r.get("card_id"))
        r["market_url"] = url
    return rows
