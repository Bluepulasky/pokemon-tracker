"""Which TCG series (era) a set belongs to, derived from its release date.

tcggo's own `series` field is sparse and inconsistent — many sets come back
blank, or tagged with their own name — so grouping the Sets view by it produced
a wall of one-set headers. The eras are, however, strictly chronological and
non-overlapping: each runs from its first set until the next era begins. So a
set's era is simply the latest era that had started by its release date.

This is a small, stable reference — the TCG era timeline, taken from
pokemoncardlist.net/sets — not a per-set list: these ~16 boundaries place all
~200 sets that exist and any set released later. Dates are YYYY/MM/DD to match
how release dates are stored. Ordered oldest-first; each start is the release of
that era's earliest main-line set.
"""
from __future__ import annotations

_ERAS: list[tuple[str, str]] = [
    ("Base",                   "1999/01/09"),
    ("Gym",                    "2000/08/14"),
    ("Neo",                    "2000/12/16"),
    ("Legendary Collection",   "2002/05/24"),
    ("E-Card",                 "2002/09/15"),
    ("EX",                     "2003/07/01"),
    ("Diamond & Pearl",        "2007/05/01"),
    ("Platinum",               "2009/02/11"),
    ("HeartGold & SoulSilver", "2010/02/10"),
    ("Call of Legends",        "2011/02/09"),
    ("Black & White",          "2011/04/25"),
    ("XY",                     "2014/02/05"),
    ("Sun & Moon",             "2017/02/03"),
    ("Sword & Shield",         "2020/02/07"),
    ("Scarlet & Violet",       "2023/03/31"),
    ("Mega Evolution",         "2025/09/25"),
]


def series_for_date(release_date: str | None) -> str | None:
    """The era a set belongs to, or None if its date is missing or pre-Base.

    The boundaries sort ascending, so the answer is the last era whose start is
    on or before the set's release. String comparison is chronological because
    the dates are fixed-width YYYY/MM/DD.
    """
    if not release_date:
        return None
    era = None
    for name, start in _ERAS:
        if release_date >= start:
            era = name
        else:
            break
    return era
