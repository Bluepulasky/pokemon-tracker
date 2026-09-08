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
import unicodedata

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


def _slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", (text or "").lower()).strip("-")


def normalized_name(text: str) -> str:
    """A card name reduced to what two spellings of it agree on.

    tcggo does not spell a card the same way on every print run. The Base Set
    unlimited product says "Pokemon Center" where the shadowless one says
    "Pokémon Center", and "Nidoran M" where the other says "Nidoran ♂". Compared
    literally those read as two different cards; compared through here they do
    not. Gender signs first, because they carry no accent to strip.
    """
    s = (text or "").replace("♂", "m").replace("♀", "f")
    s = unicodedata.normalize("NFKD", s)
    s = "".join(c for c in s if not unicodedata.combining(c))
    return re.sub(r"[^a-z0-9]+", "", s.lower())


def resolve_collisions(rows: list[dict]) -> list[dict]:
    """Give genuinely different cards distinct card_ids, in place.

    card_id is `{setcode}-{number}`, which assumes code+number identifies a card
    within an episode. Some episodes break that: the tcggo "Celebrations" episode
    bundles the Classic Collection under the same CEL code, so its Blastoise
    ("CEL 2") lands on the same id as the base Reshiram ("CEL 2"), and five cards
    share "CEL 15".

    **The illustrator is what tells the two cases apart** (#69). Splitting on the
    name instead said that Base Set had 106 cards: tcggo spells four of them
    differently on the shadowless products than on the unlimited ones — "Nidoran
    ♂"/"Nidoran M", "Pokemon Center"/"Pokémon Center", "Pokémon Flute"/"Pokemon
    Flute", "Imposter Professor Oak"/"Impostor Professor Oak" — and each spelling
    became its own card. A reprint reuses the artwork, so two products of one
    card share an illustrator (all four pairs are Ken Sugimori or Keiji
    Kinebuchi) while two different cards under one code do not (every one of the
    twelve Celebrations collisions has a different artist). Note the last pair:
    "Imposter" vs "Impostor" is a real letter apart, so no amount of normalising
    the name would have merged it. The artist would.

    The artist is only used when every product in the group has one; a group
    where any of them is blank falls back to comparing normalised names, which
    is the weaker signal but still better than the raw string.

    When a split does happen the lowest Cardmarket product id keeps the plain id
    — the base card, added to Cardmarket first — and the others take
    `{id}-{name-slug}`, so every logical card ends up with its own id and its own
    products.
    """
    from collections import defaultdict
    by_id: dict[str, list[dict]] = defaultdict(list)
    for r in rows:
        by_id[r["card_id"]].append(r)

    for cid, group in by_id.items():
        artists = [(r.get("artist") or "").strip().lower() for r in group]
        buckets: dict[str, list[dict]] = defaultdict(list)
        if all(artists):
            for r, artist in zip(group, artists):
                buckets[artist].append(r)
        else:
            # No illustrator on at least one product: fall back to the name,
            # compared through normalized_name so an accent is not a new card.
            for r in group:
                buckets[normalized_name(r.get("name"))].append(r)
        if len(buckets) <= 1:
            continue                                   # one card, its printings
        # The bucket whose cheapest product id is lowest keeps the plain id.
        ordered = sorted(buckets.values(),
                         key=lambda sub: min(x["product_id"] for x in sub))
        used = {cid}
        for sub in ordered[1:]:
            name = min(sub, key=lambda x: x["product_id"]).get("name") or ""
            base = f"{cid}-{_slug(name)}" if _slug(name) else cid
            # Two different illustrators can still print under one name; the
            # suffix has to stay unique or the split would undo itself.
            new_id, n = base, 2
            while new_id in used:
                new_id, n = f"{base}-{n}", n + 1
            used.add(new_id)
            for r in sub:
                r["card_id"] = new_id
    return rows


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
            # others, and sqlite will not bind a dict. It is stored as-is; the
            # Sets view groups by an era derived from release_date instead (see
            # services/tcg_series.py), because tcggo's series is too sparse.
            "series": _text(episode.get("series")),
            "printed_total": episode.get("cards_printed_total"),
            "total": episode.get("cards_total"),
            "release_date": (episode.get("released_at") or "").replace("-", "/"),
            "ptcgo_code": code,
            "logo_url": _text(episode.get("logo")) or None,
            "symbol_url": None,
        })

        # One card per card_id; its versions are the products sharing it. Grouping
        # by card_id (not code) is what keeps two different cards that upstream
        # gave the same code+number — Celebrations base vs Classic Collection —
        # apart: resolve_collisions has already given them distinct ids.
        by_card: dict[str, list[dict]] = {}
        for p in products:
            by_card.setdefault(p["card_id"], []).append(p)

        cards = []
        for card_id, group in by_card.items():
            _, number = split_code(group[0]["code"])
            # Prefer a row with a real offer behind it for the display data:
            # the phantom versions carry the emptier records.
            best = max(group, key=lambda r: (r["price_low"] is not None,
                                             r["available"] or 0))
            cards.append({
                "id": card_id,
                "official_set_id": set_id,
                "name": best["name"],
                "number": number,
                "number_sort": number_sort(number),
                "rarity": canonical_rarity(best["rarity"]),
                "image_small_url": best["image"],
                "image_large_url": best["image"],
                # The illustrator, used as the reprint-group key: a reprint reuses
                # the artwork, so same name + same artist is the same logical card.
                "artist": best.get("artist"),
                # Pokémon / Trainer / Energy — the only card-type tcggo gives us
                # (its `type` field is the product kind, "singles"), and what the
                # Cartas "Tipo" filter runs on.
                "supertype": best.get("supertype"),
            })
        self.repo.upsert_cards(cards)

        # Products already carry their card_id from the import, so pricing is a
        # join on our own key rather than a guess.
        return {"set_id": set_id, "cards": len(cards), "products": len(products)}
