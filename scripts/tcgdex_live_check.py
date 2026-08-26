"""Validate the TCGdex adapter against the live API.

Runs in CI because api.tcgdex.net is unreachable from some networks (it refuses
connections from Argentina, where this adapter was written). GitHub's runners can
reach it, so CI is the integration test.

Two jobs:
  1. assert the structural invariants the adapter depends on still hold
  2. write the fetched payloads to disk so they can be picked up as fixtures

Exits non-zero if an invariant breaks, so a change in the upstream shape is a
failed build rather than a silent mis-pricing.
"""
from __future__ import annotations

import json
import os
import pathlib
import sys
import time
import urllib.error
import urllib.request

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from tombot.services.sources.tcgdex import parse_variants  # noqa: E402

CARDS = [
    "base1-4", "base1-58", "base1-7", "base2-1", "base3-1", "base5-1",
    "basep-1", "ex7-15", "ex7-51", "gym1-1", "gym2-1",
    "neo1-1", "neo2-1", "neo3-1", "neo4-1",
]
OUT = pathlib.Path(os.environ.get("TCGDEX_OUT", "tcgdex-live"))


def fetch(card_id: str) -> dict | None:
    url = f"https://api.tcgdex.net/v2/en/cards/{card_id}"
    req = urllib.request.Request(url, headers={"User-Agent": "tombot-ci/0.1"})
    for attempt in range(4):
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                return json.loads(r.read())
        except urllib.error.HTTPError as e:
            if e.code == 404:
                return None
            print(f"  {card_id}: HTTP {e.code}")
        except Exception as e:                       # noqa: BLE001
            print(f"  {card_id}: {e}")
        time.sleep(2 ** attempt)
    return None


def check(card: dict) -> list[str]:
    """Invariants the adapter's correctness rests on."""
    problems: list[str] = []
    cid = card["id"]
    variants = parse_variants(card)

    if not variants:
        return [f"{cid}: no variants parsed"]

    # 1. keys stay unique, or a print run is silently lost
    keys = [v["key"] for v in variants]
    if len(keys) != len(set(keys)):
        problems.append(f"{cid}: duplicate variant keys {keys}")

    # 2. `-holo` is the reverse price. A populated one on a card with no reverse
    #    variant would mean the field means something else.
    if not card.get("variants", {}).get("reverse"):
        for entry in card.get("variants_detailed") or []:
            cm = (entry.get("pricing") or {}).get("cardmarket") or {}
            if cm.get("avg-holo"):
                problems.append(
                    f"{cid}: avg-holo={cm['avg-holo']} but the card has no reverse")

    # 3. no variant may read a `-holo` field unless it is the reverse
    for v in variants:
        if v["type"] != "reverse" and (v["price_field"] or "").endswith("-holo"):
            problems.append(f"{cid}/{v['key']}: {v['type']} read {v['price_field']}")

    # 4. a price and the field it came from travel together
    for v in variants:
        if (v["price"] is None) != (v["price_field"] is None):
            problems.append(f"{cid}/{v['key']}: price/field mismatch")

    # 5. the multiplier flag is never set on an unpriced variant
    for v in variants:
        if v["price"] is None and v["first_edition_multiplier_applies"]:
            problems.append(f"{cid}/{v['key']}: multiplier flagged with no price")

    return problems


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    problems: list[str] = []
    fetched = missing = 0

    for card_id in CARDS:
        card = fetch(card_id)
        if card is None:
            print(f"  {card_id}: NOT FOUND")
            missing += 1
            continue
        fetched += 1
        (OUT / f"{card_id}.json").write_text(json.dumps(card, indent=2, ensure_ascii=False))

        variants = parse_variants(card)
        priced = sum(1 for v in variants if v["price"] is not None)
        print(f"  {card_id:<10} variants={len(variants):<2} priced={priced:<2} "
              f"keys={[v['key'] for v in variants]}")
        problems += check(card)

    print(f"\nfetched {fetched}, missing {missing}, written to {OUT}/")

    if problems:
        print("\nINVARIANTS BROKEN:")
        for p in problems:
            print(f"  - {p}")
        return 1
    if fetched == 0:
        print("\nnothing fetched — treating as failure")
        return 1
    print("\nall invariants hold")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
