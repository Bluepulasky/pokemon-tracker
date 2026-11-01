"""On-disk cache for responses from a metered API.

Every tcggo request is billed past a daily allowance, so a response that has
already been paid for must never be paid for twice. A re-run of a scan, a
crash halfway through, or a second look at the same expansion should all cost
nothing.

Keyed by the full request (path plus sorted params), so changing a page number
or a filter is a different entry rather than a silent hit on the wrong data.

But an entry must also *expire*. With no TTL, a set's price pages were served
from September forever: every re-import read the same file, rewrote the same
numbers with today's date, spent nothing and changed nothing (#114). So there is
a default age for everything, and a caller can ask for a shorter one for data
that moves — prices — than for data that barely does, like the list of sets.
"""
from __future__ import annotations

import hashlib
import json
import logging
import pathlib
import time

log = logging.getLogger(__name__)


class HttpCache:
    def __init__(self, directory, ttl_days: float | None = None):
        self.dir = pathlib.Path(directory)
        self.ttl = None if ttl_days is None else ttl_days * 86400
        self.hits = 0
        self.misses = 0

    @staticmethod
    def key(path: str, params: dict | None) -> str:
        blob = json.dumps([path, sorted((params or {}).items())], sort_keys=True)
        return hashlib.sha256(blob.encode()).hexdigest()[:32]

    def _file(self, key: str) -> pathlib.Path:
        return self.dir / f"{key}.json"

    def get(self, path: str, params: dict | None, max_age_days: float | None = None):
        """The stored response, or None if there is none or it is too old.

        `max_age_days` can only make an entry expire sooner than the cache's own
        TTL, never later.
        """
        f = self._file(self.key(path, params))
        if not f.exists():
            self.misses += 1
            return None
        ttl = self.ttl
        if max_age_days is not None:
            ttl = min(ttl, max_age_days * 86400) if ttl is not None else max_age_days * 86400
        if ttl is not None and time.time() - f.stat().st_mtime > ttl:
            self.misses += 1
            return None
        try:
            payload = json.loads(f.read_text())
        except (OSError, ValueError):
            # A truncated file must cost one request, not poison every run.
            self.misses += 1
            return None
        self.hits += 1
        return payload

    def put(self, path: str, params: dict | None, payload) -> None:
        self.dir.mkdir(parents=True, exist_ok=True)
        f = self._file(self.key(path, params))
        tmp = f.with_suffix(".tmp")
        # Written whole then moved: a crash mid-write must not leave a file
        # that reads as a cached response.
        tmp.write_text(json.dumps(payload))
        tmp.replace(f)

    def stats(self) -> dict:
        return {"hits": self.hits, "misses": self.misses,
                "entries": len(list(self.dir.glob("*.json"))) if self.dir.exists() else 0}
