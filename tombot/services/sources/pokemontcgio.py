"""api.pokemontcg.io v2 adapter.

This is both the catalog and the price source. Cardmarket's own API is
application-gated and not obtainable for a personal project, but pokemontcg.io
republishes Cardmarket EUR prices per card with no account required
(PLAN.md §2.2).

The endpoint is genuinely unreliable — HTTP 500 on a meaningful fraction of
calls, including on documented single-resource paths. Everything here retries
with backoff, and callers must treat a failed set as resumable rather than fatal.
"""
from __future__ import annotations

import logging
import time
from typing import Iterator

import requests

log = logging.getLogger(__name__)

CARD_FIELDS = ("id,name,supertype,subtypes,types,number,artist,rarity,"
               "images,cardmarket,tcgplayer,set")


class PokemonTcgIoSource:
    name = "pokemontcgio"

    def __init__(self, config):
        self.base = config.POKEMONTCG_BASE_URL
        self.timeout = config.HTTP_TIMEOUT
        self.retries = config.HTTP_RETRIES
        self.session = requests.Session()
        if config.POKEMONTCG_API_KEY:
            self.session.headers["X-Api-Key"] = config.POKEMONTCG_API_KEY
        self.session.headers["User-Agent"] = "tombot-pokemon-tracker/0.1"

    # ------------------------------------------------------------------ http
    def _get(self, path: str, params: dict | None = None) -> dict:
        url = f"{self.base}{path}"
        last = None
        for attempt in range(self.retries):
            try:
                r = self.session.get(url, params=params, timeout=self.timeout)
                if r.status_code == 200 and r.content:
                    return r.json()
                if r.status_code == 429:
                    wait = min(60, 5 * 2 ** attempt)
                    log.warning("rate limited, sleeping %ss", wait)
                    time.sleep(wait)
                    continue
                last = f"HTTP {r.status_code}"
            except requests.RequestException as e:      # timeouts, DNS, resets
                last = str(e)
            wait = min(30, 2 ** attempt)
            log.warning("%s %s failed (%s), retry %d/%d in %ss",
                        path, params, last, attempt + 1, self.retries, wait)
            time.sleep(wait)
        raise RuntimeError(f"{url} failed after {self.retries} attempts: {last}")

    # --------------------------------------------------------------- catalog
    def fetch_set(self, set_id: str) -> dict:
        data = self._get("/sets", {"q": f"id:{set_id}", "pageSize": 1})["data"]
        if not data:
            raise LookupError(f"set not found upstream: {set_id}")
        s = data[0]
        return {
            "id": s["id"],
            "name": s.get("name"),
            "series": s.get("series"),
            "printed_total": s.get("printedTotal"),
            "total": s.get("total"),
            "release_date": s.get("releaseDate"),
            "ptcgo_code": s.get("ptcgoCode"),
            "logo_url": (s.get("images") or {}).get("logo"),
            "symbol_url": (s.get("images") or {}).get("symbol"),
        }

    def fetch_cards(self, set_id: str) -> Iterator[dict]:
        page = 1
        while True:
            payload = self._get("/cards", {
                "q": f"set.id:{set_id}", "page": page,
                "pageSize": 250, "select": CARD_FIELDS,
            })
            rows = payload.get("data") or []
            for c in rows:
                yield self._normalise_card(c, set_id)
            if page * payload.get("pageSize", 250) >= payload.get("totalCount", 0):
                return
            page += 1

    @staticmethod
    def _normalise_card(c: dict, set_id: str) -> dict:
        images = c.get("images") or {}
        return {
            "id": c["id"],
            "official_set_id": (c.get("set") or {}).get("id") or set_id,
            "name": c.get("name"),
            "number": c.get("number"),
            "rarity": c.get("rarity"),
            "supertype": c.get("supertype"),
            "subtypes": c.get("subtypes") or [],
            "types": c.get("types") or [],
            "artist": c.get("artist"),
            "image_small_url": images.get("small"),
            "image_large_url": images.get("large"),
            "external_ids": {
                "pokemontcgio": c["id"],
                "cardmarket_url": (c.get("cardmarket") or {}).get("url"),
                "tcgplayer_url": (c.get("tcgplayer") or {}).get("url"),
            },
            "source": "pokemontcgio",
        }

    # ----------------------------------------------------------- market links
    def resolve_market_url(self, card_id: str) -> str | None:
        """Resolve the per-card Cardmarket product URL.

        `cardmarket.url` in the payload is a prices.pokemontcg.io redirector, not
        a Cardmarket address. The real slug is Cardmarket-internal and not
        derivable — 'Charizard-V2-BS4', 'Brocks-Rhydon-GH2' — so it has to be
        read once from the Location header and stored.

        Only the redirector is contacted; the redirect is never followed into
        Cardmarket, which blocks automated requests anyway.
        """
        url = f"https://prices.pokemontcg.io/cardmarket/{card_id}"
        for attempt in range(3):
            try:
                r = self.session.get(url, timeout=self.timeout,
                                     allow_redirects=False, stream=True)
                loc = r.headers.get("Location")
                r.close()
                if loc and "cardmarket.com" in loc:
                    return loc.split("?", 1)[0]      # drop the utm_* tracking params
            except requests.RequestException as e:
                log.debug("market url resolve failed for %s: %s", card_id, e)
            time.sleep(1 + attempt)
        return None

    # ---------------------------------------------------------------- prices
    def fetch_prices(self, card_ids: list[str]) -> dict[str, dict]:
        """Batched by id. 800 owned cards is ~4 calls, not 800 (spec §11/§30)."""
        out: dict[str, dict] = {}
        BATCH = 60          # the q= string has a practical length limit upstream
        for i in range(0, len(card_ids), BATCH):
            chunk = card_ids[i:i + BATCH]
            q = " OR ".join(f"id:{cid}" for cid in chunk)
            try:
                payload = self._get("/cards", {
                    "q": q, "pageSize": 250, "select": "id,cardmarket,tcgplayer",
                })
            except RuntimeError as e:
                # A dead batch must not abort the whole run; the rest still refresh.
                log.error("price batch failed, skipping %d cards: %s", len(chunk), e)
                continue
            for c in payload.get("data") or []:
                cm = c.get("cardmarket") or {}
                if cm.get("prices"):
                    out[c["id"]] = {
                        "source": "cardmarket",
                        "currency": "EUR",
                        "updated_at": cm.get("updatedAt"),
                        "prices": cm["prices"],
                    }
        return out
