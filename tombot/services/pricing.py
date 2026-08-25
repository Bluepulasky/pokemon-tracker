"""Price fetch, cache and estimation.

Two things the spec gets optimistic about and this module handles honestly:

1. No public source prices by condition or by printing language. The estimate is
   base_price x condition_multiplier x language_multiplier, with the multipliers
   stored in price_modifiers and editable (PLAN.md §2.12).
2. "No price data" is NOT "worth zero". Unpriced cards return None and are shown
   as "—", so the dashboard total never quietly under-reports.
"""
from __future__ import annotations

import logging
from datetime import date

log = logging.getLogger(__name__)

# Which Cardmarket field to read for a given physical variant. Cardmarket exposes
# a reverse-holo series separately; everything else shares the card-level price.
VARIANT_PRICE_FIELDS = {
    "reverse": ["reverseHoloSell", "reverseHoloTrend", "reverseHoloAvg30"],
}
DEFAULT_FIELDS = ["averageSellPrice", "trendPrice", "avg30", "lowPrice"]


class PricingService:
    def __init__(self, repo, source, config):
        self.repo = repo
        self.source = source
        self.config = config

    # ----------------------------------------------------------------- fetch
    def refresh(self, stale_days: int | None = None, all_cards: bool = False) -> dict:
        """Refresh prices for cards actually in the collection (spec §30)."""
        stale_days = self.config.PRICE_STALE_DAYS if stale_days is None else stale_days
        pairs = (self.repo.owned_card_variants() if all_cards
                 else self.repo.stale_priced_pairs(stale_days))
        if not pairs:
            return {"checked": 0, "updated": 0, "unpriced": 0}

        card_ids = sorted({p["card_id"] for p in pairs})
        payloads = self.source.fetch_prices(card_ids)

        today = date.today().isoformat()
        updated = unpriced = 0
        for pair in pairs:
            data = payloads.get(pair["card_id"])
            if not data:
                unpriced += 1
                continue
            prices = data["prices"]
            price = self._pick(prices, pair["variant"])
            if price is None:
                unpriced += 1
                continue
            self.repo.upsert_price(
                pair["card_id"], pair["variant"], data["source"], data["currency"],
                price, prices.get("lowPrice"), prices.get("trendPrice"),
                prices.get("avg30"), prices,
            )
            self.repo.append_price_history(
                pair["card_id"], pair["variant"], data["source"],
                data["currency"], price, today,
            )
            updated += 1

        self.repo.set_meta("last_price_refresh", today)
        return {"checked": len(pairs), "updated": updated, "unpriced": unpriced}

    def _pick(self, prices: dict, variant: str) -> float | None:
        fields = VARIANT_PRICE_FIELDS.get(variant, [])
        basis = self.config.PRICE_BASIS
        for f in [*fields, basis, *DEFAULT_FIELDS]:
            v = prices.get(f)
            if v:                       # upstream uses 0.0 for "no data", not null
                return float(v)
        return None

    # -------------------------------------------------------------- estimate
    def estimate_item(self, item: dict, modifiers: dict | None = None) -> dict:
        """Estimated value of one collection row, including quantity.

        Fallback chain (spec §14): exact (card, variant) -> card, any variant -> unpriced.
        """
        mods = modifiers if modifiers is not None else self.repo.get_modifiers()
        row = self.repo.get_price(item["card_id"], item.get("variant", "normal"))
        basis = "exact"
        if not row or row.get("price") is None:
            candidates = [p for p in self.repo.get_prices_for_card(item["card_id"])
                          if p.get("price") is not None]
            row = candidates[0] if candidates else None
            basis = "variant_fallback"
        if not row or row.get("price") is None:
            return {"unit": None, "total": None, "currency": "EUR",
                    "basis": "unpriced", "updated_at": None}

        cond_m = mods.get("condition", {}).get(item.get("condition", "NM"), 1.0)
        lang_m = mods.get("language", {}).get(item.get("language", "es"), 1.0)
        unit = round(row["price"] * cond_m * lang_m, 2)
        qty = int(item.get("quantity", 1))
        return {
            "unit": unit,
            "total": round(unit * qty, 2),
            "currency": row.get("currency", "EUR"),
            "basis": basis,
            "condition_multiplier": cond_m,
            "language_multiplier": lang_m,
            "updated_at": row.get("updated_at"),
        }

    def value_collection(self) -> dict:
        """Total estimated value plus how much of it is actually priced.

        `unpriced_items` is reported so a low total can be read as 'missing data'
        rather than 'cheap collection'.
        """
        mods = self.repo.get_modifiers()
        total = 0.0
        priced = unpriced = 0
        per_set: dict[str, float] = {}
        page = 1
        while True:
            rows, count = self.repo.list_collection(page=page, page_size=500)
            if not rows:
                break
            for r in rows:
                est = self.estimate_item(r, mods)
                if est["total"] is None:
                    unpriced += 1
                    continue
                priced += 1
                total += est["total"]
                per_set[r["official_set_id"]] = round(
                    per_set.get(r["official_set_id"], 0.0) + est["total"], 2)
            if page * 500 >= count:
                break
            page += 1
        return {"total_eur": round(total, 2), "priced_items": priced,
                "unpriced_items": unpriced, "by_official_set": per_set}
