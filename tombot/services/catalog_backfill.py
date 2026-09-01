"""Recover catalog metadata from the cached tcggo responses.

Some fields tcggo returns on every card record are not stored by the importer
that first ran — the illustrator (the reprint-group key) and the supertype
(Pokémon / Trainer / Energy, the card-type filter). Re-importing to fill them
would spend the metered allowance, so this reads them back out of the request
cache those imports already wrote — no network, no cost.
"""
from __future__ import annotations

import json
import logging
from pathlib import Path

log = logging.getLogger(__name__)


def _artist_name(artist) -> str | None:
    if isinstance(artist, dict):
        return artist.get("name") or artist.get("slug") or None
    return artist or None


def _iter_card_records(payload):
    """Card dicts inside one cached response, whatever wrapping it has."""
    if isinstance(payload, dict) and isinstance(payload.get("body"), str):
        try:
            payload = json.loads(payload["body"])
        except ValueError:
            return
    data = payload.get("data") if isinstance(payload, dict) else payload
    if isinstance(data, dict):
        data = [data]
    if isinstance(data, list):
        for rec in data:
            if isinstance(rec, dict) and rec.get("cardmarket_id"):
                yield rec


def _cache_dirs(data_dir) -> list[Path]:
    """Where imports may have written the tcggo cache, newest layout first."""
    candidates = []
    if data_dir is not None and hasattr(data_dir, "__truediv__"):
        candidates.append(Path(data_dir) / ".cache-tcggo")
    candidates += [Path(".cache/tcggo"), Path(".cache/tcggo-bulk"),
                   Path("data/.cache-tcggo")]
    return [d for d in dict.fromkeys(candidates) if d.is_dir()]


def scan_cache_for_card_meta(data_dir=None) -> dict[int, dict]:
    """{cardmarket product id -> {artist, supertype}} from every cached response.

    A field is only recorded when present, so a record missing one does not
    blank a value another record supplied for the same product.
    """
    out: dict[int, dict] = {}
    for directory in _cache_dirs(data_dir):
        for f in directory.glob("*.json"):
            try:
                payload = json.loads(f.read_text())
            except (OSError, ValueError):
                continue
            for rec in _iter_card_records(payload):
                pid = int(rec["cardmarket_id"])
                meta = out.setdefault(pid, {})
                artist = _artist_name(rec.get("artist"))
                if artist and "artist" not in meta:
                    meta["artist"] = artist
                supertype = rec.get("supertype")
                if supertype and "supertype" not in meta:
                    meta["supertype"] = supertype
    return out
