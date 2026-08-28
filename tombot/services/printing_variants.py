"""Which physical variants a given printing can exist in.

The catalog does not carry this: pokemontcg.io describes a card, not the ways it
was physically produced. It is derived from the set and the rarity, which is
where the information actually lives.

The WOTC era is the case that matters here — a Base Set holo rare exists as
1st Edition, Shadowless and Unlimited, and those are genuinely different objects
to a collector. Later sets did not print those distinctions.

Note this is about *identification*, not price. pokemontcg.io publishes one price
per card id, so Shadowless and Unlimited Charizard share a number no matter how
carefully they are told apart here. Recording the variant still matters — it is
what the card is — and the pricing layer says "sin datos" rather than pretending.
"""
from __future__ import annotations

# Sets printed with the 1st Edition stamp / Shadowless run.
WOTC_EARLY = {"base1", "base2", "base3", "base5", "gym1", "gym2",
              "neo1", "neo2", "neo3", "neo4"}
# Base Set specifically had a Shadowless print run; the others did not.
#
# Still a list of ids, and still the weakest thing here: it answers wrongly for
# any catalogue whose ids differ. It survives only as the fallback for a card
# with no imported products and no release date. When products exist, the print
# runs come from them and this is not consulted at all — see
# api/catalog.py, which builds `editions` from what was actually imported.
SHADOWLESS_SETS = {"base1", "bs"}

HOLO_RARITIES = {"Rare Holo", "Rare Secret", "Rare Holo EX", "Rare Shining"}


# Reverse holos begin with Legendary Collection. Nothing printed before that
# date exists as one, so offering it on a Base Set trainer is not a harmless
# extra option — it is a variant that cannot be bought, priced, or owned.
REVERSE_HOLO_FROM = "2002/05/24"


def _predates_reverse_holo(release_date: str | None) -> bool | None:
    """True/False when the date is known, None when it is not."""
    if not release_date:
        return None
    return release_date.replace("-", "/") < REVERSE_HOLO_FROM


def variants_for(official_set_id: str, rarity: str | None,
                 release_date: str | None = None) -> list[str]:
    """Physical variants a card of this rarity, in this set, can be found as.

    Decided by the set's release date where we know it. It used to be decided
    by membership of a hardcoded list of catalogue set ids, which answers
    confidently and wrongly for any catalogue whose ids differ: "base1" is in
    the list, "bs" is not, so Base Set was treated as a modern set and every
    non-holo in it was offered as a reverse holo.
    """
    rarity = rarity or ""
    variants: list[str] = ["holo"] if rarity in HOLO_RARITIES else ["normal"]

    early = _predates_reverse_holo(release_date)
    if early is None:                      # no date: fall back to the id list
        early = official_set_id in WOTC_EARLY

    if early:
        variants.append("first_edition")
        if official_set_id in SHADOWLESS_SETS:
            variants.append("shadowless")
    elif rarity and rarity not in HOLO_RARITIES:
        variants.append("reverse")

    variants.append("other")
    return list(dict.fromkeys(variants))
