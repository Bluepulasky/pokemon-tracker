"""Read illustrators back out of the cached tcggo responses.

The reprint-group key is name + artist, and tcggo names the artist on every card
record. Sets imported before the column existed have it blank; re-importing to
fill it would spend the metered allowance, so this recovers it from the request
cache that those imports already wrote — no network, no cost.
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


def scan_cache_for_artists(data_dir=None) -> dict[int, str]:
    """{cardmarket product id -> illustrator name} from every cached response."""
    out: dict[int, str] = {}
    for directory in _cache_dirs(data_dir):
        for f in directory.glob("*.json"):
            try:
                payload = json.loads(f.read_text())
            except (OSError, ValueError):
                continue
            for rec in _iter_card_records(payload):
                name = _artist_name(rec.get("artist"))
                if name:
                    out.setdefault(int(rec["cardmarket_id"]), name)
    return out
