"""Refreshing prices actually fetches prices (#114).

For weeks the Base Set 2 Alakazam read 34.49 while tcggo had it at 52.08.
Three things together kept it there: the HTTP cache never expired, so every
re-import replayed September's pages for free; the button and the scheduler
only copied stored prices and fetched nothing; and the dashboard showed the
date of the click as if prices had been renewed.
"""
import os
import time

import pytest

from tombot.config import Config
from tombot.services.budget import BudgetExhausted, RequestBudget
from tombot.services.httpcache import HttpCache
from tombot.services.market_import import ImportInterrupted, MarketImporter
from tombot.services.price_refresh import refresh_prices
from tombot.services.pricing import PricingService
from tombot.services.repository import PokemonRepo
from tombot.services.sources.tcggo import RateLimited, TcggoSource


def _card(number, price, version="Unlimited", code="B2"):
    return {"card_code_number": f"{code} {number}", "name": f"Card {number}",
            "version": version, "artist": f"Artist {number}",
            "cardmarket_id": 1000 + number,
            "prices": {"cardmarket": {"currency": "EUR", "30d_average": price,
                                      "7d_average": price - 1,
                                      "lowest_near_mint": price + 1,
                                      "available_items": 10}}}


class _Source:
    """tcggo by episode, metered through a real RequestBudget.

    `pages[episode_id]` is a list of pages; `fail_at[(episode_id, page)]` is an
    exception class to raise there instead of answering.
    """
    game = "pokemon"

    def __init__(self, pages, budget=None, fail_at=None):
        self.pages, self.budget, self.fail_at = pages, budget, fail_at or {}
        self.calls = []

    def _get(self, path, params, fresh=False):
        ep, page = params["episode_id"], params["page"]
        self.calls.append((ep, page, fresh))
        if self.budget is not None:
            self.budget.reserve(1)
        exc = self.fail_at.get((ep, page))
        if exc is BudgetExhausted:
            raise BudgetExhausted("tcggo", 0, 0)
        if exc is not None:
            raise exc("tcggo: rate limited by the plan (429)")
        pages = self.pages.get(ep, [])
        return {"data": pages[page - 1] if page <= len(pages) else []}


@pytest.fixture()
def repo(tmp_path):
    r = PokemonRepo(tmp_path / "r.db")
    r.init_db()
    return r


def _seed(repo, episode_id, rows, code="B2", age_days=0):
    """Import a set at an old price, as if it were done `age_days` ago."""
    MarketImporter(repo, _Source({episode_id: [rows]})).import_episode(episode_id)
    with repo.tx() as c:
        c.execute("""UPDATE market_products SET updated_at = datetime('now', ?)
                      WHERE episode_id = ?""", (f"-{age_days} days", episode_id))
    return {r["code"]: r for r in repo._all(
        "SELECT * FROM market_products WHERE episode_id=?", (episode_id,))}


def _products(repo, episode_id):
    return {(r["code"], r["version"]): r for r in repo._all(
        "SELECT * FROM market_products WHERE episode_id=?", (episode_id,))}


# ------------------------------------------------------------------ the cache

def _age(cache, path, params, days):
    f = cache._file(cache.key(path, params))
    old = time.time() - days * 86400
    os.utime(f, (old, old))


def test_an_expired_entry_is_not_served(tmp_path):
    cache = HttpCache(tmp_path, ttl_days=7)
    cache.put("/x", {"a": 1}, {"v": 1})
    assert cache.get("/x", {"a": 1}) == {"v": 1}

    _age(cache, "/x", {"a": 1}, 8)
    assert cache.get("/x", {"a": 1}) is None


def test_a_caller_can_ask_for_a_shorter_age_but_not_a_longer_one(tmp_path):
    cache = HttpCache(tmp_path, ttl_days=7)
    cache.put("/x", None, {"v": 1})
    _age(cache, "/x", None, 2)

    assert cache.get("/x", None) == {"v": 1}
    assert cache.get("/x", None, max_age_days=1) is None
    _age(cache, "/x", None, 8)
    assert cache.get("/x", None, max_age_days=30) is None


