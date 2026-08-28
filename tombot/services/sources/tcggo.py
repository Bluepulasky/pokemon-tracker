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

    def __init__(self, config, budget=None, cache=None):
        self.base = getattr(config, "TCGGO_BASE_URL", BASE_URL)
        self.api_key = getattr(config, "TCGGO_API_KEY", None)
        self.game = getattr(config, "TCGGO_GAME", "pokemon")
        self.budget = budget
        # A response already paid for must never be paid for twice.
        self.cache = cache
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
        # The cache is consulted before the budget: a hit costs nothing, so it
        # must not consume an allowance slot or require a key.
        if self.cache is not None:
            hit = self.cache.get(path, params)
            if hit is not None:
                return hit

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
        payload = r.json()
        if self.cache is not None:
            self.cache.put(path, params, payload)
        return payload

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
        # The parameter is `tcgid`, not `tcg_id`. An unknown parameter is not
        # rejected — it is ignored, and the endpoint cheerfully returns page 1
        # of every card in the game, which reads exactly like a real answer.
        payload = self._get(f"/{self.game}/cards/search", {"tcgid": tcgid})
        rows = payload.get("data") or []
        if isinstance(rows, dict):
            rows = [rows]
        return [self.parse_card(c) for c in rows]

    # -------------------------------------------------------------- episodes
    def find_episode(self, name: str, code: str | None = None) -> dict | None:
        """The episode for a set, or None rather than a wrong one.

        Catalogue names disagree: ours says "Base Set", theirs says "Base", and
        searching the full name returns "Expedition Base Set" and "Base Set 2"
        but not the one we want. So the query is tried a few ways, and the code
        on a card ("BS 4") decides whenever it is available — it is the one
        identifier both sides spell the same.

        Guessing here is worse than failing: a wrong episode filters to the
        wrong set, and the answer still looks like data.
        """
        queries = [q for q in (code, name, name.strip().removesuffix(" Set").strip())
                   if q]
        seen: list[dict] = []
        for query in dict.fromkeys(queries):
            try:
                payload = self._get(f"/{self.game}/episodes/search", {"search": query})
            except RuntimeError as e:
                log.warning("episode search %r failed: %s", query, e)
                continue
            rows = payload.get("data") or []
            if isinstance(rows, dict):
                rows = [rows]
            seen.extend(rows)

            if code:
                exact_code = next((e for e in rows
                                   if (e.get("code") or "").upper() == code.upper()), None)
                if exact_code:
                    return exact_code
            wanted = {name.strip().lower(),
                      name.strip().removesuffix(" Set").strip().lower()}
            exact_name = next((e for e in rows
                               if (e.get("name") or "").strip().lower() in wanted), None)
            if exact_name:
                return exact_name

        log.warning("no episode matched %r (code %r); candidates were %s",
                    name, code, [e.get("name") for e in seen][:8])
        return None

    def search_episodes(self, query: str) -> list[dict]:
        """Sets whose name or code matches. One request, then cached."""
        payload = self._get(f"/{self.game}/episodes/search", {"search": query})
        rows = payload.get("data") or []
        return [rows] if isinstance(rows, dict) else rows

    # -------------------------------------------------------------- versions
    @staticmethod
    def as_version(card: dict) -> dict:
        """One row for the version picker: what it is, what it looks like, what it costs."""
        cm = ((card.get("prices") or {}).get("cardmarket") or {})
        episode = card.get("episode") or {}
        price = next((cm.get(f) for f in PRICE_FIELDS if cm.get(f)), None)
        return {
            "market_product_id": card.get("cardmarket_id"),
            "name": card.get("name"),
            "set": episode.get("name"),
            "code": card.get("card_code_number"),
            "number": card.get("card_number"),
            "version": card.get("version"),
            "rarity": card.get("rarity"),
            "image": card.get("image"),
            "market_url": (card.get("links") or {}).get("cardmarket"),
            "currency": cm.get("currency") or "EUR",
            "price": float(price) if price else None,
            "lowest_near_mint": cm.get("lowest_near_mint"),
            "available": cm.get("available_items"),
        }

    def search_versions(self, name: str, number: str | None = None,
                        episode_id: int | None = None) -> list[dict]:
        """Versions of a card that can actually be bought, ready to show.

        Keyed on the Cardmarket product, because that is the thing with a price.
        Two records claiming one product are the same product — Base Set
        Charizard comes back as both "Shadowless" and "1st Edition Shadowless"
        on product 660224, and only one of those is real. The one with an actual
        near-mint offer behind it wins; the phantom has none, and carries a
        price to match (10.46 for a card that sells in the hundreds).
        """
        params: dict = {"name": name, "sort": "episode_oldest"}
        if number:
            params["card_number"] = number
        if episode_id:
            # The only filter that reliably narrows to one set. Card numbers
            # are stored inconsistently — Base Set Charizard is "BS 4", Jungle
            # Flareon is 19 — so filtering by number alone silently drops
            # printings, and name alone paginates past the vintage sets.
            params["episode_id"] = episode_id
        payload = self._get(f"/{self.game}/cards/search", params)
        rows = payload.get("data") or []
        if isinstance(rows, dict):
            rows = [rows]

        best: dict[int, dict] = {}
        for row in rows:
            v = self.as_version(row)
            pid = v["market_product_id"]
            if not pid:
                continue
            kept = best.get(pid)
            if kept is None or (kept["lowest_near_mint"] is None
                                and v["lowest_near_mint"] is not None):
                best[pid] = v
        return sorted(best.values(),
                      key=lambda v: (v["set"] or "", v["version"] or ""))

    BATCH = 20          # the documented maximum for a comma-separated lookup

    def fetch_by_products(self, product_ids: list[int]) -> dict[int, dict]:
        """Prices for many Cardmarket products at once.

        Twenty per request rather than one, which is the difference between a
        collection refresh costing ten requests and costing two hundred. Stops
        when the allowance runs out and returns what it has.
        """
        out: dict[int, dict] = {}
        ids = [p for p in dict.fromkeys(product_ids) if p]
        for i in range(0, len(ids), self.BATCH):
            chunk = ids[i:i + self.BATCH]
            try:
                payload = self._get(f"/{self.game}/cards/search",
                                    {"cardmarket_ids": ",".join(map(str, chunk))})
            except BudgetExhausted as e:
                log.warning("stopping after %d products: %s", len(out), e)
                break
            except RuntimeError as e:
                log.warning("batch of %d failed: %s", len(chunk), e)
                continue
            rows = payload.get("data") or []
            if isinstance(rows, dict):
                rows = [rows]
            for row in rows:
                v = self.as_version(row)
                pid = v["market_product_id"]
                kept = out.get(pid)
                # Same dedupe as the picker: a phantom sharing a product id has
                # no near-mint offer behind it.
                if pid and (kept is None or (kept["lowest_near_mint"] is None
                                             and v["lowest_near_mint"] is not None)):
                    out[pid] = v
        return out

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
