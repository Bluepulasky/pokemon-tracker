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


class RateLimited(RuntimeError):
    """The upstream quota is exhausted.

    Distinct from a transient failure on purpose. A 500 is worth retrying in a
    few seconds; a spent daily quota is not worth retrying at all — without an
    API key the allowance is 1,000 requests/day, so the only useful responses
    are to stop, say so plainly, and point at the free key.
    """


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
        self.max_backoff = getattr(config, "HTTP_MAX_BACKOFF", 30)
        self.has_api_key = bool(config.POKEMONTCG_API_KEY)

    # ------------------------------------------------------------------ http
    @staticmethod
    def _retry_after(response) -> float | None:
        """Seconds to wait per the server, if it said."""
        raw = response.headers.get("Retry-After")
        if not raw:
            return None
        try:
            return max(0.0, float(raw))
        except ValueError:
            return None          # HTTP-date form; not worth parsing for this

    def _get(self, path: str, params: dict | None = None) -> dict:
        url = f"{self.base}{path}"
        last = None
        for attempt in range(self.retries):
            try:
                r = self.session.get(url, params=params, timeout=self.timeout)
                if r.status_code == 200 and r.content:
                    return r.json()
                if r.status_code in (429, 403):
                    # 403 is what this API returns once the daily allowance is
                    # gone, so it has to be treated as a quota signal too.
                    retry_after = self._retry_after(r)
                    if retry_after is not None and retry_after <= self.max_backoff:
                        log.warning("rate limited, server asked for %ss", retry_after)
                        time.sleep(retry_after)
                        continue
                    raise RateLimited(
                        f"upstream rate limit hit on {path}"
                        + (f"; server asked for {retry_after:.0f}s" if retry_after
                           else " (daily quota is the likely cause)"))
                last = f"HTTP {r.status_code}"
            except requests.RequestException as e:      # timeouts, DNS, resets
                last = str(e)
            wait = min(self.max_backoff, 2 ** attempt)
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
                status, loc = r.status_code, r.headers.get("Location")
                retry_after = self._retry_after(r)
                r.close()
                if loc and "cardmarket.com" in loc:
                    return loc.split("?", 1)[0]      # drop the utm_* tracking params
                if status in (429, 403):
                    # Previously this looked identical to "no link exists", so a
                    # rate limit silently marked cards unresolvable and the run
                    # kept hammering for another thousand cards.
                    raise RateLimited(
                        f"rate limited resolving market URL for {card_id}"
                        + (f"; server asked for {retry_after:.0f}s" if retry_after else ""))
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
