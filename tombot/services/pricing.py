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

from . import trust
from .variant_map import resolve

log = logging.getLogger(__name__)

# Which Cardmarket field to read for a given physical variant. Cardmarket exposes
# a reverse-holo series separately; everything else shares the card-level price.
VARIANT_PRICE_FIELDS = {
    "reverse": ["reverseHoloSell", "reverseHoloTrend", "reverseHoloAvg30"],
}
DEFAULT_FIELDS = ["averageSellPrice", "trendPrice", "avg30", "lowPrice"]


def _provider_name(source) -> str:
    """Short label for whoever supplied a quote."""
    return getattr(source, "name", None) or source.__class__.__name__.lower()


class PricingService:
    def __init__(self, repo, source, config, crosscheck=None):
        self.repo = repo
        self.source = source
        self.config = config
        # Optional second provider quoting the same market. Used to price a card
        # whose primary quote had to be refused, and recorded either way so the
        # UI can show what each provider said.
        self.crosscheck = crosscheck

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

        # Rows that already know their Cardmarket product need no resolution at
        # all: the product IS the answer, and twenty of them fit in one request.
        # This is the whole point of picking a version when the card is added.
        priced_by_product = self._prices_by_product(pairs)

        # Only the leftovers cost a resolution lookup. Fetching for everything
        # would spend requests answering questions already answered — which,
        # against a metered source, is spending money for nothing.
        needs_resolving = sorted({
            p["card_id"] for p in pairs
            if not (p.get("market_product_id")
                    and p["market_product_id"] in priced_by_product)
        })
        payloads = self.source.fetch_prices(needs_resolving) if needs_resolving else {}

        # Quotes from the second provider, for the cross-check and the fallback.
        alt = {}
        if self.crosscheck is not None:
            try:
                alt = self.crosscheck.fetch_prices(needs_resolving) or {}
            except Exception:                                # noqa: BLE001
                log.warning("cross-check provider unavailable", exc_info=True)

        today = date.today().isoformat()
        updated = unpriced = manual_kept = refused = recovered = 0
        by_product = 0
        for pair in pairs:
            card_id, variant = pair["card_id"], pair["variant"]

            if self.repo.get_price(card_id, variant, source="manual"):
                manual_kept += 1
                continue

            data = payloads.get(card_id)
            variants = (data or {}).get("variants") or []
            key = resolve(variant, [v["key"] for v in variants])
            chosen = next((v for v in variants if v["key"] == key), None)

            product_id = pair.get("market_product_id")
            direct = priced_by_product.get(product_id) if product_id else None
            if direct is not None:
                self.repo.upsert_quote(
                    card_id, variant, provider="tcggo", market="cardmarket",
                    printing=direct.get("version") or "", currency=direct["currency"],
                    price=direct["price"], low=direct.get("lowest_near_mint"),
                    product_id=product_id, trusted=True)
                self.repo.upsert_price(
                    card_id, variant, "cardmarket", direct["currency"],
                    direct["price"], None, None, None, direct,
                    variant_key=direct.get("version"),
                    market_product_id=product_id)
                self.repo.append_price_history(
                    card_id, variant, "cardmarket", direct["currency"],
                    direct["price"], today)
                updated += 1
                by_product += 1
                continue

            # Always record what the second provider says, even when the primary
            # is fine. That is what makes a disagreement visible later, and it
            # is the difference between showing one number and showing the
            # evidence behind it.
            fallback = self._crosscheck_price(card_id, variant, alt.get(card_id))

            reason = None
            if chosen:
                reason = trust.distrust_reason(chosen["market_product_id"], card_id)
                self.repo.upsert_quote(
                    card_id, variant, provider=_provider_name(self.source), market="cardmarket",
                    printing=chosen["key"], currency=chosen["currency"],
                    price=chosen["price"], product_id=chosen["market_product_id"],
                    trusted=reason is None, distrust_reason=reason,
                )
                if reason:
                    refused += 1
                    log.info("refused %s %s: %s", card_id, variant, reason)

            if not chosen or chosen["price"] is None or reason:
                # Either nothing matched, or what matched belongs to another
                # card. Fall back to the second provider before giving up.
                if fallback is None:
                    unpriced += 1
                    continue
                self.repo.upsert_price(
                    card_id, variant, "cardmarket", fallback["currency"],
                    fallback["price"], None, None, None, fallback,
                    variant_key=None, market_product_id=None,
                )
                self.repo.append_price_history(
                    card_id, variant, "cardmarket", fallback["currency"],
                    fallback["price"], today,
                )
                recovered += 1
                updated += 1
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
                "unpriced": unpriced, "manual_kept": manual_kept,
                "refused": refused, "recovered": recovered,
                "by_product": by_product}

    def _prices_by_product(self, pairs: list[dict]) -> dict:
        """Look up every already-chosen Cardmarket product, twenty per request.

        A row that names its product needs no variant translated and no
        printing resolved — the two steps that produced every mispriced card so
        far. It is a lookup, and a batched one.
        """
        ids = [p["market_product_id"] for p in pairs if p.get("market_product_id")]
        if not ids:
            return {}
        fetch = getattr(self.source, "fetch_by_products", None)
        if fetch is None:
            fetch = getattr(self.crosscheck, "fetch_by_products", None)
        if fetch is None:
            return {}
        try:
            return fetch(ids)
        except Exception:                                    # noqa: BLE001
            log.warning("product lookup failed; falling back to resolution",
                        exc_info=True)
            return {}

    def _crosscheck_price(self, card_id: str, variant: str, alt: dict | None):
        """Record the second provider's quotes and return a usable Cardmarket one.

        This provider maps one product per card, which is exactly what the
        primary gets wrong, so it is what a refused card falls back to. Its
        TCGplayer figures are stored too — a different market in a different
        currency, kept for display rather than folded into the valuation.
        """
        if not alt:
            return None

        for name, p in ((alt.get("tcgplayer") or {}).get("printings") or {}).items():
            if p.get("market") or p.get("mid") or p.get("low"):
                self.repo.upsert_quote(
                    card_id, variant, provider=_provider_name(self.crosscheck),
                    market="tcgplayer", printing=name, currency="USD",
                    price=p.get("market") or p.get("mid"),
                    low=p.get("low"), mid=p.get("mid"), high=p.get("high"),
                )

        prices = alt.get("prices") or {}
        value = self._pick(prices, variant)
        if value is None:
            return None
        self.repo.upsert_quote(
            card_id, variant, provider=_provider_name(self.crosscheck), market="cardmarket",
            printing="", currency=alt.get("currency") or "EUR", price=value,
            low=prices.get("lowPrice"), trend=prices.get("trendPrice"),
            avg30=prices.get("avg30"),
        )
        return {"currency": alt.get("currency") or "EUR", "price": value,
                "provider": _provider_name(self.crosscheck), "prices": prices}

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
