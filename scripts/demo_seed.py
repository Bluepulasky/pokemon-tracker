"""Seed a realistic demo collection so the UI can be evaluated with real content.

Purely for testing/demo. `--clear` removes every collection item and photo and
leaves the catalog and personal sets untouched.

    python scripts/demo_seed.py          # seed
    python scripts/demo_seed.py --clear  # wipe collection only
"""
import random
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from tombot.config import Config
from tombot.services.repository import PokemonRepo

# (personal set id, roughly how much of it is owned)
FILL = [
    ("base-set", 0.42),
    ("jungle-no-holos", 0.60),
    ("fossil-no-holos", 0.38),
    ("team-rocket-no-holos", 0.22),
    ("gym-heroes-no-holos", 0.15),
    ("gym-challenge-no-holos", 0.08),
    ("wotc-promos", 0.30),
    ("neo-genesis-no-holos", 0.12),
    ("neo-discovery-no-holos", 0.05),
    ("ex-team-rocket-returns-no-commons", 0.10),
]

# Weighted so the collection looks like a real one: mostly NM Spanish singles,
# with a tail of played cards, English/Portuguese copies and a few duplicates.
CONDITIONS = (["M/NM"] * 60) + (["EX"] * 22) + (["GD"] * 11) + (["PL"] * 5) + ["PO"] * 2
LANGUAGES = (["es"] * 62) + (["en"] * 27) + (["pt"] * 8) + ["other"] * 3
QUANTITIES = ([1] * 74) + ([2] * 18) + ([3] * 6) + [4, 5]


def clear(repo: PokemonRepo) -> None:
    with repo.tx() as c:
        n = c.execute("SELECT COUNT(*) FROM collection_items").fetchone()[0]
        c.execute("DELETE FROM collection_photos")
        c.execute("DELETE FROM collection_items")
        c.execute("DELETE FROM collection_snapshots")
    print(f"removed {n} collection items (catalog and sets untouched)")


def seed(repo: PokemonRepo) -> None:
    rng = random.Random(20260825)          # deterministic: same demo every time
    added = 0

    for set_id, fill in FILL:
        slots = repo.get_set_slots(set_id)
        if not slots:
            print(f"  ! {set_id}: no slots, skipping (run `flask seed-sets` first)")
            continue
        chosen = rng.sample(slots, int(len(slots) * fill))
        for slot in chosen:
            card_id = slot["card_id"]
            if not card_id:
                continue
            rarity = slot.get("rarity") or ""
            variant = "holo" if "Holo" in rarity else "normal"
            repo.upsert_collection_item({
                "card_id": card_id,
                "variant": variant,
                "condition": rng.choice(CONDITIONS),
                "language": rng.choice(LANGUAGES),
                "quantity": rng.choice(QUANTITIES),
            })
            added += 1

            # ~8% of cards also exist in a second physical variant, which is the
            # case the completion logic has to get right: still one card owned.
            if rng.random() < 0.08:
                repo.upsert_collection_item({
                    "card_id": card_id,
                    "variant": "normal" if variant == "holo" else "holo",
                    "condition": rng.choice(CONDITIONS),
                    "language": rng.choice(LANGUAGES),
                    "quantity": 1,
                })
                added += 1

        p = repo.set_progress(set_id)[0]
        print(f"  {set_id:<36} {p['owned']:>4} / {p['target']:<4} slots")

    t = repo.collection_totals()
    print(f"\nseeded {added} rows · {t['unique_cards']} unique cards · "
          f"{t['physical_cards']} physical cards")


def backfill_history(repo: PokemonRepo, months: int = 9) -> None:
    """FABRICATED history so the evolution chart has something to draw.

    Real snapshots only start accumulating once `flask monthly` runs, so a fresh
    install has a single point. These rows are demo scaffolding, not real data —
    `--clear` removes them.
    """
    from datetime import date, timedelta

    rng = random.Random(99)
    today = date.today()
    t = repo.collection_totals()
    progress = repo.set_progress()
    target = sum(p["target"] or 0 for p in progress)
    owned_now = sum(p["owned"] or 0 for p in progress)

    from tombot.services.pricing import PricingService
    value_now = 0.0
    mods = repo.get_modifiers()
    svc = PricingService(repo, None, Config)
    rows, _ = repo.list_collection(page=1, page_size=1000)
    for r in rows:
        est = svc.estimate_item(r, mods)
        if est["total"]:
            value_now += est["total"]

    for i in range(months, 0, -1):
        d = today - timedelta(days=30 * i)
        growth = (months - i + 1) / (months + 1)          # collection grew over time
        drift = 1 + rng.uniform(-0.06, 0.06)              # market noise
        repo.write_snapshot({
            "captured_on": d.isoformat(),
            "unique_cards": int(t["unique_cards"] * growth),
            "physical_cards": int(t["physical_cards"] * growth),
            "sets_total": len(progress),
            "sets_complete": 0,
            "completion_pct": round(100.0 * owned_now * growth / target, 2) if target else 0,
            "value_eur": round(value_now * growth * drift, 2),
            "breakdown_json": None,
        })
    print(f"backfilled {months} months of DEMO history")


if __name__ == "__main__":
    Config.ensure_dirs()
    repo = PokemonRepo(Config.DB_PATH)
    clear(repo)
    if "--clear" not in sys.argv:
        seed(repo)
        backfill_history(repo)
