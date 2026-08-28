"""Materialise personal-set slots from a declarative rule.

The spec lists personal sets as prose ("Jungle (sin holos)") but stores only an
explicit card list, which would mean hand-curating ~1,100 rows and re-curating
them after every catalog refresh. Rules make it reproducible (PLAN.md §2.10).

Rule shape:
    {
      "include_sets":     ["base2"],
      "exclude_rarities": ["Rare Holo"],
      "exclude_supertypes": [],
      "exclude_cards":    ["base5-83"],
      "include_cards":    ["base4-4"],
      "merge": [ {"label": "Charizard", "cards": ["base1-4", "base4-4"]} ]
    }

`merge` is what makes reprints collapse into one completion slot.
"""
from __future__ import annotations

import json
import logging

log = logging.getLogger(__name__)


class SetBuilder:
    def __init__(self, repo):
        self.repo = repo

    def build(self, set_id: str) -> dict:
        cset = self.repo.get_collection_set(set_id)
        if not cset:
            raise LookupError(f"unknown personal set: {set_id}")
        rules = json.loads(cset.get("rules_json") or "{}")
        if not rules:
            return {"set": set_id, "slots": 0, "note": "no rules_json; slots left as-is"}

        candidates: list[dict] = []
        for osid in rules.get("include_sets", []):
            rows, _ = self.repo.search_cards(official_set=osid, page=1, page_size=100000)
            candidates.extend(rows)
        for cid in rules.get("include_cards", []):
            card = self.repo.get_card(cid)
            if card:
                candidates.append(card)

        excl_rarities = set(rules.get("exclude_rarities", []))
        excl_supertypes = set(rules.get("exclude_supertypes", []))
        excl_cards = set(rules.get("exclude_cards", []))
        # include_rarities, when present, keeps only those — the way "solo holos"
        # is expressed. Empty means no rarity filter.
        incl_rarities = set(rules.get("include_rarities", []))

        kept = [
            c for c in candidates
            if c["id"] not in excl_cards
            and (c.get("rarity") or "") not in excl_rarities
            and (c.get("supertype") or "") not in excl_supertypes
            and (not incl_rarities or (c.get("rarity") or "") in incl_rarities)
        ]

        # dedupe while preserving the release-date/number order search_cards returned
        seen, ordered = set(), []
        for c in kept:
            if c["id"] not in seen:
                seen.add(c["id"])
                ordered.append(c)

        merges = rules.get("merge", [])
        merged_ids = {cid for m in merges for cid in m.get("cards", [])}

        slots: list[dict] = []
        for m in merges:
            members = [cid for cid in m.get("cards", []) if cid in seen]
            if members:
                slots.append({"label": m.get("label"), "cards": members,
                              "display_card_id": members[0]})
        for c in ordered:
            if c["id"] in merged_ids:
                continue
            slots.append({"label": c["name"], "cards": [c["id"]], "display_card_id": c["id"]})

        for i, s in enumerate(slots):
            s["position"] = i

        written = self.repo.replace_rule_slots(set_id, slots)
        log.info("built %s: %d slots from %d candidates", set_id, written, len(candidates))
        return {"set": set_id, "slots": written, "candidates": len(candidates),
                "excluded": len(candidates) - len(ordered)}

    def build_all(self) -> list[dict]:
        return [self.build(s["id"]) for s in self.repo.list_collection_sets()]
