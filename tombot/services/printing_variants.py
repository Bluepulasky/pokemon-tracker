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


def variant_from_product(version: str | None, rarity: str | None) -> str:
    """The single collection variant a chosen Cardmarket product represents.

    The add-card modal has one selector now — the version picker — and the
    product it points at decides everything. This maps that product's `version`
    (and `rarity`, the one thing the version string never says) onto the fixed
    variant vocabulary, so the row records what the card physically is without a
    second dropdown asking again.

    It is also what keeps two products of the SAME card distinct: the collection
    row is unique on (card_id, variant, condition, language), so a Chansey held
    as both "Unlimited" and "1st Edition Shadowless" must land on different
    variants (normal vs shadowless) or the second would fold into the first.

    Order matters — "1st Edition Shadowless" is a shadowless run, so shadowless
    is checked before 1st edition, matching how the picker used to fill the boxes.
    """
    v = (version or "").lower()
    r = (rarity or "").lower()
    if "reverse" in v or "reverse" in r:
        return "reverse"
    if "shadowless" in v:
        return "shadowless"
    if "1st edition" in v or "first edition" in v:
        return "first_edition"
    if "holo" in v or "holo" in r:
        return "holo"
    return "normal"


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
