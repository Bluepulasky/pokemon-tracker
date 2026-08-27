"""tcggo (CardMarket API TCG on RapidAPI).

Why it is here: it maps one Cardmarket product per card where TCGdex maps one
product to several. Asked which card owns product 273800, it answers with
exactly one — Jungle Flareon #3, the holo — which is the mapping that makes the
non-holo price four to six times too high everywhere else.

It also carries what neither other source does: the print run as a first-class
`version` field, lowest-near-mint per country, how many copies are actually for
sale, and eBay sold medians by grade.

It is not clean everywhere. Base Set Charizard "Shadowless" and "1st Edition
Shadowless" are separate cards here, correctly, but both report Cardmarket
product 660224 with contradictory prices (2,475.96 and 10.46). So the same
shared-product guard applies to this source too; it is not a reason to trust it
blindly, only a reason to prefer it where it is right.

**Every request is metered.** The plan bills per request past a daily
allowance, so nothing here talks to the network without first reserving a slot
from RequestBudget, and a run that hits the cap returns what it has instead of
spending money.
"""
from __future__ import annotations

import logging

import requests

from ..budget import BudgetExhausted

log = logging.getLogger(__name__)

BASE_URL = "https://cardmarket-api-tcg.p.rapidapi.com"
RAPIDAPI_HOST = "cardmarket-api-tcg.p.rapidapi.com"

# Print runs, as tcggo spells them, mapped onto the app's own variant keys.
VERSION_TO_KEY = {
    "unlimited": "unlimited",
    "1st edition": "1st-edition",
    "shadowless": "shadowless",
    "1st edition shadowless": "1st-edition:shadowless",
    "unlimited holo": "unlimited",
    "4th print": "unlimited",
}

# Cardmarket figures, in the order we would rather have them.
PRICE_FIELDS = ("30d_average", "7d_average", "lowest_near_mint")


class TcggoSource:
    name = "tcggo"

    def __init__(self, config, budget=None):
        self.base = getattr(config, "TCGGO_BASE_URL", BASE_URL)
        self.api_key = getattr(config, "TCGGO_API_KEY", None)
        self.game = getattr(config, "TCGGO_GAME", "pokemon")
        self.budget = budget
        self.session = requests.Session()
        if self.api_key:
            self.session.headers.update({
                "x-rapidapi-key": self.api_key,
                "x-rapidapi-host": getattr(config, "TCGGO_RAPIDAPI_HOST",
                                           RAPIDAPI_HOST),
            })

    @property
    def configured(self) -> bool:
        return bool(self.api_key)

    # ------------------------------------------------------------------ http
    def _get(self, path: str, params: dict | None = None) -> dict:
        """One metered request. Reserves budget first; never retries blindly.

        A retry is a second billable request, so a failure is reported rather
        than quietly re-sent.
        """
        if not self.api_key:
            raise RuntimeError("tcggo: no API key configured (TCGGO_API_KEY)")
        if self.budget is not None:
            self.budget.reserve(1)          # raises BudgetExhausted, sends nothing

        r = self.session.get(f"{self.base}{path}", params=params or {}, timeout=30)
        if r.status_code == 401:
            raise RuntimeError("tcggo: the API key was rejected (401)")
        if r.status_code == 429:
            raise RuntimeError("tcggo: rate limited by the plan (429)")
        if r.status_code >= 400:
            raise RuntimeError(f"tcggo: HTTP {r.status_code} for {path}")
        return r.json()

    # --------------------------------------------------------------- parsing
    @staticmethod
    def variant_key(card: dict) -> str:
        version = (card.get("version") or "").strip().lower()
        return VERSION_TO_KEY.get(version, version.replace(" ", "-") or "unlimited")

    @staticmethod
    def parse_card(card: dict) -> dict:
        """One card record into the shape the pricing service stores."""
        cm = ((card.get("prices") or {}).get("cardmarket") or {})
        price = next((cm.get(f) for f in PRICE_FIELDS if cm.get(f)), None)
        by_country = {
            k.rsplit("_", 1)[-1].lower(): v
            for k, v in cm.items()
            if k.startswith("lowest_near_mint_") and not k.endswith("EU_only")
            and v is not None
        }
        return {
            "provider": "tcggo",
            "source_id": card.get("id"),
            "tcgid": card.get("tcgid"),
            "name": card.get("name"),
            "number": card.get("card_number"),
            "set_code": (card.get("card_code_number") or "").split(" ")[0] or None,
            "rarity": card.get("rarity"),
            "version": card.get("version"),
            "key": TcggoSource.variant_key(card),
            "market_product_id": card.get("cardmarket_id"),
            "tcgplayer_id": card.get("tcgplayer_id"),
            "currency": cm.get("currency") or "EUR",
            "price": float(price) if price else None,
            "price_low": cm.get("lowest_near_mint"),
            "price_avg30": cm.get("30d_average"),
            "price_avg7": cm.get("7d_average"),
            # How many copies are actually listed. A "price" with nothing for
            # sale behind it is a number, not an offer.
            "available_items": cm.get("available_items"),
            "lowest_by_country": by_country,
        }

    # ---------------------------------------------------------------- prices
    def fetch_by_tcgid(self, tcgid: str) -> list[dict]:
        """Every printing tcggo holds for one pokemontcg.io card id."""
        payload = self._get(f"/{self.game}/cards/search", {"tcg_id": tcgid})
        rows = payload.get("data") or []
        if isinstance(rows, dict):
            rows = [rows]
        return [self.parse_card(c) for c in rows]

    def fetch_prices(self, card_ids: list[str]) -> dict[str, dict]:
        """Prices for as many of these cards as the budget allows.

        Stops cleanly when the allowance runs out and returns what it has: a
        partial refresh costs nothing extra and the rest resumes tomorrow.
        """
        out: dict[str, dict] = {}
        for card_id in card_ids:
            try:
                variants = self.fetch_by_tcgid(card_id)
            except BudgetExhausted as e:
                log.warning("stopping after %d cards: %s", len(out), e)
                break
            except RuntimeError as e:
                log.warning("skipping %s: %s", card_id, e)
                continue
            if variants:
                out[card_id] = {"source": "cardmarket", "variants": variants}
        return out
