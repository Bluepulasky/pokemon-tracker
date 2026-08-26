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

from .variant_map import resolve

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
        """Refresh prices for the printings actually held (spec §30).

        Each owned (card, variant) is matched to a specific TCGdex printing, so a
        Shadowless Charizard is priced as Shadowless rather than as the Unlimited
        print. A variant with no matching printing is left unpriced rather than
        borrowing a neighbouring one.

        Manual prices are never touched.
        """
        stale_days = self.config.PRICE_STALE_DAYS if stale_days is None else stale_days
        pairs = (self.repo.owned_card_variants() if all_cards
                 else self.repo.stale_priced_pairs(stale_days))
        if not pairs:
            return {"checked": 0, "updated": 0, "unpriced": 0, "manual_kept": 0}

        card_ids = sorted({p["card_id"] for p in pairs})
        payloads = self.source.fetch_prices(card_ids)

        today = date.today().isoformat()
        updated = unpriced = manual_kept = 0
        for pair in pairs:
            card_id, variant = pair["card_id"], pair["variant"]

            if self.repo.get_price(card_id, variant, source="manual"):
                manual_kept += 1
                continue

            data = payloads.get(card_id)
            variants = (data or {}).get("variants") or []
            key = resolve(variant, [v["key"] for v in variants])
            chosen = next((v for v in variants if v["key"] == key), None)

            if not chosen or chosen["price"] is None:
                unpriced += 1
                continue

            self.repo.upsert_price(
                card_id, variant, data["source"], chosen["currency"],
                chosen["price"], None, None, None, chosen,
                variant_key=chosen["key"],
                market_product_id=chosen["market_product_id"],
            )
            self.repo.append_price_history(
                card_id, variant, data["source"], chosen["currency"],
                chosen["price"], today,
            )
            updated += 1

        self.repo.set_meta("last_price_refresh", today)
        return {"checked": len(pairs), "updated": updated,
                "unpriced": unpriced, "manual_kept": manual_kept}

    def _pick(self, prices: dict, variant: str) -> float | None:
        """Price for this variant, or None.

        A variant the upstream prices separately — reverse holo is the only one —
        is read ONLY from its own fields. Falling through to the card-level price
        when those are empty is how a reverse holo silently acquired the price of
        the ordinary card, which is the valuation bug this addresses.

        Everything else legitimately uses the card-level price: the upstream
        publishes one number per card id, so holo and non-holo of the same
        printing genuinely share it.
        """
        dedicated = VARIANT_PRICE_FIELDS.get(variant)
        if dedicated:
            for f in dedicated:
                v = prices.get(f)
                if v:                   # upstream uses 0.0 for "no data", not null
                    return float(v)
            return None                 # no data for this variant; do not guess

        for f in [self.config.PRICE_BASIS, *DEFAULT_FIELDS]:
            v = prices.get(f)
            if v:
                return float(v)
        return None

    # -------------------------------------------------------------- estimate
    def estimate_item(self, item: dict, modifiers: dict | None = None) -> dict:
        """Estimated value of one collection row, including quantity.

        Priced against the exact printing the user recorded and nothing else.

        There used to be a fallback that borrowed the price of any other variant
        of the same card. That silently valued a Charizard reprint at the Base
        Set price and vice versa — a wrong number is worse than no number here,
        because it lands in the dashboard total looking like fact. Missing data
        now reports itself.
        """
        mods = modifiers if modifiers is not None else self.repo.get_modifiers()
        row = self.repo.get_price(item["card_id"], item.get("variant", "normal"))

        if not row or row.get("price") is None:
            # The upstream prices a card id as a whole, so a variant with no
            # entry of its own legitimately falls back to the card-level price —
            # that is the same printing, not a different one.
            card_level = self.repo.get_price(item["card_id"], "normal")
            if card_level and card_level.get("price") is not None \
                    and item.get("variant") not in VARIANT_PRICE_FIELDS:
                row, basis = card_level, "printing_level"
            else:
                return {"unit": None, "total": None, "currency": "EUR",
                        "basis": "no_data", "updated_at": None,
                        "reason": "sin precio para esta impresión"}
        else:
            basis = "exact"

        cond_m = mods.get("condition", {}).get(item.get("condition", "NM"), 1.0)
        lang_m = mods.get("language", {}).get(item.get("language", "es"), 1.0)
        # A 1st edition is never priced apart from its unstamped twin by the
        # feed, so the premium is applied here. Editable per variant, because a
        # single figure cannot be right for both a Charizard and a common.
        var_m = mods.get("variant", {}).get(item.get("variant", "normal"), 1.0)
        unit = round(row["price"] * cond_m * lang_m * var_m, 2)
        qty = int(item.get("quantity", 1))
        return {
            "unit": unit,
            "total": round(unit * qty, 2),
            "currency": row.get("currency", "EUR"),
            "basis": basis,
            "priced_variant": row.get("variant"),
            "condition_multiplier": cond_m,
            "language_multiplier": lang_m,
            "variant_multiplier": var_m,
            "variant_key": row.get("variant_key"),
            "manual": row.get("source") == "manual",
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
                "unpriced_items": unpriced, "by_official_set": per_set,
                # Surfaced so a low total reads as missing data rather than a
                # cheap collection.
                "coverage_pct": round(100.0 * priced / (priced + unpriced), 1)
                                if (priced + unpriced) else 100.0}