def test_a_sets_price_pages_expire_after_a_day_and_set_lists_do_not(tmp_path, repo,
                                                                      monkeypatch):
    """The pages that carry prices go stale fast; the list of sets barely moves."""
    monkeypatch.setattr(Config, "TCGGO_API_KEY", "test-key", raising=False)
    cache = HttpCache(tmp_path / "c", ttl_days=30)
    budget = RequestBudget(repo, "tcggo", limit=50)
    source = TcggoSource(Config, budget=budget, cache=cache)

    class Resp:
        status_code = 200

        @staticmethod
        def json():
            return {"data": []}

    monkeypatch.setattr(source.session, "get", lambda *a, **k: Resp())
    prices = ("/pokemon/cards/search", {"episode_id": 5, "page": 1})
    sets = ("/pokemon/episodes", {"page": 1})
    for path, params in (prices, sets):
        source._get(path, params)
        _age(cache, path, params, 2)
    assert budget.used() == 2

    source._get(*sets)
    assert budget.used() == 2, "a two-day-old set list is still good"
    source._get(*prices)
    assert budget.used() == 3, "a two-day-old price page must be fetched again"


def test_fresh_skips_the_cache_but_still_fills_it(tmp_path, repo, monkeypatch):
    monkeypatch.setattr(Config, "TCGGO_API_KEY", "test-key", raising=False)
    cache = HttpCache(tmp_path / "c", ttl_days=30)
    budget = RequestBudget(repo, "tcggo", limit=50)
    source = TcggoSource(Config, budget=budget, cache=cache)
    answers = iter([{"v": 1}, {"v": 2}])

    class Resp:
        status_code = 200

        @staticmethod
        def json():
            return next(answers)

    monkeypatch.setattr(source.session, "get", lambda *a, **k: Resp())
    assert source._get("/x") == {"v": 1}
    assert source._get("/x", fresh=True) == {"v": 2}
    assert source._get("/x") == {"v": 2}
    assert budget.used() == 2


def test_a_429_is_its_own_error(repo, monkeypatch):
    monkeypatch.setattr(Config, "TCGGO_API_KEY", "test-key", raising=False)
    source = TcggoSource(Config, budget=RequestBudget(repo, "tcggo", limit=5))

    class Resp:
        status_code = 429

    monkeypatch.setattr(source.session, "get", lambda *a, **k: Resp())
    with pytest.raises(RateLimited):
        source._get("/x")


# --------------------------------------------------- an interrupted import

@pytest.mark.parametrize("failure", [BudgetExhausted, RateLimited])
def test_a_set_cut_short_is_left_exactly_as_it_was(repo, failure):
    """Storing page 1 and pruning against it deleted everything on page 2."""
    page1 = [_card(n, 10.0) for n in range(1, 101)]
    page2 = [_card(n, 10.0) for n in range(101, 121)]
    before = _seed(repo, 7, page1 + page2)
    assert len(before) == 120

    newer = [[_card(n, 20.0) for n in range(1, 101)], page2]
    importer = MarketImporter(repo, _Source({7: newer}, fail_at={(7, 2): failure}))
    with pytest.raises(ImportInterrupted) as e:
        importer.import_episode(7)

    assert e.value.page == 2
    after = _products(repo, 7)
    assert len(after) == 120, "nothing may be pruned"
    assert after[("B2 1", "Unlimited")]["price"] == 10.0, "nothing may be written"


def test_a_set_coming_back_short_keeps_its_prices_but_not_the_deletion(repo):
    _seed(repo, 7, [_card(n, 10.0) for n in range(1, 41)])

    short = [[_card(n, 20.0) for n in range(1, 21)]]
    result = MarketImporter(repo, _Source({7: short})).import_episode(
        7, max_prune=10)

    assert result["prune_held"] == 20
    assert result["pruned"] == 0
    after = _products(repo, 7)
    assert len(after) == 40
    assert after[("B2 1", "Unlimited")]["price"] == 20.0


