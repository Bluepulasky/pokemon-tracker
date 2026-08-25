"""Rate-limit handling.

A real install lost most of its sets when a bootstrap exhausted the upstream
allowance: the keyless quota is 1,000 requests/day and a full bootstrap fired
roughly 2,200. Rate limiting therefore has to be a first-class outcome —
distinguishable from a transient failure, non-destructive, and resumable.
"""
import types

import pytest

from tombot.config import Config
from tombot.services.importer import CatalogImporter
from tombot.services.sources.pokemontcgio import PokemonTcgIoSource, RateLimited


class _Resp:
    def __init__(self, status, headers=None, loc=None):
        self.status_code = status
        self.headers = dict(headers or {})
        if loc:
            self.headers["Location"] = loc
        self.content = b""

    def close(self):
        pass

    def json(self):
        return {}


def _source(status, headers=None, loc=None):
    src = PokemonTcgIoSource(Config)
    src.session = types.SimpleNamespace(
        headers={}, get=lambda *a, **k: _Resp(status, headers, loc))
    src.retries = 2
    src.max_backoff = 0            # do not really sleep in tests
    return src


@pytest.mark.parametrize("status", [429, 403])
def test_quota_responses_raise_rate_limited(status):
    """403 matters as much as 429 — it is what this API returns once the daily
    allowance is gone."""
    with pytest.raises(RateLimited):
        _source(status)._get("/cards")


def test_transient_failure_is_not_mistaken_for_a_quota_problem():
    """A 500 is worth retrying in seconds; a spent quota is not. Conflating them
    means either pointless retries or giving up on a recoverable blip."""
    with pytest.raises(RuntimeError) as exc:
        _source(500)._get("/cards")
    assert not isinstance(exc.value, RateLimited)


def test_long_retry_after_gives_up_instead_of_sleeping():
    with pytest.raises(RateLimited) as exc:
        _source(429, {"Retry-After": "3600"})._get("/cards")
    assert "3600" in str(exc.value)


def test_market_url_rate_limit_is_not_silent():
    """This previously looked identical to 'this card has no link', so a rate
    limit quietly marked cards unresolvable and kept hammering."""
    with pytest.raises(RateLimited):
        _source(429).resolve_market_url("base1-4")


def test_market_url_still_resolves_normally():
    src = _source(302, loc="https://cardmarket.com/en/Pokemon/Products/Singles/"
                           "Base-Set/Charizard-V2-BS4?utm_source=x")
    assert src.resolve_market_url("base1-4") == (
        "https://cardmarket.com/en/Pokemon/Products/Singles/Base-Set/Charizard-V2-BS4")


class _StubRepo:
    def __init__(self):
        self.cards = 0
    def upsert_official_set(self, s): pass
    def upsert_cards(self, c): self.cards += len(c); return len(c)
    def set_meta(self, *a): pass


class _FlakySource:
    """Imports `ok_sets` fine, then the quota runs out."""
    def __init__(self, ok_sets):
        self.ok = set(ok_sets)
    def fetch_set(self, sid):
        if sid not in self.ok:
            raise RateLimited("quota exhausted")
        return {"id": sid, "name": sid, "series": "x", "printed_total": 1,
                "total": 1, "release_date": "1999/01/09", "ptcgo_code": None,
                "logo_url": None, "symbol_url": None}
    def fetch_cards(self, sid):
        yield {"id": f"{sid}-1", "official_set_id": sid, "name": "c", "number": "1"}


def test_import_stops_on_rate_limit_and_reports_what_it_skipped():
    """Grinding through the remaining sets burns an allowance that is already
    spent and buries the cause under generic failures."""
    imp = CatalogImporter(_StubRepo(), _FlakySource(["base1", "base2"]), Config)
    result = imp.import_sets(["base1", "base2", "base3", "gym1", "neo1"])

    assert result["rate_limited"] is True
    assert set(result["sets"]) == {"base1", "base2"}, "work done before the limit is kept"
    assert set(result["not_attempted"]) == {"base3", "gym1", "neo1"}
    assert result["failed"] == [], "a quota stop is not a per-set failure"
