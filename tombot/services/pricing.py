"""Price and value the collection from imported Cardmarket products.

Prices are read from `market_products` by the product id on each owned row, so
pricing is a local lookup with no network call. A row's value is its printing's
price times a condition multiplier (M/NM 1.00 down to PO), since no source
prices by condition — the factors are local and editable (price_modifiers).

Unpriced rows return None (shown as "—") rather than 0, so a missing price does
not read as "worth zero" in the totals.
"""
from __future__ import annotations

import logging
from datetime import date

from ..config import DEFAULT_CONDITION

log = logging.getLogger(__name__)

# Cardmarket prices reverse holo as its own series; every other variant shares
# the card-level price. Used when a variant has no product of its own but the
# card does — a reverse holo must not borrow the ordinary card's number.
VARIANT_PRICE_FIELDS = {"reverse"}


class PricingService:
    def __init__(self, repo, config):
        self.repo = repo
        self.config = config

    # ----------------------------------------------------------------- refresh
    def refresh(self, stale_days: int | None = None, all_cards: bool = False) -> dict:
        """Re-price every owned printing from the imported products.

        A row that names its Cardmarket product is priced from that product,
        exactly. A row with no product — added before a version was picked, or
        in a set not imported — is left unpriced rather than guessed at. Manual
        prices are never touched.

        No network: importing a set is what fetches prices, and this reads what
        that import stored. To get fresher numbers, re-import the set.
        """
        pairs = self.repo.owned_card_variants()
        if not pairs:
            return {"checked": 0, "updated": 0, "unpriced": 0, "manual_kept": 0}

        product_ids = [p["market_product_id"] for p in pairs
                       if p.get("market_product_id")]
        products = self.repo.market_products_by_ids(product_ids)

        today = date.today().isoformat()
        updated = unpriced = manual_kept = 0
        for pair in pairs:
            card_id, variant = pair["card_id"], pair["variant"]

            if self.repo.get_price(card_id, variant, source="manual"):
                manual_kept += 1
                continue

            product_id = pair.get("market_product_id")
            prod = products.get(product_id) if product_id else None
            if not prod or prod.get("price") is None:
                unpriced += 1
                continue

            self.repo.upsert_price(
                card_id, variant, "cardmarket", prod.get("currency") or "EUR",
                prod["price"], prod.get("price_low"), None, prod.get("price_avg30"),
                dict(prod), variant_key=prod.get("version"),
                market_product_id=product_id)
            self.repo.append_price_history(
                card_id, variant, "cardmarket", prod.get("currency") or "EUR",
                prod["price"], today)
            updated += 1

        self.repo.set_meta("last_price_refresh", today)
        return {"checked": len(pairs), "updated": updated,
                "unpriced": unpriced, "manual_kept": manual_kept}

    # -------------------------------------------------------------- estimate
    def estimate_item(self, item: dict, modifiers: dict | None = None) -> dict:
        """Estimated value of one collection row, including quantity.

        The printing's own price scaled by the condition multiplier. A wrong
        number is worse than no number here, because it lands in the dashboard
        total looking like fact, so missing data reports itself.
        """
        mods = modifiers if modifiers is not None else self.repo.get_modifiers()
        row = self.repo.get_price(item["card_id"], item.get("variant", "normal"))

        if not row or row.get("price") is None:
            # A variant with no price of its own can use the card-level price —
            # the same printing — but reverse holo, which is priced separately,
            # must not.
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

        # A missing multiplier used to become 1.00 in silence, valuing a played
        # card as mint. It now warns.
        condition = item.get("condition") or DEFAULT_CONDITION
        cond_m = mods.get("condition", {}).get(condition)
        if cond_m is None:
            log.warning("no multiplier for condition %r; using 1.00. The grade "
                        "is not in config.CONDITIONS.", condition)
            cond_m = 1.0
        first_ed_m = 2.0 if item.get("first_edition") else 1.0
        unit = round(row["price"] * cond_m * first_ed_m, 2)
        qty = int(item.get("quantity", 1))
        return {
            "unit": unit,
            "total": round(unit * qty, 2),
            "first_edition_multiplier": first_ed_m,
            "currency": row.get("currency", "EUR"),
            "basis": basis,
            "priced_variant": row.get("variant"),
            "condition_multiplier": cond_m,
            "variant_key": row.get("variant_key"),
            "manual": row.get("source") == "manual",
            "updated_at": row.get("updated_at"),
        }

    def value_collection(self) -> dict:
        """Total estimated value plus how much of it is actually priced.

        `unpriced_items` is reported so a low total reads as 'missing data'
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
                "coverage_pct": round(100.0 * priced / (priced + unpriced), 1)
                                if (priced + unpriced) else 100.0}