# ----------------------------------------------------------- the refresh

def test_a_refresh_fetches_new_prices_and_reprices_the_collection(repo):
    """The Alakazam case: an old price in the database, a new one upstream."""
    stored = _seed(repo, 7, [_card(1, 34.49)], age_days=50)
    repo.upsert_official_set({"id": "b2", "name": "Base Set 2", "series": "Base",
                              "printed_total": 130, "total": 130,
                              "release_date": "2000/02/24", "ptcgo_code": "B2",
                              "logo_url": None, "symbol_url": None})
    repo.upsert_cards([{"id": "b2-1", "official_set_id": "b2", "name": "Alakazam",
                        "number": "1", "rarity": "rare"}])
    repo.upsert_collection_item({"card_id": "b2-1", "variant": "normal",
                                 "condition": "M/NM", "language": "es",
                                 "market_product_id": stored["B2 1"]["id"]})
    pricing = PricingService(repo, Config)
    pricing.refresh()
    assert repo.get_price("b2-1", "normal")["price"] == pytest.approx(34.49)

    budget = RequestBudget(repo, "tcggo", limit=95)
    source = _Source({7: [[_card(1, 52.08)]]}, budget=budget)
    summary = refresh_prices(repo, source, budget, pricing)

    assert [i["episode_id"] for i in summary["imported"]] == [7]
    assert summary["requests"] == 1          # a short page is the last one
    assert summary["remaining"] == 94
    assert all(fresh for _, _, fresh in source.calls), "must bypass the cache"
    product = _products(repo, 7)[("B2 1", "Unlimited")]
    assert product["price"] == pytest.approx(52.08)
    assert product["updated_at"][:10] == repo._one(
        "SELECT date('now') AS d")["d"]
    assert repo.get_price("b2-1", "normal")["price"] == pytest.approx(52.08)
    assert repo.get_meta("last_price_refresh") is not None


def test_the_oldest_prices_go_first(repo):
    _seed(repo, 1, [_card(1, 1.0)], age_days=3)
    _seed(repo, 2, [_card(1, 1.0, code="XX")], age_days=30)
    _seed(repo, 3, [_card(1, 1.0, code="YY")], age_days=10)

    source = _Source({1: [[_card(1, 2.0)]], 2: [[_card(1, 2.0, code="XX")]],
                      3: [[_card(1, 2.0, code="YY")]]})
    summary = refresh_prices(repo, source, None, PricingService(repo, Config))

    assert [i["episode_id"] for i in summary["imported"]] == [2, 3, 1]


def test_it_stops_before_a_set_the_allowance_cannot_cover(repo):
    _seed(repo, 1, [_card(1, 1.0)], age_days=5)
    _seed(repo, 2, [_card(1, 1.0, code="XX")], age_days=4)
    budget = RequestBudget(repo, "tcggo", limit=10)
    budget.reserve(4)                    # 6 left: one set fits, then 5 do not

    source = _Source({1: [[_card(1, 2.0)]], 2: [[_card(1, 2.0, code="XX")]]},
                     budget=budget)
    summary = refresh_prices(repo, source, budget, PricingService(repo, Config))

    assert [i["episode_id"] for i in summary["imported"]] == [1]
    assert [p["episode_id"] for p in summary["pending"]] == [2]
    assert summary["stopped"] == "budget"
    assert _products(repo, 2)[("XX 1", "Unlimited")]["price"] == 1.0


@pytest.mark.parametrize("failure,reason", [(BudgetExhausted, "budget"),
                                            (RateLimited, "rate_limited")])
