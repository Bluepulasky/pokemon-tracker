"""Import a set's Cardmarket products in bulk.

Asking per card is what made the allowance the bottleneck. Registering 150
cards cost 150 requests, for products that all live in a handful of sets — and
Base Set comes back whole in four.

This does not replace the catalog import. That one is free (pokemontcg.io),
and it is where the card ids, numbers and images come from — the things the
slot model is built on. tcggo's own `tcgid` is populated on only some records,
so it cannot supply those ids. What this adds is the other half: which products
exist to buy, and what they cost.

Deliberately resumable. It imports whole sets, stops when the remaining
allowance would not cover another one, and picks up where it left off on the
next run. A first start therefore never spends the day's budget in one go, and
never leaves a set half-imported.
"""
from __future__ import annotations

import logging

from .budget import BudgetExhausted

log = logging.getLogger(__name__)

PAGE_SIZE = 100          # the documented maximum; the default of 20 is 5x the cost


class MarketImporter:
    def __init__(self, repo, source, budget=None):
        self.repo = repo
        self.source = source
        self.budget = budget

    def import_episode(self, episode_id: int) -> dict:
        """Every product in one set, 100 per request."""
        rows, page, spent_before = [], 1, self._used()
        while page <= 60:                      # a set is never this large
            try:
                payload = self.source._get(
                    f"/{self.source.game}/cards/search",
                    {"episode_id": episode_id, "page": page,
                     "per_page": PAGE_SIZE, "sort": "card_number_lowest"})
            except BudgetExhausted:
                log.warning("episode %s stopped at page %d: allowance spent",
                            episode_id, page)
                break
            batch = payload.get("data") or []
            if not batch:
                break
            rows.extend(batch)
            if len(batch) < PAGE_SIZE:
                break
            page += 1

        code = (rows[0].get("card_code_number") or "").rsplit(" ", 1)[0] if rows else ""
        stored = self.repo.upsert_market_products(
            [self._row(r, episode_id, code) for r in self._dedupe(rows)])
        return {"episode_id": episode_id, "fetched": len(rows), "stored": stored,
                "requests": self._used() - spent_before}

    def import_sets(self, official_set_ids, episode_for_set) -> dict:
        """Import each set, stopping while there is still allowance to stop with.

        Whole sets only: half a set looks imported and answers wrongly, which
        is worse than a set that has not been imported at all.
        """
        done, skipped, requests = [], [], 0
        for set_id in official_set_ids:
            episode_id = episode_for_set(set_id)
            if episode_id is None:
                skipped.append({"set": set_id, "why": "no episode matched"})
                continue
            if self.budget is not None and not self.budget.can_afford(6):
                skipped.append({"set": set_id, "why": "allowance too low; will resume"})
                continue
            result = self.import_episode(episode_id)
            requests += result["requests"]
            done.append({"set": set_id, **result})
        return {"imported": done, "skipped": skipped, "requests": requests}

    # ------------------------------------------------------------- internals
    def _used(self) -> int:
        return self.budget.used() if self.budget is not None else 0

    def _dedupe(self, rows: list[dict]) -> list[dict]:
        """One row per Cardmarket product.

        The source returns a third version for nearly every Base Set card that
        Cardmarket does not sell — 307 rows where Cardmarket lists 211. The
        phantom shares its product id and has no near-mint offer behind it.
        """
        best: dict[int, dict] = {}
        for raw in rows:
            pid = raw.get("cardmarket_id")
            if not pid:
                continue
            cm = ((raw.get("prices") or {}).get("cardmarket") or {})
            kept = best.get(pid)
            if kept is None:
                best[pid] = raw
                continue
            kept_nm = ((kept.get("prices") or {}).get("cardmarket") or {}).get("lowest_near_mint")
            if kept_nm is None and cm.get("lowest_near_mint") is not None:
                best[pid] = raw
        return list(best.values())

    @staticmethod
    def _row(raw: dict, episode_id: int, episode_code: str = "") -> dict:
        from .tcggo_catalog import card_id_for, split_code

        cm = ((raw.get("prices") or {}).get("cardmarket") or {})
        # The number comes from card_code_number, never from card_number:
        # that field holds "BS 4" on some rows and 4 on others, and building an
        # id from it splits one card into two.
        code = raw.get("card_code_number") or ""
        prefix, number = split_code(code)
        price = next((cm.get(f) for f in ("30d_average", "7d_average", "lowest_near_mint")
                      if cm.get(f)), None)
        return {
            "product_id": raw.get("cardmarket_id"),
            "episode_id": episode_id,
            "code": code,
            "number": number,
            "card_id": card_id_for(episode_code or prefix, number),
            "name": raw.get("name"),
            "version": raw.get("version"),
            "rarity": raw.get("rarity"),
            "currency": cm.get("currency") or "EUR",
            "price": float(price) if price else None,
            "price_low": cm.get("lowest_near_mint"),
            "price_avg30": cm.get("30d_average"),
            "price_avg7": cm.get("7d_average"),
            "available": cm.get("available_items"),
            "image": raw.get("image"),
            "market_url": (raw.get("links") or {}).get("cardmarket"),
        }
