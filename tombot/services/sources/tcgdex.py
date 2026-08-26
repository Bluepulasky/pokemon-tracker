"""api.tcgdex.net adapter.

Chosen over pokemontcg.io for prices because it is the only source found that
separates print runs. pokemontcg.io publishes one Cardmarket number per card id,
so a Base Set Charizard reads €487 whether it is the Unlimited print or the
Shadowless one — which are €487 and €3,091 respectively.

Two properties of the payload drive everything below, both established by
reading real responses rather than the documentation:

1. Several variant entries can share one Cardmarket product. `1st-edition`
   always shares its `idProduct` with the same subtype minus the stamp, so it is
   never priced separately and needs a multiplier instead.

2. `avg-holo` / `trend-holo` are the REVERSE HOLO price, not "the holo price".
   A card with no holo at all (ex7-51 Cubone) still carries a populated
   `avg-holo` for its reverse, and a holo-only card (base1-4 Charizard) carries
   its price in plain `avg` with `avg-holo` null. Reading `-holo` for a holo
   variant would leave every Shadowless Charizard unpriced.
"""
from __future__ import annotations

import logging
import time
from typing import Iterator

import requests

from .pokemontcgio import RateLimited

log = logging.getLogger(__name__)

BASE_URL = "https://api.tcgdex.net/v2"

# Cardmarket price fields, in the order we prefer them.
BASE_FIELDS = ("avg", "trend", "avg30", "avg7", "low")
# The same series for the reverse-holo product line.
REVERSE_FIELDS = ("avg-holo", "trend-holo", "avg30-holo", "avg7-holo", "low-holo")


def price_fields_for(variant_type: str) -> tuple[str, ...]:
    """Which Cardmarket fields describe this variant.

    Only `reverse` reads the `-holo` series. Everything else — including `holo` —
    reads the plain series, because the plain series describes whatever the card's
    main product is.
    """
    return REVERSE_FIELDS if variant_type == "reverse" else BASE_FIELDS


def variant_key(entry: dict) -> str:
    """Stable local key for a variant entry.

    Built from type, subtype and stamps rather than the API's `variantId`, which
    is opaque and not obviously stable across their data rebuilds. This also
    reads back in the UI: `holo:shadowless:1st-edition`.
    """
    parts = [entry.get("type") or "normal"]
    if entry.get("subtype"):
        parts.append(entry["subtype"])
    for stamp in sorted(entry.get("stamp") or []):
        parts.append(stamp)
    # base3-1 has two `holo:pre-release` printings that differ only by foil
    # pattern (cosmos vs starlight). Without this they collapse into one key and
    # a print run disappears.
    if entry.get("foil"):
        parts.append(entry["foil"])
    if entry.get("size") and entry["size"] != "standard":
        parts.append(entry["size"])
    return ":".join(parts)


def variant_label(entry: dict) -> str:
    """Human label for the edition dropdown."""
    bits = []
    subtype = (entry.get("subtype") or "").replace("-", " ")
    if subtype:
        bits.append(subtype.title())
    bits.append((entry.get("type") or "normal").title())
    for stamp in entry.get("stamp") or []:
        bits.append(stamp.replace("-", " ").title())
    if entry.get("foil"):
        bits.append(entry["foil"].title())
    if entry.get("size") and entry["size"] != "standard":
        bits.append(entry["size"].title())
    return " ".join(dict.fromkeys(bits))


def parse_variants(card: dict) -> list[dict]:
    """Normalise `variants_detailed` into rows we can store.

    An entry with no `pricing` key at all (1999-2000-copyright) and one with
    `pricing.cardmarket: null` (WOTC promos) both mean the same thing: no price.
    Neither falls back to another variant's number.
    """
    entries = card.get("variants_detailed") or []

    # Which Cardmarket products are exclusive to 1st-edition printings.
    #
    # This differs by set and it matters for the multiplier. In Base Set, Team
    # Rocket and Neo the 1st-edition entry shares its product with the unstamped
    # one, so the stored price is the ordinary print and a multiplier is the only
    # way to value a 1st edition. In Gym Heroes and Gym Challenge the unstamped
    # entry has no product at all and the ONLY priced product is the 1st-edition
    # one — applying a multiplier there would double a price that already is the
    # 1st edition.
    stamped_only: set[int] = set()
    for entry in entries:
        cm = (entry.get("pricing") or {}).get("cardmarket") or {}
        pid = cm.get("idProduct")
        if not pid or "1st-edition" not in (entry.get("stamp") or []):
            continue
        has_plain_twin = any(
            ((o.get("pricing") or {}).get("cardmarket") or {}).get("idProduct") == pid
            and "1st-edition" not in (o.get("stamp") or [])
            for o in entries
        )
        if not has_plain_twin:
            stamped_only.add(pid)

    out: list[dict] = []
    for entry in entries:
        cm = (entry.get("pricing") or {}).get("cardmarket") or {}
        fields = price_fields_for(entry.get("type") or "normal")
        price = next((cm[f] for f in fields if cm.get(f)), None)
        out.append({
            "key": variant_key(entry),
            "label": variant_label(entry),
            "type": entry.get("type") or "normal",
            "subtype": entry.get("subtype"),
            "stamps": list(entry.get("stamp") or []),
            "size": entry.get("size") or "standard",
            "market_product_id": cm.get("idProduct"),
            "currency": cm.get("unit") or "EUR",
            "price": float(price) if price else None,
            "price_field": next((f for f in fields if cm.get(f)), None),
            "updated_at": cm.get("updated"),
            # True when this price describes an ordinary print and a 1st-edition
            # copy therefore needs the multiplier. False when the price already
            # is the 1st edition, or when there is no price to adjust.
            "first_edition_multiplier_applies": bool(
                cm.get("idProduct")
                and cm.get("idProduct") not in stamped_only
                and "1st-edition" in (entry.get("stamp") or [])
            ),
            "price_is_first_edition": cm.get("idProduct") in stamped_only,
        })
    return out