def test_a_cut_mid_set_stops_the_run_and_reports_what_is_left(repo, failure, reason):
    _seed(repo, 1, [_card(1, 1.0)], age_days=5)
    _seed(repo, 2, [_card(n, 1.0, code="XX") for n in range(1, 31)], age_days=4)
    _seed(repo, 3, [_card(1, 1.0, code="YY")], age_days=3)

    source = _Source({1: [[_card(1, 2.0)]],
                      2: [[_card(n, 2.0, code="XX") for n in range(1, 31)]],
                      3: [[_card(1, 2.0, code="YY")]]},
                     fail_at={(2, 1): failure})
    summary = refresh_prices(repo, source, None, PricingService(repo, Config))

    assert summary["stopped"] == reason
    assert [i["episode_id"] for i in summary["imported"]] == [1]
    assert [p["episode_id"] for p in summary["pending"]] == [2, 3]
    set2 = _products(repo, 2)
    assert len(set2) == 30
    assert all(p["price"] == 1.0 for p in set2.values())


def test_any_other_error_stops_the_run_rather_than_paying_to_repeat_it(repo):
    """A rejected key fails every set alike, and each try is a billed request."""
    _seed(repo, 1, [_card(1, 1.0)], age_days=5)
    _seed(repo, 2, [_card(1, 1.0, code="XX")], age_days=4)

    class KeyRejected(RuntimeError):
        def __init__(self, _msg):
            super().__init__("tcggo: the API key was rejected (401)")

    source = _Source({}, fail_at={(1, 1): KeyRejected, (2, 1): KeyRejected})
    summary = refresh_prices(repo, source, None, PricingService(repo, Config))

    assert summary["stopped"] == "error"
    assert [f["episode_id"] for f in summary["failed"]] == [1]
    assert [p["episode_id"] for p in summary["pending"]] == [2]
    assert len(source.calls) == 1


def test_a_set_that_would_lose_many_products_stops_the_run(repo):
    _seed(repo, 1, [_card(n, 1.0) for n in range(1, 41)], age_days=5)
    _seed(repo, 2, [_card(1, 1.0, code="XX")], age_days=4)

    source = _Source({1: [[_card(n, 2.0) for n in range(1, 11)]],
                      2: [[_card(1, 2.0, code="XX")]]})
    summary = refresh_prices(repo, source, None, PricingService(repo, Config))

    assert summary["stopped"] == "prune_held"
    assert summary["imported"][0]["prune_held"] == 30
    assert len(_products(repo, 1)) == 40
    assert [p["episode_id"] for p in summary["pending"]] == [2]


def test_nothing_fetched_is_not_recorded_as_a_refresh(repo):
    _seed(repo, 1, [_card(1, 1.0)], age_days=5)
    budget = RequestBudget(repo, "tcggo", limit=5)          # under one set's cost

    summary = refresh_prices(repo, _Source({}, budget=budget), budget,
                             PricingService(repo, Config))

    assert summary["imported"] == []
    assert summary["stopped"] == "budget"
    assert repo.get_meta("last_price_refresh") is None


def test_copying_stored_prices_is_not_recorded_as_a_refresh(repo):
    """PricingService.refresh fetches nothing, so it must not say it did."""
    PricingService(repo, Config).refresh()
    assert repo.get_meta("last_price_refresh") is None


# ------------------------------------------------------------- the dashboard

def test_the_dashboard_shows_the_date_of_the_prices(tmp_path, monkeypatch):
    for attr, value in (("DB_PATH", tmp_path / "a.db"), ("DATA_DIR", tmp_path),
                        ("MEDIA_DIR", tmp_path / "m"),
                        ("CATALOG_IMG_DIR", tmp_path / "m" / "c"),
                        ("COLLECTION_IMG_DIR", tmp_path / "m" / "i"),
                        ("THUMB_DIR", tmp_path / "m" / "t")):
        monkeypatch.setattr(Config, attr, value)
    repo = PokemonRepo(Config.DB_PATH)
    repo.init_db()
    _seed(repo, 1, [_card(1, 1.0)], age_days=20)
    repo.set_meta("last_price_refresh", "2099-01-01")       # a click, not a price

    from tombot import create_app
    client = create_app(Config).test_client()
    expected = repo._one("SELECT date('now', '-20 days') AS d")["d"]

    assert client.get("/api/dashboard").get_json()["last_price_refresh"] == expected
    assert client.get("/api/meta").get_json()["last_price_refresh"] == expected
