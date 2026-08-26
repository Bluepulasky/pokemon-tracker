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
SHADOWLESS_SETS = {"base1"}

HOLO_RARITIES = {"Rare Holo", "Rare Secret", "Rare Holo EX", "Rare Shining"}


def variants_for(official_set_id: str, rarity: str | None,
                 release_date: str | None = None) -> list[str]:
    """Physical variants a card of this rarity, in this set, can be found as."""
    rarity = rarity or ""
    variants: list[str] = ["holo"] if rarity in HOLO_RARITIES else ["normal"]

    if official_set_id in WOTC_EARLY:
        variants.append("first_edition")
        if official_set_id in SHADOWLESS_SETS:
            variants.append("shadowless")
    else:
        # Reverse holo became standard from the e-Card era onward and is the one
        # within-printing variant the upstream ever prices separately.
        if rarity and rarity not in HOLO_RARITIES:
            variants.append("reverse")

    variants.append("other")
    return list(dict.fromkeys(variants))
