"""Match a collection item's variant to a TCGdex printing.

The collection records variants in the app's own vocabulary — normal, holo,
reverse, first_edition, shadowless, other — chosen so a user can pick one without
knowing TCGdex's keys. TCGdex describes printings as `holo:shadowless:1st-edition`
and similar. This resolves one to the other.

A miss returns None rather than the nearest printing. Guessing here is how a
Shadowless Charizard ends up valued as an Unlimited one.
"""
from __future__ import annotations

# Subtypes that mean "the ordinary open print run" rather than a special one.
ORDINARY = ("unlimited", None, "")


def _score(key: str, variant: str) -> int | None:
    """How well a TCGdex key matches our variant. Higher is better, None is no match."""
    parts = key.split(":")
    kind, rest = parts[0], parts[1:]
    stamped_first = "1st-edition" in rest
    shadowless = any(p.startswith("shadowless") for p in rest)
    # A printing carrying an oddity — a jumbo, an error stamp, a promo tour
    # stamp — is never what a plain variant means.
    oddity = any(
        p not in ("unlimited", "1st-edition", "cosmos", "starlight", "galaxy",
                  "set-logo")
        and not p.startswith("shadowless")
        for p in rest
    )

    if variant == "first_edition":
        return None if not stamped_first else (20 if not oddity else 5)
    if variant == "shadowless":
        # The unstamped shadowless run; the stamped one belongs to first_edition.
        return None if not shadowless or stamped_first else 20
    if variant == "reverse":
        return None if kind != "reverse" else 20

    # normal / holo / other: an ordinary printing of the right kind.
    if variant in ("normal", "holo") and kind != variant:
        return None
    if stamped_first or shadowless or oddity:
        return None
    return 20 if any(p in ORDINARY for p in (rest or [None])) else 10


def resolve(variant: str, keys: list[str]) -> str | None:
    """Best TCGdex printing key for this variant, or None if nothing fits."""
    scored = [(s, k) for k in keys if (s := _score(k, variant)) is not None]
    if not scored:
        return None
    # Ties break on the shorter key: fewer qualifiers means a plainer printing.
    return max(scored, key=lambda sk: (sk[0], -len(sk[1])))[1]
