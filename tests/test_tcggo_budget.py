"""The daily request cap, and the tcggo adapter's parsing.

The cap is the part with money behind it: the plan bills per request past the
allowance, so these tests are about it being impossible to exceed rather than
unlikely to be.
"""
import json
import pathlib
import threading

import pytest

from tombot.config import DEFAULT_MODIFIERS
from tombot.services.budget import BudgetExhausted, RequestBudget
from tombot.services.repository import PokemonRepo
from tombot.services.sources.tcggo import TcggoSource

FIX = pathlib.Path(__file__).parent / "fixtures" / "tcggo"


@pytest.fixture()
def repo(tmp_path):
    r = PokemonRepo(tmp_path / "b.db")
    r.init_db(DEFAULT_MODIFIERS)
    return r


# ------------------------------------------------------------------- budget

def test_the_cap_is_a_hard_stop(repo):
    b = RequestBudget(repo, "tcggo", limit=3)
    for _ in range(3):
        b.reserve()
    assert b.remaining() == 0
    with pytest.raises(BudgetExhausted) as e:
        b.reserve()
    assert "3/3" in str(e.value)
    assert "nothing was sent" in str(e.value)


def test_a_restart_does_not_hand_back_a_fresh_allowance(repo, tmp_path):
    """An in-memory counter would let a crash loop spend the cap many times."""
    RequestBudget(repo, "tcggo", limit=5).reserve(4)

    reopened = PokemonRepo(tmp_path / "b.db")
    reopened.init_db(DEFAULT_MODIFIERS)
    fresh = RequestBudget(reopened, "tcggo", limit=5)

    assert fresh.used() == 4
    assert fresh.remaining() == 1


def test_a_reservation_larger_than_what_is_left_is_refused_whole(repo):
    """Partial reservations would send some requests and report failure."""
    b = RequestBudget(repo, "tcggo", limit=10)
    b.reserve(8)
    with pytest.raises(BudgetExhausted):
        b.reserve(3)
    assert b.used() == 8, "the refused reservation must not have been counted"


def test_two_threads_cannot_both_take_the_last_slot(repo):
    """The check and the increment share a transaction, so only one wins."""
    b = RequestBudget(repo, "tcggo", limit=20)
    b.reserve(19)

    granted, refused = [], []
    barrier = threading.Barrier(8)

    def race():
        barrier.wait()
        try:
            b.reserve()
            granted.append(1)
        except BudgetExhausted:
            refused.append(1)

    threads = [threading.Thread(target=race) for _ in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert len(granted) == 1, f"{len(granted)} threads got the last slot"
    assert len(refused) == 7
    assert b.used() == 20


def test_providers_are_counted_separately(repo):
    a, c = RequestBudget(repo, "tcggo", 2), RequestBudget(repo, "other", 2)
    a.reserve(2)
    c.reserve(1)                       # must not be blocked by tcggo's spend
    assert a.remaining() == 0
    assert c.remaining() == 1


def test_a_zero_limit_blocks_everything(repo):
    """Turning the source off must not be one forgotten call away from billing."""
    with pytest.raises(BudgetExhausted):
        RequestBudget(repo, "tcggo", limit=0).reserve()


# ------------------------------------------------------------------ adapter

def test_no_request_is_sent_once_the_budget_is_spent(repo, monkeypatch):
    """The reservation happens before the HTTP call, not after it."""
    from tombot.config import Config

    monkeypatch.setattr(Config, "TCGGO_API_KEY", "test-key", raising=False)
    sent = []
    source = TcggoSource(Config, budget=RequestBudget(repo, "tcggo", limit=1))
    monkeypatch.setattr(source.session, "get",
                        lambda *a, **k: sent.append(a) or (_ for _ in ()).throw(
                            AssertionError("should not be reached")))

    with pytest.raises(AssertionError):
        source._get("/pokemon/cards/search")     # first one is allowed through
    with pytest.raises(BudgetExhausted):
        source._get("/pokemon/cards/search")     # second must not reach the net
    assert len(sent) == 1


def test_a_run_that_hits_the_cap_returns_what_it_has(repo, monkeypatch):
    """Partial results cost nothing; raising would throw away paid-for work."""
    from tombot.config import Config

    monkeypatch.setattr(Config, "TCGGO_API_KEY", "test-key", raising=False)
    source = TcggoSource(Config, budget=RequestBudget(repo, "tcggo", limit=2))
    payload = json.loads((FIX / "flareon-ju19.json").read_text())

    class FakeResponse:
        status_code = 200

        @staticmethod
        def json():
            return payload

    # Patched at the socket, not at _get: _get is where the budget is spent,
    # so replacing it would test nothing.
    monkeypatch.setattr(source.session, "get", lambda *a, **k: FakeResponse())

    out = source.fetch_prices(["base2-19", "base1-4", "base1-7", "base2-3"])

    assert len(out) == 2, "should stop at the cap, not raise"
    assert out["base2-19"]["variants"][0]["market_product_id"] == 273816


# ------------------------------------------------------------------ parsing

def test_the_two_jungle_flareons_get_different_products():
    """The collision TCGdex has: here #3 and #19 are separate products."""
    holo = json.loads((FIX / "flareon-ju3.json").read_text())["data"][0]
    plain = json.loads((FIX / "flareon-ju19.json").read_text())["data"][0]

    a, b = TcggoSource.parse_card(holo), TcggoSource.parse_card(plain)
    assert a["market_product_id"] == 273800
    assert b["market_product_id"] == 273816
    assert a["market_product_id"] != b["market_product_id"]
    assert b["price"] == pytest.approx(10.72)      # not the holo's 49.31


def test_print_runs_are_separate_cards_with_their_own_keys():
    """Shadowless and 1st Edition Shadowless are distinct here, unlike upstream."""
    shadowless = json.loads((FIX / "charizard-shadowless.json").read_text())["data"]
    first_ed = json.loads((FIX / "charizard-1st-shadowless.json").read_text())["data"]

    a, b = TcggoSource.parse_card(shadowless), TcggoSource.parse_card(first_ed)
    assert a["key"] == "shadowless"
    assert b["key"] == "1st-edition:shadowless"


def test_tcggo_has_its_own_shared_product_and_the_data_shows_it():
    """Both Charizard print runs report product 660224 with different prices.

    Recorded so the guard is not quietly dropped for this source: one of these
    two mappings is wrong, whichever it turns out to be.
    """
    a = TcggoSource.parse_card(
        json.loads((FIX / "charizard-shadowless.json").read_text())["data"])
    b = TcggoSource.parse_card(
        json.loads((FIX / "charizard-1st-shadowless.json").read_text())["data"])

    assert a["market_product_id"] == b["market_product_id"] == 660224
    assert a["price"] != b["price"]


def test_stock_and_country_prices_survive_parsing():
    """A price with nothing listed behind it is a number, not an offer."""
    card = json.loads((FIX / "flareon-ju3.json").read_text())["data"][0]
    p = TcggoSource.parse_card(card)

    assert p["available_items"] == 412
    assert p["lowest_by_country"]["es"] == 199
    assert p["lowest_by_country"]["de"] == 65
    assert p["currency"] == "EUR"
