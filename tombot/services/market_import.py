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

        from .tcggo_catalog import resolve_collisions
        code = (rows[0].get("card_code_number") or "").rsplit(" ", 1)[0] if rows else ""
        product_rows = [self._row(r, episode_id, code) for r in self._dedupe(rows)]
        # Split any different cards that upstream gave the same code+number onto
        # distinct card_ids before storing, so their products never merge.
        resolve_collisions(product_rows)
        stored = self.repo.upsert_market_products(product_rows)
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
        """One row per PRINTING — per card and print run, not per product id.

        This used to key on `cardmarket_id` and skip any row without one, on the
        theory that the extra rows were phantoms Cardmarket does not sell. They
        are not. For Base Set tcggo sends 307 rows — 102 "1st Edition
        Shadowless", 100 "Shadowless", 101 "Unlimited" — which is one row per
        real print run of all 102 cards, and only 193 survived:

          * 83 lost because tcggo stamps two different print runs with one
            cardmarket_id (Charizard's 1st Edition Shadowless at 50,000 EUR and
            its Shadowless at 2,000 EUR both come back as 660224), so whichever
            arrived second overwrote the first;
          * 31 lost because tcggo sent no cardmarket_id at all — 28 of them
            carrying a real price. In Base Set 2 that is what removed 11 cards
            from the catalogue outright: a card whose only row has no product id
            has no products, and cards are built from products.

        So the key is (code, version): the card and its print run. Rows without
        a product id are kept — a printing with a price and no buy link is worth
        more than no printing. A genuine repeat of one printing keeps whichever
        row has an offer behind it.
        """
        best: dict[tuple, dict] = {}
        for raw in rows:
            key = ((raw.get("card_code_number") or "").strip(),
                   (raw.get("version") or "").strip())
            kept = best.get(key)
            if kept is None:
                best[key] = raw
                continue
            cm = ((raw.get("prices") or {}).get("cardmarket") or {})
            kept_cm = ((kept.get("prices") or {}).get("cardmarket") or {})
            # Prefer the row that can actually be bought, then the one that at
            # least carries a product id.
            if ((kept_cm.get("lowest_near_mint") is None
                 and cm.get("lowest_near_mint") is not None)
                    or (not kept.get("cardmarket_id") and raw.get("cardmarket_id"))):
                best[key] = raw
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
            # Cardmarket's id is an attribute of the printing, not its identity:
            # it repeats across print runs and is absent on some (#68).
            "cardmarket_id": raw.get("cardmarket_id"),
            "episode_id": episode_id,
            "code": code,
            "number": number,
            "card_id": card_id_for(episode_code or prefix, number),
            "name": raw.get("name"),
            # Never NULL — it is half the key, and SQLite counts NULLs as distinct.
            "version": (raw.get("version") or "").strip(),
            "rarity": raw.get("rarity"),
            "currency": cm.get("currency") or "EUR",
            "price": float(price) if price else None,
            "price_low": cm.get("lowest_near_mint"),
            "price_avg30": cm.get("30d_average"),
            "price_avg7": cm.get("7d_average"),
            "available": cm.get("available_items"),
            "image": raw.get("image"),
            "market_url": (raw.get("links") or {}).get("cardmarket"),
            "artist": _artist_name(raw.get("artist")),
            "supertype": raw.get("supertype"),
        }


def _artist_name(artist) -> str | None:
    """The illustrator's name, whatever shape tcggo sends it in.

    tcggo returns artist as {id, name, slug} on cards and occasionally as a bare
    string; both collapse to the display name.
    """
    if isinstance(artist, dict):
        return artist.get("name") or artist.get("slug") or None
    return artist or None