class TcgdexSource:
    name = "tcgdex"

    def __init__(self, config):
        self.base = getattr(config, "TCGDEX_BASE_URL", BASE_URL)
        self.lang = getattr(config, "TCGDEX_LANG", "en")
        self.timeout = config.HTTP_TIMEOUT
        self.retries = config.HTTP_RETRIES
        self.max_backoff = getattr(config, "HTTP_MAX_BACKOFF", 30)
        self.session = requests.Session()
        self.session.headers["User-Agent"] = "tombot-pokemon-tracker/0.1"

    # ------------------------------------------------------------------ http
    def _get(self, path: str) -> dict | None:
        url = f"{self.base}/{self.lang}{path}"
        last = None
        for attempt in range(self.retries):
            try:
                r = self.session.get(url, timeout=self.timeout)
                if r.status_code == 200 and r.content:
                    return r.json()
                if r.status_code == 404:
                    return None            # a card this source does not carry
                if r.status_code in (429, 403):
                    raise RateLimited(f"rate limited on {path}")
                last = f"HTTP {r.status_code}"
            except requests.RequestException as e:
                last = str(e)
            wait = min(self.max_backoff, 2 ** attempt)
            log.warning("%s failed (%s), retry %d/%d in %ss",
                        path, last, attempt + 1, self.retries, wait)
            time.sleep(wait)
        raise RuntimeError(f"{url} failed after {self.retries} attempts: {last}")

    # ---------------------------------------------------------------- prices
    def fetch_card(self, card_id: str) -> dict | None:
        return self._get(f"/cards/{card_id}")

    def fetch_variants(self, card_id: str) -> list[dict]:
        card = self.fetch_card(card_id)
        return parse_variants(card) if card else []

    def fetch_prices(self, card_ids: list[str]) -> dict[str, dict]:
        """Per-card variant prices.

        One request per card — this API has no bulk-by-id query. There is no
        published rate limit, but a partial result is still returned if the run
        is cut short, so nothing is lost.
        """
        out: dict[str, dict] = {}
        for card_id in card_ids:
            try:
                card = self.fetch_card(card_id)
            except RateLimited:
                log.error("rate limited after %d cards; returning partial", len(out))
                break
            except RuntimeError as e:
                log.warning("skipping %s: %s", card_id, e)
                continue
            if not card:
                continue
            variants = parse_variants(card)
            if variants:
                out[card_id] = {"source": "cardmarket", "variants": variants}
        return out

    # --------------------------------------------------------------- catalog
    def image_url(self, card: dict, quality: str = "high", fmt: str = "webp") -> str | None:
        """TCGdex image URLs arrive without an extension; you append it.

            https://assets.tcgdex.net/en/base/base1/7  ->  .../7/high.webp
        """
        base = card.get("image")
        return f"{base}/{quality}.{fmt}" if base else None

    def fetch_set(self, set_id: str) -> dict | None:
        s = self._get(f"/sets/{set_id}")
        if not s:
            return None
        return {
            "id": s["id"],
            "name": s.get("name"),
            "series": (s.get("serie") or {}).get("name"),
            "printed_total": (s.get("cardCount") or {}).get("official"),
            "total": (s.get("cardCount") or {}).get("total"),
            "release_date": s.get("releaseDate"),
            "ptcgo_code": None,
            "logo_url": f"{s['logo']}/high.webp" if s.get("logo") else None,
            "symbol_url": f"{s['symbol']}/high.webp" if s.get("symbol") else None,
        }

    def fetch_cards(self, set_id: str) -> Iterator[dict]:
        payload = self._get(f"/sets/{set_id}") or {}
        for brief in payload.get("cards") or []:
            yield {"id": brief.get("id"), "name": brief.get("name"),
                   "number": brief.get("localId")}
