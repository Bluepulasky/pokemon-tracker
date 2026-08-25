"""The user's personal sets, as declarative rules.

Set IDs and rarity distributions were verified against the live pokemontcg.io API
(PLAN.md §2.11). "sin holos" maps exactly onto rarity 'Rare Holo'; "sin comunes"
onto 'Common'.

Editing this file and re-running `flask seed-sets --rebuild` is non-destructive:
manual slot edits are preserved, and collection items are never touched.
"""

NO_HOLO = ["Rare Holo"]

PERSONAL_SETS = [
    # --- Gen1 -------------------------------------------------------------
    {"id": "base-set", "name": "Base Set", "group_name": "Gen1", "position": 10,
     "description": "Base Set completo (102).",
     "rules": {"include_sets": ["base1"]}},

    {"id": "jungle-no-holos", "name": "Jungle (sin holos)", "group_name": "Gen1", "position": 20,
     "description": "Jungle sin las 16 Rare Holo → 48 cartas.",
     "rules": {"include_sets": ["base2"], "exclude_rarities": NO_HOLO}},

    {"id": "fossil-no-holos", "name": "Fossil (sin holos)", "group_name": "Gen1", "position": 30,
     "description": "Fossil sin las 15 Rare Holo → 47 cartas.",
     "rules": {"include_sets": ["base3"], "exclude_rarities": NO_HOLO}},

    {"id": "team-rocket-no-holos", "name": "Team Rocket (sin holos)", "group_name": "Gen1",
     "position": 40,
     "description": "Team Rocket sin Rare Holo. Dark Raichu #83 (Rare Secret) se mantiene.",
     "rules": {"include_sets": ["base5"], "exclude_rarities": NO_HOLO}},

    {"id": "gym-heroes-no-holos", "name": "Gym Heroes (sin holos)", "group_name": "Gen1",
     "position": 50,
     "rules": {"include_sets": ["gym1"], "exclude_rarities": NO_HOLO}},

    {"id": "gym-challenge-no-holos", "name": "Gym Challenge (sin holos)", "group_name": "Gen1",
     "position": 60,
     "rules": {"include_sets": ["gym2"], "exclude_rarities": NO_HOLO}},

    {"id": "wotc-promos", "name": "WOTC Promos", "group_name": "Gen1", "position": 70,
     "description": "Wizards Black Star Promos (53).",
     "rules": {"include_sets": ["basep"]}},

    # --- Gen 2 ------------------------------------------------------------
    {"id": "neo-genesis-no-holos", "name": "Neo Genesis (sin holos)", "group_name": "Gen 2",
     "position": 110, "rules": {"include_sets": ["neo1"], "exclude_rarities": NO_HOLO}},

    {"id": "neo-discovery-no-holos", "name": "Neo Discovery (sin holos)", "group_name": "Gen 2",
     "position": 120, "rules": {"include_sets": ["neo2"], "exclude_rarities": NO_HOLO}},

    {"id": "neo-revelation-no-holos", "name": "Neo Revelation (sin holos)", "group_name": "Gen 2",
     "position": 130, "rules": {"include_sets": ["neo3"], "exclude_rarities": NO_HOLO}},

    {"id": "neo-destiny-no-holos", "name": "Neo Destiny (sin holos)", "group_name": "Gen 2",
     "position": 140, "rules": {"include_sets": ["neo4"], "exclude_rarities": NO_HOLO}},

    # --- Gen 3 ------------------------------------------------------------
    {"id": "ex-team-rocket-returns-no-commons", "name": "EX Team Rocket Returns (sin comunes)",
     "group_name": "Gen 3", "position": 210,
     "rules": {"include_sets": ["ex7"], "exclude_rarities": ["Common"]}},
]

# Official sets the catalog import needs, derived from the rules above.
def required_official_sets() -> list[str]:
    out: list[str] = []
    for s in PERSONAL_SETS:
        for osid in s["rules"].get("include_sets", []):
            if osid not in out:
                out.append(osid)
    return out
