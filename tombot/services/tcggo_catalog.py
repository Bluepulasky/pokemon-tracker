"""Build the catalog from tcggo alone.

The app used to take its card list from pokemontcg.io and its prices from
tcggo, joined on pokemontcg.io's id. That join was the problem: tcggo populates
`tcgid` on only some rows, so the join silently picked whichever row had one —
which is how a Base Set Charizard came back at 8.89 EUR.

With one source there is no join. A card is identified by where it sits in a
set, which is the one thing both halves of the data agree on:

    episode BS, number 4  ->  card "bs-4"

and the versions of it are the Cardmarket products carrying that code. The
import that fetches the catalog is the same import that fetches the prices, so
the card list costs nothing extra.
"""
from __future__ import annotations

import logging
import re

log = logging.getLogger(__name__)


def card_id_for(episode_code: str, number) -> str:
    """A stable id from the set code and the card number.

    Not tcggo's row id: a card has several rows, one per version, and any of
    them could be the phantom. The position in the set is the identity.
    """
    code = re.sub(r"[^a-z0-9]+", "", (episode_code or "").lower())
    num = re.sub(r"[^a-z0-9]+", "-", str(number or "").lower()).strip("-")
    return f"{code}-{num}"


def split_code(card_code_number: str) -> tuple[str, str]:
    """"BS 4" -> ("BS", "4"). The number keeps letters: "SK H7" -> ("SK", "H7")."""
    parts = (card_code_number or "").rsplit(" ", 1)
    return (parts[0], parts[1]) if len(parts) == 2 else (card_code_number or "", "")


def number_sort(number: str) -> float:
    """Numeric where it can be, so #10 does not sort before #2."""
    m = re.match(r"^(\d+)", str(number or ""))
    return float(m.group(1)) if m else 9e6


# Rarity decides which cards a rule-based set contains, and the source spells
# it three ways: "Rare Holo", "Holo Rare" and "rare". Jungle has sixteen holos
# and the source calls thirteen of them one thing and three another, so a rule
# excluding "Rare Holo" would drop thirteen and keep three — a set of 51 where
# it should be 48, with nothing to show anything went wrong.
RARITY_CANON = {
    "rare holo": "Rare Holo",
    "holo rare": "Rare Holo",
    "rare": "Rare",
    "common": "Common",
    "uncommon": "Uncommon",
    "rare holo ex": "Rare Holo EX",
    "classic collection": "Classic Collection",
}


def canonical_rarity(value: str | None) -> str | None:
    if not value:
        return None
    return RARITY_CANON.get(value.strip().lower(), value.strip())


def _text(value) -> str:
    """A display string, whatever shape the field arrives in."""
    if value is None:
        return ""
    if isinstance(value, dict):
        return str(value.get("name") or value.get("slug") or "")
    return str(value)


class TcggoCatalog:
    """Turns imported market products into sets and cards."""

    def __init__(self, repo):
        self.repo = repo

    def build_set(self, episode: dict) -> dict:
        """One episode's products into an official set and its cards."""
        episode_id = episode["id"]
        code = episode.get("code") or str(episode_id)
        products = self.repo._all(
            "SELECT * FROM market_products WHERE episode_id=? ORDER BY code",
            (episode_id,))
        if not products:
            return {"set_id": None, "cards": 0, "why": "nothing imported"}

        set_id = code.lower()
        self.repo.upsert_official_set({
            "id": set_id,
            "name": episode.get("name") or code,
            # `series` arrives as an object on some episodes and a string on
            # others, and sqlite will not bind a dict.
            "series": _text(episode.get("series")),
            "printed_total": episode.get("cards_printed_total"),
            "total": episode.get("cards_total"),
            "release_date": (episode.get("released_at") or "").replace("-", "/"),
            "ptcgo_code": code,
            "logo_url": _text(episode.get("logo")) or None,
            "symbol_url": None,
        })

        # One card per code; its versions are the products carrying that code.
        by_code: dict[str, list[dict]] = {}
        for p in products:
            by_code.setdefault(p["code"], []).append(p)

        cards = []
        for card_code, group in by_code.items():
            _, number = split_code(card_code)
            # Prefer a row with a real offer behind it for the display data:
            # the phantom versions carry the emptier records.
            best = max(group, key=lambda r: (r["price_low"] is not None,
                                             r["available"] or 0))
            cards.append({
                "id": card_id_for(code, number),
                "official_set_id": set_id,
                "name": best["name"],
                "number": number,
                "number_sort": number_sort(number),
                "rarity": canonical_rarity(best["rarity"]),
                "image_small_url": best["image"],
                "image_large_url": best["image"],
            })
        self.repo.upsert_cards(cards)

        # Products already carry their card_id from the import, so pricing is a
        # join on our own key rather than a guess.
        return {"set_id": set_id, "cards": len(cards), "products": len(products)}
